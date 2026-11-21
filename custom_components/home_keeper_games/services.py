"""The ``home_keeper_games.*`` services and the operations behind them.

Each service has 1 handler here, ``async (ctx, data) -> response``. The service
registration and the websocket twin of the service (``websocket_api.py``) both
call the same handler, so the 2 surfaces cannot do different things. The fields
of a service are in :data:`SERVICE_FIELDS`, and the websocket command takes the
same fields.

The gate of each service is in ``api_surface.SERVICES``. An ``admin_only``
service rejects a non-admin user with ``Unauthorized`` before the handler runs.
A ``caller_scoped`` service lets a non-admin user change only their own person,
and its handler checks that. A call with no user (an automation) is trusted.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er

from . import csv_io, import_export, models, people, projections
from .api_surface import SERVICES, ServiceSpec
from .backend_i18n import resolve_exception
from .config_flow import clean_currency, merge_flow_input
from .const import (
    CONF_CURRENCY,
    DOMAIN,
    MAX_CSV_BYTES,
    MAX_IMPORT_ROW_RESULTS,
    PANEL_VERSION,
)
from .coordinator import LibraryCoordinator, find_coordinator
from .covers import (
    async_bundle_cover,
    async_use_upload,
    copy_covers_out,
    covers_dir,
    release_cover,
)
from .models import LibraryError
from .store import LibraryStore, now, today

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class Ctx:
    """The context of 1 operation: Home Assistant, the coordinator and the caller."""

    hass: HomeAssistant
    coordinator: LibraryCoordinator
    actor: people.Actor

    @property
    def store(self) -> LibraryStore:
        """The store."""
        return self.coordinator.store

    def game_reply(self, game: dict[str, Any]) -> dict[str, Any]:
        """A game in a reply, projected for the caller."""
        state = self.store.state
        current = state["games"].get(game["id"], game)
        return projections.project_game(
            state,
            current,
            viewer=self.actor.person_id,
            is_admin=self.actor.is_admin,
        )


Handler = Callable[[Ctx, dict[str, Any]], Awaitable[dict[str, Any]]]

# ── Field schemas ────────────────────────────────────────────────────────────

_OPT_STR = vol.Any(None, cv.string)
_OPT_INT = vol.Any(None, vol.Coerce(int))
_OPT_NUM = vol.Any(None, vol.Coerce(float))
_STR_LIST = vol.All(cv.ensure_list, [cv.string])
_FORMAT = vol.In(models.FORMATS)
_ORDER = vol.All(vol.Coerce(int), vol.Range(min=0))

_GAME_FIELDS = {
    vol.Optional("title"): cv.string,
    vol.Optional("subtitle"): _OPT_STR,
    vol.Optional("authors"): _STR_LIST,
    vol.Optional("barcode"): _OPT_STR,
    vol.Optional("publisher"): _OPT_STR,
    vol.Optional("published"): vol.Any(None, cv.string, vol.Coerce(str)),
    vol.Optional("pages"): _OPT_INT,
    vol.Optional("language"): _OPT_STR,
    vol.Optional("subjects"): _STR_LIST,
    vol.Optional("series"): vol.Any(None, cv.string, dict),
    vol.Optional("description"): _OPT_STR,
    vol.Optional("tags"): _STR_LIST,
    vol.Optional("shared_notes"): _OPT_STR,
    vol.Optional("needs_details"): cv.boolean,
}
_COPY_FIELDS = {
    vol.Optional("shelf_id"): _OPT_STR,
    vol.Optional("format"): _FORMAT,
    vol.Optional("condition"): vol.Any(None, vol.In(models.CONDITIONS)),
    vol.Optional("acquired"): _OPT_STR,
    vol.Optional("acquired_from"): _OPT_STR,
    vol.Optional("price"): _OPT_NUM,
    vol.Optional("value"): _OPT_NUM,
    vol.Optional("signed"): cv.boolean,
    vol.Optional("first_edition"): cv.boolean,
    vol.Optional("note"): _OPT_STR,
}
_GAME_REF = {
    vol.Optional("game_id"): cv.string,
    vol.Optional("barcode"): cv.string,
    vol.Optional("title"): cv.string,
    vol.Optional("authors"): _STR_LIST,
}
_LOAN_FIELDS = {
    vol.Required("party"): cv.string,
    vol.Optional("started"): _OPT_STR,
    vol.Optional("due"): _OPT_STR,
    vol.Optional("note"): _OPT_STR,
    vol.Optional("add_task", default=True): cv.boolean,
}

SERVICE_FIELDS: dict[str, dict[Any, Any]] = {
    "add_room": {
        vol.Required("name"): cv.string,
        vol.Optional("area_id"): _OPT_STR,
        vol.Optional("order"): _ORDER,
    },
    "update_room": {
        vol.Required("room_id"): cv.string,
        vol.Optional("name"): cv.string,
        vol.Optional("area_id"): _OPT_STR,
        vol.Optional("order"): _ORDER,
    },
    "delete_room": {
        vol.Required("room_id"): cv.string,
        vol.Optional("force", default=False): cv.boolean,
    },
    "add_unit": {
        vol.Required("room_id"): cv.string,
        vol.Required("name"): cv.string,
        vol.Optional("note"): _OPT_STR,
        vol.Optional("order"): _ORDER,
    },
    "update_unit": {
        vol.Required("unit_id"): cv.string,
        vol.Optional("room_id"): cv.string,
        vol.Optional("name"): cv.string,
        vol.Optional("note"): _OPT_STR,
        vol.Optional("order"): _ORDER,
    },
    "delete_unit": {
        vol.Required("unit_id"): cv.string,
        vol.Optional("force", default=False): cv.boolean,
    },
    "add_shelf": {
        vol.Required("unit_id"): cv.string,
        vol.Required("name"): cv.string,
        vol.Optional("order"): _ORDER,
    },
    "update_shelf": {
        vol.Required("shelf_id"): cv.string,
        vol.Optional("unit_id"): cv.string,
        vol.Optional("name"): cv.string,
        vol.Optional("order"): _ORDER,
    },
    "delete_shelf": {
        vol.Required("shelf_id"): cv.string,
        vol.Optional("force", default=False): cv.boolean,
    },
    "add_game": {**_GAME_FIELDS},
    "update_game": {vol.Required("game_id"): cv.string, **_GAME_FIELDS},
    "delete_game": {vol.Required("game_id"): cv.string},
    "scan_barcode": {
        vol.Required("barcode"): cv.string,
        vol.Optional("shelf_id"): _OPT_STR,
        vol.Optional("format"): _FORMAT,
        vol.Optional("on_duplicate", default="ask"): vol.In(
            ("ask", "add_copy", "move", "skip")
        ),
    },
    "add_copy": {vol.Required("game_id"): cv.string, **_COPY_FIELDS},
    "update_copy": {vol.Required("copy_id"): cv.string, **_COPY_FIELDS},
    "move_copy": {
        vol.Required("copy_id"): cv.string,
        vol.Optional("shelf_id"): _OPT_STR,
    },
    "delete_copy": {vol.Required("copy_id"): cv.string},
    "set_cover": {
        vol.Required("game_id"): cv.string,
        vol.Required("kind"): vol.In(models.COVER_KINDS),
        vol.Optional("file_id"): cv.string,
    },
    "set_reading": {
        vol.Required("game_id"): cv.string,
        vol.Optional("person_id"): cv.string,
        vol.Optional("status"): vol.In((*models.STATUSES, models.STATUS_NONE)),
        vol.Optional("rating"): _OPT_INT,
        vol.Optional("page"): _OPT_INT,
        vol.Optional("started"): _OPT_STR,
        vol.Optional("finished"): _OPT_STR,
        vol.Optional("read_count"): vol.Coerce(int),
        vol.Optional("private_notes"): _OPT_STR,
    },
    "lend_game": {vol.Required("copy_id"): cv.string, **_LOAN_FIELDS},
    "borrow_game": {
        **_GAME_REF,
        **_LOAN_FIELDS,
        vol.Required("person_id"): cv.string,
        vol.Optional("format"): vol.Any(None, _FORMAT),
    },
    "return_loan": {
        vol.Required("loan_id"): cv.string,
        vol.Optional("returned"): _OPT_STR,
    },
    "update_loan": {
        vol.Required("loan_id"): cv.string,
        vol.Optional("party"): cv.string,
        vol.Optional("started"): _OPT_STR,
        vol.Optional("due"): _OPT_STR,
        vol.Optional("note"): _OPT_STR,
        vol.Optional("format"): vol.Any(None, _FORMAT),
    },
    "delete_loan": {vol.Required("loan_id"): cv.string},
    "add_to_wishlist": {
        **_GAME_REF,
        vol.Required("person_id"): cv.string,
        vol.Optional("buy", default=False): cv.boolean,
    },
    "update_wishlist": {
        vol.Required("game_id"): cv.string,
        vol.Optional("buy"): cv.boolean,
        vol.Optional("person_id"): cv.string,
    },
    "remove_from_wishlist": {vol.Required("game_id"): cv.string},
    "got_wishlist_game": {
        vol.Required("game_id"): cv.string,
        vol.Optional("shelf_id"): _OPT_STR,
        vol.Optional("format"): _FORMAT,
    },
    "set_person_settings": {
        vol.Required("person_id"): cv.string,
        vol.Optional("share_reading"): cv.boolean,
        vol.Optional("yearly_goal"): _OPT_INT,
        vol.Optional("wishlist_todo"): _OPT_STR,
    },
    "set_settings": {vol.Required("currency"): cv.string},
    "import_csv": {
        vol.Required("content"): cv.string,
        vol.Required("person_id"): cv.string,
        vol.Optional("shelf_id"): _OPT_STR,
        vol.Optional("import_notes", default=True): cv.boolean,
        vol.Optional("replace_reading", default=False): cv.boolean,
        vol.Optional("dry_run", default=False): cv.boolean,
    },
    "export_csv": {vol.Optional("person_id"): _OPT_STR},
    "export_data": {vol.Optional("files_dir"): _OPT_STR},
    "import_data": {
        vol.Required("document"): dict,
        vol.Optional("dry_run", default=False): cv.boolean,
        vol.Optional("files_dir"): _OPT_STR,
    },
    "list_games": {
        vol.Optional("query"): cv.string,
        vol.Optional("room_id"): cv.string,
        vol.Optional("shelf_id"): cv.string,
        vol.Optional("owned"): cv.boolean,
        vol.Optional("status"): vol.In(models.STATUSES),
        vol.Optional("person_id"): cv.string,
        vol.Optional("limit"): vol.All(vol.Coerce(int), vol.Range(min=1)),
    },
    "get_game": {vol.Required("game_id"): cv.string},
    "list_locations": {},
    "list_loans": {
        vol.Optional("status", default="all"): vol.In(("open", "returned", "all")),
        vol.Optional("direction"): vol.In(models.DIRECTIONS),
    },
    "list_people": {},
}


# ── Shared helpers ───────────────────────────────────────────────────────────


def _clean(data: dict[str, Any], *drop: str) -> dict[str, Any]:
    return {k: v for k, v in data.items() if k not in drop}


def _person_or_error(ctx: Ctx, person_id: str | None) -> str:
    """A known person id, else ``no_person`` or ``person_not_found``."""
    if not person_id:
        raise LibraryError("no_person")
    if people.person(ctx.hass, person_id) is None:
        raise LibraryError("person_not_found", id=person_id)
    return person_id


def _self_or_admin(ctx: Ctx, person_id: str | None) -> str:
    """The person of the call. A non-admin user can only name their own person."""
    target = person_id or ctx.actor.person_id
    if target != ctx.actor.person_id and not ctx.actor.is_admin:
        raise Unauthorized(context=None)
    return _person_or_error(ctx, target)


async def _add_game(ctx: Ctx, data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Add a game. Return ``(game, existing)``.

    With a barcode, a stored game with that barcode is returned. A game with a
    barcode and no title takes the barcode as its title and needs details.
    """
    fields = dict(data)
    code = models.barcode(fields.get("barcode"))
    if code is not None:
        if found := models.find_game_by_barcode(ctx.store.state, code):
            return dict(found), True
        fields["barcode"] = code
        if not fields.get("title"):
            fields["title"] = code
            fields["needs_details"] = True
    elif not fields.get("title"):
        raise LibraryError("barcode_or_title_required")
    game, existing = await ctx.store.add_game(fields)
    return ctx.store.game(game["id"]), existing


async def _resolve_game(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    """The game of ``game_id``, ``barcode`` or ``title``. A new game if none matches."""
    if data.get("game_id"):
        return ctx.store.game(data["game_id"])
    if data.get("barcode"):
        game, _ = await _add_game(ctx, {"barcode": data["barcode"]})
        return game
    if data.get("title"):
        key = models.title_key(data["title"], data.get("authors") or [])
        for game in ctx.store.state["games"].values():
            if models.title_key(game.get("title"), game.get("authors")) == key:
                return dict(game)
        game, _ = await _add_game(
            ctx, {"title": data["title"], "authors": data.get("authors") or []}
        )
        return game
    raise LibraryError("barcode_or_title_required")


async def _loan_reply(ctx: Ctx, loan_id: str) -> dict[str, Any]:
    """Run the loan task sync, then return the loan as stored."""
    await ctx.coordinator.loan_sync.async_reconcile()
    loan = ctx.store.state["loans"].get(loan_id)
    return {"loan": dict(loan) if loan else None}


# ── Locations ────────────────────────────────────────────────────────────────


async def _add_room(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    return {"room": await ctx.store.add_room(data)}


async def _update_room(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    return {"room": await ctx.store.update_room(data["room_id"], _clean(data))}


async def _delete_room(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    room = await ctx.store.delete_room(data["room_id"], force=data.get("force", False))
    return {"room": room}


async def _add_unit(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    return {"unit": await ctx.store.add_unit(data)}


async def _update_unit(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    unit = await ctx.store.update_unit(data["unit_id"], _clean(data))
    return {"unit": unit}


async def _delete_unit(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    unit = await ctx.store.delete_unit(data["unit_id"], force=data.get("force", False))
    return {"unit": unit}


async def _add_shelf(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    return {"shelf": await ctx.store.add_shelf(data)}


async def _update_shelf(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    return {"shelf": await ctx.store.update_shelf(data["shelf_id"], _clean(data))}


async def _delete_shelf(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    shelf = await ctx.store.delete_shelf(
        data["shelf_id"], force=data.get("force", False)
    )
    return {"shelf": shelf}


# ── Games ────────────────────────────────────────────────────────────────────


async def _add_game_service(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    game, existing = await _add_game(ctx, data)
    return {"game": ctx.game_reply(game), "existing": existing}


async def _update_game(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    game = await ctx.store.update_game(data["game_id"], _clean(data, "game_id"))
    return {"game": ctx.game_reply(game)}


async def _delete_game(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    game = await ctx.store.delete_game(data["game_id"])
    await ctx.coordinator.loan_sync.async_reconcile()
    return {"game": game}


def _copies_with_location(ctx: Ctx, game_id: str) -> list[dict[str, Any]]:
    state = ctx.store.state
    out = []
    for copy in models.copies_of(state, game_id):
        row = projections.project_copy(copy, is_admin=ctx.actor.is_admin)
        row["location"] = models.location_path(state, copy.get("shelf_id"))
        out.append(row)
    return out


async def _new_copy(ctx: Ctx, data: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Add a copy. Return ``(copy, from_wishlist)``.

    ``from_wishlist`` is True when the copy took its game off the wishlist.
    """
    game_id = str(data.get("game_id"))
    from_wishlist = models.copy_clears_wishlist(ctx.store.state, game_id)
    copy = await ctx.store.add_copy(data)
    if from_wishlist:
        await ctx.coordinator.wishlist_sync.async_run()
    return copy, from_wishlist


async def _scan_barcode(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    shelf_id = ctx.store.check_shelf(data.get("shelf_id"))
    copy_data: dict[str, Any] = {"shelf_id": shelf_id}
    if data.get("format"):
        copy_data["format"] = data["format"]
    code = models.barcode(data["barcode"])
    if code is None:
        raise LibraryError("field_required", field="barcode")
    existing = models.find_game_by_barcode(ctx.store.state, code)
    if existing is not None:
        copies = models.copies_of(ctx.store.state, existing["id"])
        mode = data.get("on_duplicate", "ask")
        if copies and mode in ("ask", "skip"):
            return {
                "result": "duplicate" if mode == "ask" else "skipped",
                "game": ctx.game_reply(existing),
                "copy": None,
                "existing_copies": _copies_with_location(ctx, existing["id"]),
                "from_wishlist": False,
            }
        if copies and mode == "move":
            target = next(
                (c for c in copies if c.get("shelf_id") != shelf_id), copies[0]
            )
            moved = await ctx.store.move_copy(target["id"], shelf_id)
            return {
                "result": "moved",
                "game": ctx.game_reply(existing),
                "copy": moved,
                "existing_copies": _copies_with_location(ctx, existing["id"]),
                "from_wishlist": False,
            }
        copy, from_wishlist = await _new_copy(
            ctx, {**copy_data, "game_id": existing["id"]}
        )
        return {
            "result": "added",
            "game": ctx.game_reply(existing),
            "copy": copy,
            "existing_copies": _copies_with_location(ctx, existing["id"]),
            "from_wishlist": from_wishlist,
        }
    game, _ = await _add_game(ctx, {"barcode": code})
    copy, from_wishlist = await _new_copy(ctx, {**copy_data, "game_id": game["id"]})
    return {
        "result": "not_found",
        "game": ctx.game_reply(game),
        "copy": copy,
        "existing_copies": [],
        "from_wishlist": from_wishlist,
    }


# ── Copies and covers ────────────────────────────────────────────────────────


async def _add_copy(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    copy, from_wishlist = await _new_copy(ctx, data)
    return {"copy": copy, "from_wishlist": from_wishlist}


async def _update_copy(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    copy = await ctx.store.update_copy(data["copy_id"], _clean(data, "copy_id"))
    return {"copy": copy}


async def _move_copy(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    return {"copy": await ctx.store.move_copy(data["copy_id"], data.get("shelf_id"))}


async def _delete_copy(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    return {"copy": await ctx.store.delete_copy(data["copy_id"])}


async def _set_cover(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    game_id = data["game_id"]
    kind = data["kind"]
    if kind == "custom":
        if not data.get("file_id"):
            raise LibraryError("field_required", field="file_id")
        game = await async_use_upload(
            ctx.hass, ctx.coordinator, game_id, data["file_id"]
        )
    else:
        game = await ctx.store.set_cover(game_id, "none", None)
    return {"game": ctx.game_reply(game)}


# ── Reading ──────────────────────────────────────────────────────────────────


async def _set_reading(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    person_id = _self_or_admin(ctx, data.get("person_id"))
    row = await ctx.store.set_reading(
        data["game_id"], person_id, _clean(data, "game_id", "person_id")
    )
    return {"game_id": data["game_id"], "person_id": person_id, "reading": row}


# ── Loans ────────────────────────────────────────────────────────────────────


async def _lend_game(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    loan = await ctx.store.add_loan({**data, "direction": "out"})
    return await _loan_reply(ctx, loan["id"])


async def _borrow_game(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    person_id = _person_or_error(ctx, data["person_id"])
    if not data.get("party"):
        raise LibraryError("field_required", field="party")
    game = await _resolve_game(ctx, data)
    loan = await ctx.store.add_loan(
        {
            **_clean(data, "game_id", "barcode", "title", "authors"),
            "direction": "in",
            "game_id": game["id"],
            "person_id": person_id,
        }
    )
    reply = await _loan_reply(ctx, loan["id"])
    reply["game"] = ctx.game_reply(game)
    return reply


async def _return_loan(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    loan = await ctx.store.return_loan(data["loan_id"], data.get("returned"))
    return await _loan_reply(ctx, loan["id"])


async def _update_loan(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    loan = await ctx.store.update_loan(data["loan_id"], _clean(data, "loan_id"))
    return await _loan_reply(ctx, loan["id"])


async def _delete_loan(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    loan = await ctx.store.delete_loan(data["loan_id"])
    await ctx.coordinator.loan_sync.async_reconcile()
    return {"loan": loan}


# ── Wishlist ─────────────────────────────────────────────────────────────────


async def _add_to_wishlist(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    person_id = _person_or_error(ctx, data["person_id"])
    game = await _resolve_game(ctx, data)
    game = await ctx.store.add_to_wishlist(
        game["id"], person_id, buy=data.get("buy", False)
    )
    await ctx.coordinator.wishlist_sync.async_run()
    return {"game": ctx.game_reply(game)}


async def _update_wishlist(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    if "person_id" in data:
        _person_or_error(ctx, data["person_id"])
    game = await ctx.store.update_wishlist(data["game_id"], _clean(data, "game_id"))
    await ctx.coordinator.wishlist_sync.async_run()
    return {"game": ctx.game_reply(game)}


async def _remove_from_wishlist(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    game = await ctx.store.remove_from_wishlist(data["game_id"])
    await ctx.coordinator.wishlist_sync.async_run()
    return {"game": ctx.game_reply(game)}


async def _got_wishlist_game(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    copy = await ctx.store.got_wishlist_game(data["game_id"], _clean(data, "game_id"))
    await ctx.coordinator.wishlist_sync.async_run()
    return {"copy": copy}


# ── People ───────────────────────────────────────────────────────────────────


async def _set_person_settings(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    person_id = data["person_id"]
    if not ctx.actor.is_admin and (
        person_id != ctx.actor.person_id or "wishlist_todo" in data
    ):
        raise Unauthorized(context=None)
    _person_or_error(ctx, person_id)
    entity_id = data.get("wishlist_todo")
    if entity_id and (
        not entity_id.startswith("todo.") or ctx.hass.states.get(entity_id) is None
    ):
        raise LibraryError("todo_entity_not_found", entity_id=entity_id)
    settings = await ctx.store.set_person_settings(person_id, _clean(data, "person_id"))
    if "wishlist_todo" in data:
        await ctx.coordinator.wishlist_sync.async_run()
    return {"person_id": person_id, "settings": settings}


async def _set_settings(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    currency = clean_currency(data["currency"])
    if currency is None:
        raise LibraryError("invalid_currency", currency=data["currency"])
    entry = ctx.coordinator.config_entry
    ctx.hass.config_entries.async_update_entry(
        entry, options=merge_flow_input(entry, {CONF_CURRENCY: currency})
    )
    # The store fires settings_updated, and the tab and the card read the
    # currency from get_state again.
    ctx.coordinator.async_check_settings()
    return {"currency": currency}


# ── Import and export ────────────────────────────────────────────────────────


async def _import_csv(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    content = data["content"]
    if len(content.encode("utf-8")) > MAX_CSV_BYTES:
        raise LibraryError("csv_too_large", mb=MAX_CSV_BYTES // (1024 * 1024))
    person_id = _person_or_error(ctx, data["person_id"])
    shelf_id = ctx.store.check_shelf(data.get("shelf_id"))
    rows = csv_io.parse(content)
    snapshot = models.clone(ctx.store.state)
    new_state, counts, results = await ctx.hass.async_add_executor_job(
        lambda: csv_io.apply_import(
            snapshot,
            rows,
            person_id=person_id,
            shelf_id=shelf_id,
            import_notes=data.get("import_notes", True),
            replace_reading=data.get("replace_reading", False),
            now=now(),
        )
    )
    dry_run = data.get("dry_run", False)
    summary = csv_io.summary_of(counts, counts["reading_kept"])
    if not dry_run:
        # The plan ran on a snapshot. The store merges it into the current
        # data, so a change made while the plan ran stays.
        await ctx.store.commit_import(
            snapshot, new_state, summary, person_id=person_id, source="csv"
        )
    lang = ctx.hass.config.language
    shown = []
    for result in results[:MAX_IMPORT_ROW_RESULTS]:
        row = {k: v for k, v in result.items() if k not in ("error", "placeholders")}
        row["message"] = (
            resolve_exception(lang, result["error"], **result["placeholders"])
            if "error" in result
            else ""
        )
        shown.append(row)
    return {
        "dry_run": dry_run,
        "counts": {key: counts[key] for key in csv_io.COUNT_KEYS},
        "rows": shown,
        "truncated": len(results) > MAX_IMPORT_ROW_RESULTS,
    }


async def _export_csv(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    person_id = data.get("person_id") or None
    if person_id:
        _person_or_error(ctx, person_id)
    content = csv_io.export(ctx.store.state, person_id)
    return {"filename": csv_io.export_filename(today()), "content": content}


# ── Home Keeper export and import ────────────────────────────────────────────


def _person_names(hass: HomeAssistant) -> dict[str, str]:
    return {p["person_id"]: str(p["name"]) for p in people.persons(hass)}


def _area_names(hass: HomeAssistant) -> dict[str, str]:
    return {area.id: area.name for area in ar.async_get(hass).async_list_areas()}


def _todo_names(hass: HomeAssistant) -> dict[str, str]:
    """The to-do entities that a wishlist can use. The library lists are left out."""
    registry = er.async_get(hass)
    out = {}
    for state in hass.states.async_all("todo"):
        entry = registry.async_get(state.entity_id)
        if entry is not None and entry.platform == DOMAIN:
            continue
        out[state.entity_id] = str(
            state.attributes.get("friendly_name") or state.entity_id
        )
    return out


async def _files_dir(ctx: Ctx, raw: str | None) -> Path | None:
    """The checked ``files_dir`` of a bundle, or None for no bundle.

    The real path is checked again, so a symbolic link cannot point out of the
    directory of the bundles.
    """
    if not raw:
        return None
    config_dir = ctx.hass.config.config_dir
    path = import_export.check_files_dir(raw, config_dir)
    real, real_config = await ctx.hass.async_add_executor_job(
        lambda: (os.path.realpath(path), os.path.realpath(config_dir))
    )
    return Path(import_export.check_files_dir(real, real_config))


async def _export_data(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    files_dir = await _files_dir(ctx, data.get("files_dir"))
    state = models.clone(ctx.store.state)
    cover_files: dict[str, str] = {}
    if files_dir is not None:
        cover_files = await ctx.hass.async_add_executor_job(
            copy_covers_out,
            covers_dir(ctx.hass),
            files_dir,
            import_export.covers_to_copy(state),
        )
    section, skipped = import_export.build_export(
        state,
        person_names=_person_names(ctx.hass),
        area_names=_area_names(ctx.hass),
        entity_names=_todo_names(ctx.hass),
        cover_files=cover_files,
    )
    return {
        "format": import_export.FORMAT,
        "version": PANEL_VERSION,
        "data": projections.project_export(section, is_admin=ctx.actor.is_admin),
        "skipped": skipped,
    }


async def _bundle_covers(
    ctx: Ctx, plan: import_export.ImportPlan, files_dir: Path | None, write: bool
) -> tuple[dict[str, int], list[str]]:
    """Read the cover files of the plan. Return the counts and the old files.

    With *write*, each new cover file is on its game in ``plan.state``, so the
    import writes the covers with the records.
    """
    covers = {"imported": 0, "skipped": 0}
    released: list[str] = []
    for job in plan.covers:
        name = None
        if files_dir is not None:
            name = await async_bundle_cover(
                ctx.hass, files_dir, job.game_id, job.file, write=write
            )
            if name is None:
                plan.problems.append(
                    import_export.Problem(
                        import_export.LEVEL_WARNING,
                        job.path,
                        "import_cover_unreadable",
                        {"file": job.file},
                    )
                )
        covers["skipped" if name is None else "imported"] += 1
        if write and name is not None:
            game = plan.state["games"][job.game_id]
            old = (game.get("cover") or {}).get("file")
            game["cover"] = {"kind": job.kind, "file": name}
            if old:
                released.append(old)
    return covers, released


async def _import_data(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    files_dir = await _files_dir(ctx, data.get("files_dir"))
    dry_run = data.get("dry_run", False)
    snapshot = models.clone(ctx.store.state)
    persons = _person_names(ctx.hass)
    areas = _area_names(ctx.hass)
    todos = _todo_names(ctx.hass)
    stamp = now()
    plan = await ctx.hass.async_add_executor_job(
        lambda: import_export.plan_import(
            snapshot,
            data["document"],
            persons=persons,
            areas=areas,
            todo_entities=todos,
            now=stamp,
        )
    )
    write = plan.ok and not dry_run
    covers, released = await _bundle_covers(ctx, plan, files_dir, write)
    if write:
        # The plan ran on a snapshot. The store merges it into the current
        # data, so a change made while the plan ran stays.
        await ctx.store.commit_data_import(snapshot, plan.state, plan.counts)
        for file in released:
            release_cover(ctx.hass, file)
        # The loan tasks and the to-do items are not imported. The syncs make
        # them again.
        await ctx.coordinator.loan_sync.async_reconcile()
        await ctx.coordinator.wishlist_sync.async_run()
    lang = ctx.hass.config.language
    messages = {
        index: resolve_exception(lang, problem.key, **problem.placeholders)
        for index, problem in enumerate(plan.problems)
    }
    reply = import_export.report(plan, dry_run=dry_run, messages=messages)
    reply["counts"]["covers"] = covers
    return reply


# ── Reads ────────────────────────────────────────────────────────────────────


async def _list_games(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    filters = dict(data)
    if filters.get("status"):
        person_id = filters.get("person_id") or ctx.actor.person_id
        filters["person_id"] = person_id
        shared = models.person_settings(ctx.store.state["people"], str(person_id))
        if (
            not ctx.actor.is_admin
            and person_id != ctx.actor.person_id
            and not shared["share_reading"]
        ):
            return {"games": []}
    return {
        "games": projections.list_games(
            ctx.store.state,
            filters,
            viewer=ctx.actor.person_id,
            is_admin=ctx.actor.is_admin,
        )
    }


async def _get_game(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    detail = projections.game_detail(
        ctx.store.state,
        data["game_id"],
        viewer=ctx.actor.person_id,
        is_admin=ctx.actor.is_admin,
    )
    if detail is None:
        raise LibraryError("game_not_found", id=data["game_id"])
    return {"game": detail}


async def _list_locations(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    state = ctx.store.state
    counts: dict[str | None, int] = {}
    for copy in state["copies"].values():
        counts[copy.get("shelf_id")] = counts.get(copy.get("shelf_id"), 0) + 1
    rooms = []
    for room in sorted(state["rooms"].values(), key=lambda r: (r["order"], r["name"])):
        units = []
        for unit in sorted(
            (b for b in state["units"].values() if b["room_id"] == room["id"]),
            key=lambda b: (b["order"], b["name"]),
        ):
            shelves = [
                {**shelf, "copies": counts.get(shelf["id"], 0)}
                for shelf in sorted(
                    (
                        s
                        for s in state["shelves"].values()
                        if s["unit_id"] == unit["id"]
                    ),
                    key=lambda s: (s["order"], s["name"]),
                )
            ]
            units.append({**unit, "shelves": shelves})
        rooms.append({**room, "units": units})
    return {"rooms": rooms, "no_shelf": counts.get(None, 0)}


async def _list_loans(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    state = ctx.store.state
    wanted = data.get("status", "all")
    out = []
    for loan in sorted(state["loans"].values(), key=lambda lo: lo["started"]):
        is_open = models.is_open(loan)
        if (wanted == "open" and not is_open) or (wanted == "returned" and is_open):
            continue
        if data.get("direction") and loan["direction"] != data["direction"]:
            continue
        row = projections.project_loan(loan, is_admin=ctx.actor.is_admin)
        row["title"] = (state["games"].get(loan["game_id"]) or {}).get("title", "")
        row["overdue"] = models.is_overdue(loan, today())
        out.append(row)
    return {"loans": out}


async def _list_people(ctx: Ctx, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "people": projections.project_people(
            ctx.store.state,
            people.persons(ctx.hass),
            viewer=ctx.actor.person_id,
            is_admin=ctx.actor.is_admin,
        )
    }


SERVICE_HANDLERS: dict[str, Handler] = {
    "add_room": _add_room,
    "update_room": _update_room,
    "delete_room": _delete_room,
    "add_unit": _add_unit,
    "update_unit": _update_unit,
    "delete_unit": _delete_unit,
    "add_shelf": _add_shelf,
    "update_shelf": _update_shelf,
    "delete_shelf": _delete_shelf,
    "add_game": _add_game_service,
    "update_game": _update_game,
    "delete_game": _delete_game,
    "scan_barcode": _scan_barcode,
    "add_copy": _add_copy,
    "update_copy": _update_copy,
    "move_copy": _move_copy,
    "delete_copy": _delete_copy,
    "set_cover": _set_cover,
    "set_reading": _set_reading,
    "lend_game": _lend_game,
    "borrow_game": _borrow_game,
    "return_loan": _return_loan,
    "update_loan": _update_loan,
    "delete_loan": _delete_loan,
    "add_to_wishlist": _add_to_wishlist,
    "update_wishlist": _update_wishlist,
    "remove_from_wishlist": _remove_from_wishlist,
    "got_wishlist_game": _got_wishlist_game,
    "set_person_settings": _set_person_settings,
    "set_settings": _set_settings,
    "import_csv": _import_csv,
    "export_csv": _export_csv,
    "export_data": _export_data,
    "import_data": _import_data,
    "list_games": _list_games,
    "get_game": _get_game,
    "list_locations": _list_locations,
    "list_loans": _list_loans,
    "list_people": _list_people,
}

_RESPONSES = {
    "none": SupportsResponse.NONE,
    "optional": SupportsResponse.OPTIONAL,
    "only": SupportsResponse.ONLY,
}


def coordinator_or_error(hass: HomeAssistant) -> LibraryCoordinator:
    """The loaded coordinator, or the localized ``not_loaded`` error."""
    coordinator = find_coordinator(hass)
    if coordinator is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="not_loaded"
        )
    return coordinator


async def async_run(
    hass: HomeAssistant, spec: ServiceSpec, actor: people.Actor, data: dict[str, Any]
) -> dict[str, Any]:
    """Run 1 operation for *actor*, with the gate of *spec*.

    Raise ``Unauthorized`` for a refused caller, and :class:`LibraryError` for
    input that the library refuses.
    """
    if spec.admin_only and not actor.is_admin:
        raise Unauthorized(context=None)
    coordinator = coordinator_or_error(hass)
    ctx = Ctx(hass, coordinator, actor)
    return await SERVICE_HANDLERS[spec.name](ctx, data)


def _service_handler(
    hass: HomeAssistant, spec: ServiceSpec
) -> Callable[[ServiceCall], Coroutine[Any, Any, ServiceResponse]]:
    async def handle(call: ServiceCall) -> ServiceResponse:
        actor = await people.actor_for_call(hass, call)
        try:
            result = await async_run(hass, spec, actor, dict(call.data))
        except Unauthorized as err:
            raise Unauthorized(context=call.context) from err
        except LibraryError as err:
            raise service_error(err) from err
        return result if call.return_response else None

    return handle


def service_error(err: LibraryError) -> ServiceValidationError:
    """The Home Assistant error for a library error."""
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=err.key,
        translation_placeholders=err.placeholders,
    )


def async_register_services(hass: HomeAssistant) -> None:
    """Register each service of ``api_surface.SERVICES``."""
    for spec in SERVICES:
        hass.services.async_register(
            DOMAIN,
            spec.name,
            _service_handler(hass, spec),
            schema=vol.Schema(SERVICE_FIELDS[spec.name]),
            supports_response=_RESPONSES[spec.response],
        )
