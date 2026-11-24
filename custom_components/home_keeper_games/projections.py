"""Pure read projections: what a caller can read, and the derived counts.

An admin reads the full document. A non-admin reads a projection:

* A copy has no ``price``, ``value`` or ``acquired_from``.
* A loan has no ``party``.
* The reading row of another person shows only if that person shares the
  reading status (``share_reading``), and never with ``private_notes``.
* A person setting of another person has no ``wishlist_todo``.

A reply never leaks: each read surface goes through :func:`project_state` or
:func:`project_game`. The sensors use the stats functions at the end.

This module imports no Home Assistant code.
"""

from __future__ import annotations

from typing import Any

from .const import COVER_URL_PREFIX
from .models import clone, is_open, is_overdue, location_path, person_settings

PRIVATE_COPY_FIELDS = ("price", "value", "acquired_from")
PRIVATE_LOAN_FIELDS = ("party",)
PRIVATE_READING_FIELDS = ("private_notes",)
PRIVATE_PERSON_FIELDS = ("wishlist_todo",)
# The to-do item of a wishlist entry names the ``wishlist_todo`` of its person.
PRIVATE_WISHLIST_FIELDS = ("todo_entity", "todo_uid")


def project_export(data: dict[str, Any], *, is_admin: bool) -> dict[str, Any]:
    """The library section of an export as the viewer reads it.

    ``export_data`` is admin-only, so an admin reads the full section. For a
    non-admin viewer the private fields are gone, as in :func:`project_state`.
    """
    out = {key: clone(value) for key, value in data.items()}
    if is_admin:
        return out
    for copy in out.get("copies", []):
        for name in PRIVATE_COPY_FIELDS:
            copy.pop(name, None)
    for loan in out.get("loans", []):
        for name in PRIVATE_LOAN_FIELDS:
            loan.pop(name, None)
    for entry in out.get("reading", []):
        for row in entry.get("games", []):
            for name in PRIVATE_READING_FIELDS:
                row.pop(name, None)
    for person in out.get("people", []):
        for name in (*PRIVATE_PERSON_FIELDS, "wishlist_todo_name"):
            person.pop(name, None)
    return out


def cover_url(game: dict[str, Any]) -> str | None:
    """The cover path of a game, or None if it has no stored cover file.

    The ``v`` query is the version token in the file name, so a new cover gets a
    new URL and the browser cache does not show the old one.
    """
    cover = game.get("cover") or {}
    file = cover.get("file")
    if cover.get("kind", "none") == "none" or not isinstance(file, str) or not file:
        return None
    token = file.rsplit(".", 1)[0].rsplit("-", 1)[-1]
    return f"{COVER_URL_PREFIX}/{game['id']}?v={token}"


def visible_reading(
    state: dict[str, Any],
    game_id: str,
    *,
    viewer: str | None,
    is_admin: bool,
) -> dict[str, dict[str, Any]]:
    """The reading rows of a game that the viewer can read, by person id."""
    out: dict[str, dict[str, Any]] = {}
    for person_id, rows in state["reading"].items():
        row = rows.get(game_id) if isinstance(rows, dict) else None
        if row is None:
            continue
        if is_admin or person_id == viewer:
            out[person_id] = dict(row)
            continue
        if not person_settings(state["people"], person_id)["share_reading"]:
            continue
        shared = dict(row)
        for field in PRIVATE_READING_FIELDS:
            shared.pop(field, None)
        out[person_id] = shared
    return out


def project_copy(copy: dict[str, Any], *, is_admin: bool) -> dict[str, Any]:
    """A copy as the viewer reads it."""
    out = dict(copy)
    if not is_admin:
        for field in PRIVATE_COPY_FIELDS:
            out.pop(field, None)
    return out


def project_loan(loan: dict[str, Any], *, is_admin: bool) -> dict[str, Any]:
    """A loan as the viewer reads it."""
    out = dict(loan)
    if not is_admin:
        for field in PRIVATE_LOAN_FIELDS:
            out.pop(field, None)
    return out


def project_game(
    state: dict[str, Any],
    game: dict[str, Any],
    *,
    viewer: str | None,
    is_admin: bool,
    copy_count: int | None = None,
) -> dict[str, Any]:
    """A game with its visible ``reading``, ``owned`` and ``cover_url``."""
    out = dict(game)
    if copy_count is None:
        copy_count = sum(
            1 for c in state["copies"].values() if c.get("game_id") == game["id"]
        )
    out["owned"] = copy_count > 0
    out["copy_count"] = copy_count
    out["cover_url"] = cover_url(game)
    out["reading"] = visible_reading(
        state, game["id"], viewer=viewer, is_admin=is_admin
    )
    wishlist = game.get("wishlist")
    if wishlist and not is_admin and wishlist.get("person_id") != viewer:
        out["wishlist"] = {
            k: v for k, v in wishlist.items() if k not in PRIVATE_WISHLIST_FIELDS
        }
    return out


def _sorted(records: dict[str, Any], *keys: str) -> list[dict[str, Any]]:
    def sort_key(record: dict[str, Any]) -> tuple[Any, ...]:
        fields = [str(record.get(k, "")) for k in keys]
        return (*fields, int(record.get("order", 0) or 0), record["id"])

    return sorted((dict(r) for r in records.values()), key=sort_key)


def _by_order(records: dict[str, Any], parent: str | None) -> list[dict[str, Any]]:
    return sorted(
        (dict(r) for r in records.values()),
        key=lambda r: (
            str(r.get(parent, "")) if parent else "",
            int(r.get("order", 0) or 0),
            str(r.get("name", "")).casefold(),
            r["id"],
        ),
    )


def project_people(
    state: dict[str, Any],
    persons: list[dict[str, Any]],
    *,
    viewer: str | None,
    is_admin: bool,
) -> list[dict[str, Any]]:
    """The people of Home Assistant with their library settings.

    *persons* holds ``{person_id, name, entity_id, user_id}`` for each Home
    Assistant person.
    """
    out = []
    for person in persons:
        settings = person_settings(state["people"], person["person_id"])
        row = {
            "person_id": person["person_id"],
            "name": person.get("name", ""),
            "entity_id": person.get("entity_id"),
            **settings,
        }
        if not is_admin and person["person_id"] != viewer:
            for field in PRIVATE_PERSON_FIELDS:
                row.pop(field, None)
        out.append(row)
    return out


def project_state(
    state: dict[str, Any],
    *,
    persons: list[dict[str, Any]],
    viewer: str | None,
    is_admin: bool,
    viewer_name: str | None = None,
    currency: str,
    tab: bool,
    revision: int,
) -> dict[str, Any]:
    """The reply of ``home_keeper_games/get_state`` for the viewer."""
    counts = {game_id: len(rows) for game_id, rows in copies_by_game(state).items()}
    games = [
        project_game(
            state,
            game,
            viewer=viewer,
            is_admin=is_admin,
            copy_count=counts.get(game["id"], 0),
        )
        for game in state["games"].values()
    ]
    games.sort(key=lambda b: (b["title"].casefold(), b["id"]))
    reply: dict[str, Any] = {
        "revision": revision,
        "rooms": _by_order(state["rooms"], None),
        "units": _by_order(state["units"], "room_id"),
        "shelves": _by_order(state["shelves"], "unit_id"),
        "games": games,
        "copies": [
            project_copy(c, is_admin=is_admin)
            for c in _sorted(state["copies"], "game_id", "created_at")
        ],
        "loans": [
            project_loan(loan, is_admin=is_admin)
            for loan in _sorted(state["loans"], "started")
        ],
        "people": {
            row["person_id"]: row
            for row in project_people(state, persons, viewer=viewer, is_admin=is_admin)
        },
        "me": {"person_id": viewer, "name": viewer_name, "is_admin": is_admin},
        "currency": currency,
        "home_keeper": {"tab": tab},
    }
    return reply


def copies_by_game(state: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """The copies of each game, by game id."""
    index: dict[str, list[dict[str, Any]]] = {}
    for copy in state["copies"].values():
        index.setdefault(copy.get("game_id", ""), []).append(copy)
    return index


def game_matches(
    state: dict[str, Any],
    game: dict[str, Any],
    filters: dict[str, Any],
    copies_index: dict[str, list[dict[str, Any]]] | None = None,
) -> bool:
    """Whether a game passes the ``list_games`` filters.

    ``query`` searches the title, the franchise, the genres, the tags and the
    barcodes of the copies. ``shelf_id`` and ``room_id`` match a copy location.
    ``owned`` keeps games with or without copies. ``status`` with ``person_id``
    matches a reading status.
    """
    if copies_index is None:
        copies_index = copies_by_game(state)
    copies = copies_index.get(game["id"], [])
    query = str(filters.get("query") or "").strip().casefold()
    if query:
        parts = [
            game["title"],
            game["franchise"],
            *game["genres"],
            *game["tags"],
            *(c.get("barcode") for c in copies),
        ]
        haystack = " ".join(str(p) for p in parts if p).casefold()
        if query not in haystack:
            return False
    owned = filters.get("owned")
    if owned is not None and bool(copies) != owned:
        return False
    shelf_id = filters.get("shelf_id")
    if shelf_id and not any(c.get("shelf_id") == shelf_id for c in copies):
        return False
    room_id = filters.get("room_id")
    if room_id:
        rooms = set()
        for copy in copies:
            shelf = state["shelves"].get(copy.get("shelf_id") or "") or {}
            unit = state["units"].get(shelf.get("unit_id") or "") or {}
            rooms.add(unit.get("room_id"))
        if room_id not in rooms:
            return False
    status = filters.get("status")
    if status:
        person_id = filters.get("person_id")
        row = (state["reading"].get(person_id) or {}).get(game["id"]) or {}
        if row.get("status") != status:
            return False
    return True


def list_games(
    state: dict[str, Any],
    filters: dict[str, Any],
    *,
    viewer: str | None,
    is_admin: bool,
) -> list[dict[str, Any]]:
    """The projected games that pass *filters*, sorted by title."""
    limit = int(filters.get("limit") or 0)
    index = copies_by_game(state)
    rows = [
        project_game(
            state,
            game,
            viewer=viewer,
            is_admin=is_admin,
            copy_count=len(index.get(game["id"], [])),
        )
        for game in sorted(
            state["games"].values(),
            key=lambda b: (b["title"].casefold(), b["id"]),
        )
        if game_matches(state, game, filters, index)
    ]
    return rows[:limit] if limit > 0 else rows


def game_detail(
    state: dict[str, Any],
    game_id: str,
    *,
    viewer: str | None,
    is_admin: bool,
) -> dict[str, Any] | None:
    """A game with its copies (each with a location path) and its loans."""
    game = state["games"].get(game_id)
    if game is None:
        return None
    out = project_game(state, game, viewer=viewer, is_admin=is_admin)
    copies = []
    for copy in state["copies"].values():
        if copy.get("game_id") != game_id:
            continue
        row = project_copy(copy, is_admin=is_admin)
        row["location"] = location_path(state, copy.get("shelf_id"))
        copies.append(row)
    copies.sort(key=lambda c: (str(c.get("created_at", "")), c["id"]))
    out["copies"] = copies
    out["loans"] = [
        project_loan(loan, is_admin=is_admin)
        for loan in sorted(
            (lo for lo in state["loans"].values() if lo.get("game_id") == game_id),
            key=lambda lo: (str(lo.get("started", "")), lo["id"]),
        )
    ]
    return out


# ── Stats for the sensors ────────────────────────────────────────────────────


def games_read_in_year(state: dict[str, Any], person_id: str, year: int) -> int:
    """The number of games that the person finished in *year*."""
    count = 0
    for row in (state["reading"].get(person_id) or {}).values():
        finished = row.get("finished")
        if row.get("status") != "read" or not isinstance(finished, str):
            continue
        if not finished.startswith(f"{year:04d}-"):
            continue
        count += 1
    return count


def reading_now(state: dict[str, Any], person_id: str) -> list[str]:
    """The titles that the person reads now, sorted by the last change."""
    rows = [
        (row.get("updated_at") or "", game_id)
        for game_id, row in (state["reading"].get(person_id) or {}).items()
        if row.get("status") == "reading" and game_id in state["games"]
    ]
    rows.sort(reverse=True)
    return [str(state["games"][game_id].get("title", "")) for _, game_id in rows]


def want_to_read(state: dict[str, Any], person_id: str) -> list[dict[str, Any]]:
    """The games with status ``want`` for the person, oldest first."""
    rows = [
        (row.get("updated_at") or "", game_id)
        for game_id, row in (state["reading"].get(person_id) or {}).items()
        if row.get("status") == "want" and game_id in state["games"]
    ]
    rows.sort()
    return [state["games"][game_id] for _, game_id in rows]


def owned_game_count(state: dict[str, Any]) -> int:
    """The number of games with 1 copy or more."""
    return len({c.get("game_id") for c in state["copies"].values()})


def loans_out_count(state: dict[str, Any]) -> int:
    """The number of open loans that lend a copy out."""
    return sum(
        1
        for loan in state["loans"].values()
        if loan.get("direction") == "out" and is_open(loan)
    )


def loans_overdue_count(state: dict[str, Any], today: str) -> int:
    """The number of open loans with a due date before *today*."""
    return sum(1 for loan in state["loans"].values() if is_overdue(loan, today))
