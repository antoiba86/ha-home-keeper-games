"""Pure data model of the library: normalize and build the stored records.

The store holds one JSON document with these sections, each a map by id::

    rooms, units, shelves, games, copies, loans
    reading:  {person_id: {game_id: row}}
    people:   {person_id: settings}
    todo_orphans: [{entity_id, uid}]

A record is a plain dict. The functions here check caller input and return new
dicts. They never change their arguments, and they never read a clock: the caller
passes ``now`` (an aware ISO 8601 timestamp) and ``today`` (a ``YYYY-MM-DD``
date). A bad value raises :class:`LibraryError` with a translation key from
``strings.json`` ``exceptions``. The service layer turns it into a localized error.

This module imports no Home Assistant code.
"""

from __future__ import annotations

import copy as _copy
import math
import re
import unicodedata
import uuid
from datetime import date
from typing import Any

STATE_SECTIONS = (
    "rooms",
    "units",
    "shelves",
    "games",
    "copies",
    "reading",
    "loans",
    "people",
)

FORMATS = ("physical", "digital", "other")
DEFAULT_FORMAT = "physical"
# The consoles of a copy. ``other`` is any platform that is not in the list.
PLATFORMS = (
    "ps5",
    "ps4",
    "ps3",
    "switch2",
    "switch",
    "xbox_series",
    "xbox_one",
    "pc",
    "other",
)
DEFAULT_PLATFORM = "other"
CONDITIONS = ("new", "fine", "good", "fair", "poor")
STATUSES = ("want", "reading", "read", "dnf")
# The ``status`` value of ``set_reading`` that removes the reading row.
STATUS_NONE = "none"
DIRECTIONS = ("out", "in")
COVER_KINDS = ("custom", "none")
# A barcode: letters and digits, with no spaces or hyphens.
MAX_BARCODE = 50
_BARCODE_RE = re.compile(rf"[0-9A-Z]{{1,{MAX_BARCODE}}}")

MAX_NAME = 100
MAX_TITLE = 500
MAX_SHORT = 200
MAX_NOTE = 2000
MAX_LONG = 20000
MAX_LIST = 50
MAX_ORDER = 1_000_000
MAX_PAGES = 100_000
MAX_READ_COUNT = 1000
MAX_GOAL = 10_000
MAX_MONEY = 1_000_000_000

# The game fields that a caller sets. ``wishlist``, ``cover`` and the time stamps
# have their own paths.
GAME_TEXT_FIELDS = {
    "title": MAX_TITLE,
    "summary": MAX_LONG,
    "release_date": 50,
    "shared_notes": MAX_LONG,
}
GAME_FIELDS = (
    "title",
    "summary",
    "genres",
    "release_date",
    "franchise",
    "igdb_id",
    "tags",
    "shared_notes",
    "needs_details",
)
# The largest IGDB game id that the integration takes.
MAX_IGDB_ID = 2**53
COPY_FIELDS = (
    "shelf_id",
    "platform",
    "format",
    "storefront",
    "region",
    "edition",
    "steelbook",
    "barcode",
    "condition",
    "acquired",
    "acquired_from",
    "price",
    "value",
    "note",
)
READING_FIELDS = (
    "status",
    "rating",
    "page",
    "started",
    "finished",
    "read_count",
    "private_notes",
)
LOAN_UPDATE_FIELDS = ("party", "due", "note", "started", "format")
PERSON_FIELDS = ("share_reading", "wishlist_todo", "yearly_goal")


class LibraryError(ValueError):
    """Input that the library refuses.

    ``key`` is a key in ``strings.json`` ``exceptions``, and ``placeholders``
    fill its message.
    """

    def __init__(self, key: str, **placeholders: Any) -> None:
        super().__init__(key)
        self.key = key
        self.placeholders = {name: str(value) for name, value in placeholders.items()}


def new_id() -> str:
    """A new record id: a uuid4 hex string."""
    return uuid.uuid4().hex


def empty_state() -> dict[str, Any]:
    """The document of a new library."""
    state: dict[str, Any] = {name: {} for name in STATE_SECTIONS}
    state["todo_orphans"] = []
    return state


def normalize_state(raw: Any) -> dict[str, Any]:
    """Return a document with every section, from a stored or a missing one.

    A section that is absent or has the wrong type becomes empty. This is also the
    place for a storage migration: the store calls it on every load.
    """
    state = empty_state()
    if not isinstance(raw, dict):
        return state
    for name in STATE_SECTIONS:
        value = raw.get(name)
        if isinstance(value, dict):
            state[name] = value
    orphans = raw.get("todo_orphans")
    if isinstance(orphans, list):
        state["todo_orphans"] = [
            entry
            for entry in orphans
            if isinstance(entry, dict)
            and isinstance(entry.get("entity_id"), str)
            and isinstance(entry.get("uid"), str)
        ]
    return state


def clone(value: Any) -> Any:
    """A deep copy of a JSON value."""
    return _copy.deepcopy(value)


# The sections that hold 1 record for each id. ``reading`` holds 1 map of rows
# for each person.
RECORD_SECTIONS = tuple(name for name in STATE_SECTIONS if name != "reading")


def _merge_records(
    target: dict[str, Any], before: dict[str, Any], after: dict[str, Any]
) -> list[str]:
    """Write the change from *before* to *after* into *target*, record by record.

    A new record is added. For a changed record, only the fields that changed
    are written, so a concurrent change of another field stays. A record that
    *target* no longer has stays deleted. Return the ids that were written.
    """
    written: list[str] = []
    for key, record in after.items():
        old = before.get(key)
        if old is None:
            if key not in target:
                target[key] = clone(record)
                written.append(key)
            continue
        if record == old or key not in target:
            continue
        current = dict(target[key])
        for field in [*record, *(f for f in old if f not in record)]:
            if field not in record:
                current.pop(field, None)
            elif field not in old or record[field] != old[field]:
                current[field] = clone(record[field])
        target[key] = current
        written.append(key)
    for key in before:
        if key not in after:
            target.pop(key, None)
    return written


def merge_changes(
    current: dict[str, Any], before: dict[str, Any], after: dict[str, Any]
) -> dict[str, Any]:
    """Return *current* with the changes that turned *before* into *after*.

    An import plans its changes on a snapshot (*before*) while other changes
    can go on. This merge writes only the records and the fields that the plan
    changed, so a change made in the meantime stays. A copy or a reading row of
    the plan whose game was deleted in the meantime is dropped, and a copy on a
    deleted shelf goes to no shelf. *current* does not change.
    """
    merged = clone(current)
    written = {
        name: _merge_records(merged[name], before[name], after[name])
        for name in RECORD_SECTIONS
    }
    rows_written: list[tuple[str, str]] = []
    for person_id in sorted(set(before["reading"]) | set(after["reading"])):
        rows = merged["reading"].setdefault(person_id, {})
        for game_id in _merge_records(
            rows,
            before["reading"].get(person_id, {}),
            after["reading"].get(person_id, {}),
        ):
            rows_written.append((person_id, game_id))
    for copy_id in written["copies"]:
        copy = merged["copies"][copy_id]
        if copy.get("game_id") not in merged["games"]:
            del merged["copies"][copy_id]
        elif copy.get("shelf_id") not in merged["shelves"]:
            copy["shelf_id"] = None
    for person_id, game_id in rows_written:
        if game_id not in merged["games"]:
            del merged["reading"][person_id][game_id]
    merged["reading"] = {p: r for p, r in merged["reading"].items() if r}
    return merged


# ── Field checks ─────────────────────────────────────────────────────────────


def text(value: Any, field: str, max_len: int, *, required: bool = False) -> str:
    """A trimmed string of at most *max_len* characters."""
    if value is None:
        value = ""
    if isinstance(value, int | float) and not isinstance(value, bool):
        value = str(value)
    if not isinstance(value, str):
        raise LibraryError("invalid_field", field=field)
    value = value.strip()
    if required and not value:
        raise LibraryError("field_required", field=field)
    if len(value) > max_len:
        raise LibraryError("field_too_long", field=field, max=max_len)
    return value


def optional_text(value: Any, field: str, max_len: int) -> str | None:
    """Like :func:`text`, but an empty value is None."""
    result = text(value, field, max_len)
    return result or None


def str_list(value: Any, field: str, *, max_len: int = MAX_SHORT) -> list[str]:
    """A list of distinct, trimmed, non-empty strings, in input order."""
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list | tuple):
        raise LibraryError("invalid_field", field=field)
    out: list[str] = []
    for item in value:
        entry = text(item, field, max_len)
        if entry and entry not in out:
            out.append(entry)
    if len(out) > MAX_LIST:
        raise LibraryError("field_too_long", field=field, max=MAX_LIST)
    return out


def boolean(value: Any, field: str) -> bool:
    """A bool. Strings and numbers are refused."""
    if not isinstance(value, bool):
        raise LibraryError("invalid_field", field=field)
    return value


def integer(
    value: Any, field: str, *, low: int, high: int, nullable: bool = True
) -> int | None:
    """An int from *low* to *high*, or None if *nullable* and the value is None."""
    if value is None or value == "":
        if nullable:
            return None
        raise LibraryError("field_required", field=field)
    if isinstance(value, bool):
        raise LibraryError("invalid_field", field=field)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value.strip()):
        value = int(value.strip())
    if not isinstance(value, int):
        raise LibraryError("invalid_field", field=field)
    if not low <= value <= high:
        raise LibraryError("out_of_range", field=field, low=low, high=high)
    return value


def money(value: Any, field: str) -> float | int | None:
    """A number from 0 up, or None. A whole value stays an int."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise LibraryError("invalid_field", field=field)
    if isinstance(value, str):
        try:
            value = float(value.strip())
        except ValueError as err:
            raise LibraryError("invalid_field", field=field) from err
    if not isinstance(value, int | float) or not math.isfinite(value):
        raise LibraryError("invalid_field", field=field)
    if not 0 <= value <= MAX_MONEY:
        raise LibraryError("out_of_range", field=field, low=0, high=MAX_MONEY)
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def iso_date(value: Any, field: str) -> str | None:
    """A ``YYYY-MM-DD`` string from a date or a string, or None."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value.isoformat()[:10]
    if isinstance(value, str):
        candidate = value.strip()[:10]
        try:
            return date.fromisoformat(candidate).isoformat()
        except ValueError as err:
            raise LibraryError("invalid_date", field=field) from err
    raise LibraryError("invalid_date", field=field)


def choice(value: Any, field: str, options: tuple[str, ...]) -> str:
    """One of *options*."""
    if value not in options:
        raise LibraryError("invalid_choice", field=field, options=", ".join(options))
    return str(value)


def entity_id_or_none(value: Any, field: str, domain: str) -> str | None:
    """A ``<domain>.<object_id>`` entity id, or None."""
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not re.fullmatch(
        rf"{re.escape(domain)}\.[a-z0-9_]+", value
    ):
        raise LibraryError("invalid_field", field=field)
    return value


# ── Locations ────────────────────────────────────────────────────────────────


def build_room(data: dict[str, Any], *, order: int) -> dict[str, Any]:
    """A new room."""
    return {
        "id": new_id(),
        "name": text(data.get("name"), "name", MAX_NAME, required=True),
        "area_id": optional_text(data.get("area_id"), "area_id", MAX_SHORT),
        "order": _order(data.get("order", order)),
    }


def build_unit(data: dict[str, Any], *, order: int) -> dict[str, Any]:
    """A new unit. The caller checks that ``room_id`` exists."""
    return {
        "id": new_id(),
        "room_id": text(data.get("room_id"), "room_id", MAX_SHORT, required=True),
        "name": text(data.get("name"), "name", MAX_NAME, required=True),
        "note": text(data.get("note"), "note", MAX_NOTE),
        "order": _order(data.get("order", order)),
    }


def build_shelf(data: dict[str, Any], *, order: int) -> dict[str, Any]:
    """A new shelf. The caller checks that ``unit_id`` exists."""
    return {
        "id": new_id(),
        "unit_id": text(data.get("unit_id"), "unit_id", MAX_SHORT, required=True),
        "name": text(data.get("name"), "name", MAX_NAME, required=True),
        "order": _order(data.get("order", order)),
    }


def _order(value: Any) -> int:
    result = integer(value, "order", low=0, high=MAX_ORDER, nullable=False)
    assert result is not None
    return result


_LOCATION_RULES: dict[str, dict[str, Any]] = {
    "room": {"name": ("name",), "area_id": ("area_id",), "order": ("order",)},
    "unit": {
        "name": ("name",),
        "note": ("note",),
        "order": ("order",),
        "room_id": ("room_id",),
    },
    "shelf": {"name": ("name",), "order": ("order",), "unit_id": ("unit_id",)},
}


def update_location(
    kind: str, record: dict[str, Any], data: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Return ``(updated, changed_fields)`` for a room, a unit or a shelf."""
    updated = dict(record)
    changed: list[str] = []
    for field in _LOCATION_RULES[kind]:
        if field not in data:
            continue
        raw = data[field]
        if field == "name":
            value: Any = text(raw, field, MAX_NAME, required=True)
        elif field == "order":
            value = _order(raw)
        elif field == "note":
            value = text(raw, field, MAX_NOTE)
        elif field == "area_id":
            value = optional_text(raw, field, MAX_SHORT)
        else:
            value = text(raw, field, MAX_SHORT, required=True)
        if value != updated.get(field):
            updated[field] = value
            changed.append(field)
    return updated, changed


def next_order(records: dict[str, dict[str, Any]], **match: Any) -> int:
    """The order after the last record whose fields equal *match*."""
    orders = [
        int(record.get("order", 0))
        for record in records.values()
        if all(record.get(key) == value for key, value in match.items())
    ]
    return max(orders) + 1 if orders else 0


# ── Games ────────────────────────────────────────────────────────────────────


def clean_barcode(value: Any) -> str:
    """A barcode without spaces and hyphens, in capital letters."""
    return re.sub(r"[\s-]", "", str(value)).upper()


def barcode(value: Any, field: str = "barcode") -> str | None:
    """A checked barcode, or None for an empty value."""
    if value is None or value == "":
        return None
    if not isinstance(value, str | int) or isinstance(value, bool):
        raise LibraryError("invalid_field", field=field)
    cleaned = clean_barcode(value)
    if not _BARCODE_RE.fullmatch(cleaned):
        raise LibraryError("invalid_barcode", barcode=cleaned[:MAX_BARCODE])
    return cleaned


def game_field(field: str, value: Any) -> Any:
    """Check one caller-set game field and return its stored value."""
    if field in GAME_TEXT_FIELDS:
        return text(value, field, GAME_TEXT_FIELDS[field], required=field == "title")
    if field in ("genres", "tags"):
        return str_list(value, field)
    if field == "franchise":
        return optional_text(value, field, MAX_SHORT) or None
    if field == "igdb_id":
        return integer(value, field, low=1, high=MAX_IGDB_ID)
    if field == "needs_details":
        return boolean(value, field)
    raise LibraryError("invalid_field", field=field)


def build_game(data: dict[str, Any], *, now: str) -> dict[str, Any]:
    """A new game from caller input."""
    game: dict[str, Any] = {
        "id": new_id(),
        "title": "",
        "summary": "",
        "genres": [],
        "release_date": "",
        "franchise": None,
        "igdb_id": None,
        "tags": [],
        "shared_notes": "",
        "cover": {"kind": "none", "file": None},
        "needs_details": False,
        "created_at": now,
        "updated_at": now,
        "wishlist": None,
    }
    for field in GAME_FIELDS:
        if field in data:
            game[field] = game_field(field, data[field])
    if not game["title"]:
        raise LibraryError("field_required", field="title")
    return game


def update_game(
    game: dict[str, Any], data: dict[str, Any], *, now: str
) -> tuple[dict[str, Any], list[str]]:
    """Return ``(updated, changed_fields)``. ``updated_at`` moves on a change."""
    updated = dict(game)
    changed: list[str] = []
    patch = {field: data[field] for field in GAME_FIELDS if field in data}
    for field, raw in patch.items():
        value = game_field(field, raw)
        if value != updated.get(field):
            updated[field] = value
            changed.append(field)
    if changed:
        updated["updated_at"] = now
    return updated, changed


def fold(value: Any) -> str:
    """A key for loose text comparison: no accents, case or punctuation."""
    if not isinstance(value, str):
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    words = re.findall(r"[^\W_]+", plain.casefold())
    return " ".join(words)


def title_key(title: Any) -> str:
    """The match key of a title: no accents, case or punctuation.

    The whole title counts, because the part after ``:`` often names a different
    game of 1 franchise.
    """
    return fold(title)


# ── Copies ───────────────────────────────────────────────────────────────────


def copy_field(field: str, value: Any) -> Any:
    """Check one caller-set copy field and return its stored value."""
    if field == "shelf_id":
        return optional_text(value, field, MAX_SHORT)
    if field == "platform":
        return choice(value, field, PLATFORMS)
    if field == "format":
        return choice(value, field, FORMATS)
    if field in ("storefront", "edition"):
        return text(value, field, MAX_SHORT)
    if field == "region":
        return text(value, field, 20)
    if field == "steelbook":
        return boolean(value, field)
    if field == "barcode":
        return barcode(value)
    if field == "condition":
        return None if value in (None, "") else choice(value, field, CONDITIONS)
    if field == "acquired":
        return iso_date(value, field)
    if field == "acquired_from":
        return text(value, field, MAX_SHORT)
    if field in ("price", "value"):
        return money(value, field)
    if field == "note":
        return text(value, field, MAX_NOTE)
    raise LibraryError("invalid_field", field=field)


def build_copy(data: dict[str, Any], *, now: str) -> dict[str, Any]:
    """A new copy. The caller checks that the game and the shelf exist.

    A digital copy is on no shelf.
    """
    record: dict[str, Any] = {
        "id": new_id(),
        "game_id": text(data.get("game_id"), "game_id", MAX_SHORT, required=True),
        "shelf_id": None,
        "platform": DEFAULT_PLATFORM,
        "format": DEFAULT_FORMAT,
        "storefront": "",
        "region": "",
        "edition": "",
        "steelbook": False,
        "barcode": None,
        "condition": None,
        "acquired": None,
        "acquired_from": "",
        "price": None,
        "value": None,
        "note": "",
        "created_at": now,
    }
    for field in COPY_FIELDS:
        if field in data:
            record[field] = copy_field(field, data[field])
    if record["format"] == "digital":
        record["shelf_id"] = None
    return record


def update_copy(
    record: dict[str, Any], data: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Return ``(updated, changed_fields)`` for a copy.

    A digital copy leaves its shelf.
    """
    updated = dict(record)
    changed: list[str] = []
    for field in COPY_FIELDS:
        if field not in data:
            continue
        value = copy_field(field, data[field])
        if value != updated.get(field):
            updated[field] = value
            changed.append(field)
    if updated.get("format") == "digital":
        updated["shelf_id"] = None
        changed = [f for f in changed if f != "shelf_id"]
        if record.get("shelf_id") is not None:
            changed.append("shelf_id")
    return updated, changed


# ── Reading ──────────────────────────────────────────────────────────────────


def empty_reading(*, now: str) -> dict[str, Any]:
    """A reading row with status ``want``."""
    return {
        "status": "want",
        "rating": None,
        "page": None,
        "started": None,
        "finished": None,
        "read_count": 0,
        "private_notes": "",
        "updated_at": now,
    }


def reading_field(field: str, value: Any) -> Any:
    """Check one reading field and return its stored value."""
    if field == "status":
        return choice(value, field, STATUSES)
    if field == "rating":
        return integer(value, field, low=1, high=5)
    if field == "page":
        return integer(value, field, low=0, high=MAX_PAGES)
    if field in ("started", "finished"):
        return iso_date(value, field)
    if field == "read_count":
        return integer(value, field, low=0, high=MAX_READ_COUNT, nullable=False)
    if field == "private_notes":
        return text(value, field, MAX_LONG)
    raise LibraryError("invalid_field", field=field)


def apply_reading(
    row: dict[str, Any] | None, data: dict[str, Any], *, now: str, today: str
) -> tuple[dict[str, Any], list[str]]:
    """Return ``(row, changed_fields)`` after a ``set_reading`` call.

    When the status becomes ``read``, ``finished`` is today and ``read_count``
    goes up by 1, unless the call sends those fields. When the status becomes
    ``reading``, ``started`` is today unless the call sends it.
    """
    base = dict(row) if row else empty_reading(now=now)
    previous = row.get("status") if row else None
    updated = dict(base)
    for field in READING_FIELDS:
        if field in data:
            updated[field] = reading_field(field, data[field])
    status = updated["status"]
    if status != previous:
        if status == "read":
            if "finished" not in data:
                updated["finished"] = today
            if "read_count" not in data:
                updated["read_count"] = int(base.get("read_count") or 0) + 1
        elif status == "reading" and "started" not in data:
            updated["started"] = today
    changed = [
        field for field in READING_FIELDS if updated.get(field) != base.get(field)
    ]
    if row is None and "status" not in changed:
        changed.insert(0, "status")
    if changed:
        updated["updated_at"] = now
    return updated, changed


# ── Loans ────────────────────────────────────────────────────────────────────


def build_loan(data: dict[str, Any], *, today: str) -> dict[str, Any]:
    """A new loan. The caller checks the game, the copy and the person."""
    direction = choice(data.get("direction"), "direction", DIRECTIONS)
    started = iso_date(data.get("started"), "started") or today
    due = iso_date(data.get("due"), "due")
    if due is not None and due < started:
        raise LibraryError("due_before_start")
    copy_id = optional_text(data.get("copy_id"), "copy_id", MAX_SHORT)
    person_id = optional_text(data.get("person_id"), "person_id", MAX_SHORT)
    if direction == "out" and copy_id is None:
        raise LibraryError("field_required", field="copy_id")
    if direction == "in":
        copy_id = None
        if person_id is None:
            raise LibraryError("field_required", field="person_id")
    fmt = data.get("format")
    return {
        "id": new_id(),
        "direction": direction,
        "game_id": text(data.get("game_id"), "game_id", MAX_SHORT, required=True),
        "copy_id": copy_id,
        "party": text(data.get("party"), "party", MAX_SHORT, required=True),
        "person_id": person_id,
        "format": None if fmt in (None, "") else choice(fmt, "format", FORMATS),
        "started": started,
        "due": due,
        "returned": None,
        "note": text(data.get("note"), "note", MAX_NOTE),
        "hk_task_id": None,
        "add_task": bool(data.get("add_task", True)),
        "overdue_fired": False,
    }


def update_loan(
    loan: dict[str, Any], data: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Return ``(updated, changed_fields)``. A new due date can fire again."""
    updated = dict(loan)
    changed: list[str] = []
    for field in LOAN_UPDATE_FIELDS:
        if field not in data:
            continue
        raw = data[field]
        if field == "party":
            value: Any = text(raw, field, MAX_SHORT, required=True)
        elif field == "note":
            value = text(raw, field, MAX_NOTE)
        elif field == "format":
            value = None if raw in (None, "") else choice(raw, field, FORMATS)
        elif field == "started":
            value = iso_date(raw, field) or loan["started"]
        else:
            value = iso_date(raw, field)
        if value != updated.get(field):
            updated[field] = value
            changed.append(field)
    if updated.get("due") is not None and updated["due"] < updated["started"]:
        raise LibraryError("due_before_start")
    if "due" in changed:
        updated["overdue_fired"] = False
    return updated, changed


def is_open(loan: dict[str, Any]) -> bool:
    """Whether the loan is not returned."""
    return loan.get("returned") is None


def is_overdue(loan: dict[str, Any], today: str) -> bool:
    """Whether the loan is open and its due date is before *today*."""
    due = loan.get("due")
    return is_open(loan) and isinstance(due, str) and due < today


# ── People ───────────────────────────────────────────────────────────────────


def default_person() -> dict[str, Any]:
    """The settings of a person with no stored settings."""
    return {"share_reading": True, "wishlist_todo": None, "yearly_goal": None}


def person_settings(people: dict[str, Any], person_id: str) -> dict[str, Any]:
    """The settings of *person_id*, with the defaults for a missing key."""
    stored = people.get(person_id)
    settings = default_person()
    if isinstance(stored, dict):
        settings.update({k: stored[k] for k in PERSON_FIELDS if k in stored})
    return settings


def apply_person_settings(
    settings: dict[str, Any], data: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Return ``(settings, changed_fields)``."""
    updated = dict(settings)
    for field in PERSON_FIELDS:
        if field not in data:
            continue
        raw = data[field]
        if field == "share_reading":
            updated[field] = boolean(raw, field)
        elif field == "wishlist_todo":
            updated[field] = entity_id_or_none(raw, field, "todo")
        else:
            updated[field] = integer(raw, field, low=1, high=MAX_GOAL)
    changed = [f for f in PERSON_FIELDS if updated.get(f) != settings.get(f)]
    return updated, changed


# ── Wishlist ─────────────────────────────────────────────────────────────────


def build_wishlist(person_id: str, *, buy: bool, now: str) -> dict[str, Any]:
    """A new wishlist entry on a game."""
    return {
        "person_id": text(person_id, "person_id", MAX_SHORT, required=True),
        "buy": boolean(buy, "buy"),
        "added_at": now,
        "todo_uid": None,
        "todo_entity": None,
        "bought": False,
    }


# ── Derived reads ────────────────────────────────────────────────────────────


def copies_of(state: dict[str, Any], game_id: str) -> list[dict[str, Any]]:
    """The copies of a game, oldest first."""
    rows = [c for c in state["copies"].values() if c.get("game_id") == game_id]
    return sorted(rows, key=lambda c: (str(c.get("created_at", "")), c["id"]))


def copy_clears_wishlist(state: dict[str, Any], game_id: str) -> bool:
    """Whether a new copy of a game takes the game off the wishlist.

    It does when the game has a wishlist entry and no copy yet: the first copy
    is the game that the person wanted.
    """
    game = state["games"].get(game_id)
    if not game or not game.get("wishlist"):
        return False
    return not any(c.get("game_id") == game_id for c in state["copies"].values())


def open_loan_of_copy(state: dict[str, Any], copy_id: str) -> dict[str, Any] | None:
    """The open ``out`` loan of a copy, if one exists."""
    for loan in state["loans"].values():
        if loan.get("copy_id") == copy_id and is_open(loan):
            return loan
    return None


def location_path(state: dict[str, Any], shelf_id: str | None) -> list[str]:
    """``[room, unit, shelf]`` names for a shelf, or ``[]``."""
    shelf = state["shelves"].get(shelf_id) if shelf_id else None
    if shelf is None:
        return []
    unit = state["units"].get(shelf.get("unit_id")) or {}
    room = state["rooms"].get(unit.get("room_id")) or {}
    return [
        str(room.get("name", "")),
        str(unit.get("name", "")),
        str(shelf.get("name", "")),
    ]


def find_shelf_by_path(state: dict[str, Any], path: list[str]) -> str | None:
    """The id of the shelf whose room, unit and shelf names fold to *path*."""
    if len(path) != 3:
        return None
    wanted = [fold(part) for part in path]
    for shelf_id in state["shelves"]:
        if [fold(part) for part in location_path(state, shelf_id)] == wanted:
            return shelf_id
    return None


def find_game_by_barcode(
    state: dict[str, Any], code: str | None
) -> dict[str, Any] | None:
    """The game of the oldest copy with this barcode, or None."""
    if not code:
        return None
    copies = sorted(
        (c for c in state["copies"].values() if c.get("barcode") == code),
        key=lambda c: (str(c.get("created_at", "")), c["id"]),
    )
    for copy in copies:
        game = state["games"].get(copy.get("game_id"))
        if game is not None:
            return game
    return None


__all__ = [
    "CONDITIONS",
    "COPY_FIELDS",
    "COVER_KINDS",
    "DIRECTIONS",
    "FORMATS",
    "GAME_FIELDS",
    "PLATFORMS",
    "STATUSES",
    "STATUS_NONE",
    "LibraryError",
    "apply_person_settings",
    "apply_reading",
    "build_copy",
    "build_game",
    "build_loan",
    "build_room",
    "build_shelf",
    "build_unit",
    "build_wishlist",
    "empty_state",
    "normalize_state",
    "update_copy",
    "update_game",
    "update_loan",
    "update_location",
]
