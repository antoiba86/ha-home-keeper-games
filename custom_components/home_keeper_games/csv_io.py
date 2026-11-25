"""Pure CSV import and export in the format of the integration.

Import has 2 steps:

1. ``parse(text)`` reads the CSV text into *import rows*: plain dicts with the
   keys of :func:`empty_row`.
2. ``apply_import(state, rows, ...)`` returns a new document, a summary and a
   result for each row. It changes no argument, so a dry run is the same call
   with the result thrown away.

Export writes every game and copy field. The ``platform`` column is the
platform of the copy and of the progress on the row. ``rows_from_state`` makes
the rows, and ``write(rows)`` writes them, so ``parse(write(rows))`` gives the
rows back (a property test checks this).

This module imports no Home Assistant code.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date
from typing import Any

from .models import (
    COPY_FIELDS,
    DEFAULT_PLATFORM,
    FORMATS,
    PLATFORMS,
    PLAY_STATUSES,
    LibraryError,
    build_copy,
    build_game,
    build_wishlist,
    clean_barcode,
    clone,
    copy_field,
    empty_progress,
    find_shelf_by_path,
    location_path,
    title_key,
)

LIBRARY_COLUMNS = (
    "game_id",
    "title",
    "summary",
    "genres",
    "release_date",
    "franchise",
    "igdb_id",
    "tags",
    "shared_notes",
    "copy_id",
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
    "copy_note",
    "location",
    "play_status",
    "rating",
    "playtime_minutes",
    "started_at",
    "completed_at",
    "last_played_at",
    "completion_count",
    "review",
    "wishlist",
    "wishlist_buy",
)
# The separator of a list in a library CSV cell, and of a location path.
LIST_SEP = "; "
PATH_SEP = " / "

# The copy fields of a library row, and their CSV column.
_COPY_COLUMNS = {
    "platform": "platform",
    "format": "format",
    "storefront": "storefront",
    "region": "region",
    "edition": "edition",
    "steelbook": "steelbook",
    "condition": "condition",
    "acquired": "acquired",
    "acquired_from": "acquired_from",
    "price": "price",
    "value": "value",
    "note": "copy_note",
}


def empty_row(line: int) -> dict[str, Any]:
    """An import row with every key."""
    return {
        "line": line,
        "game_id": None,
        "title": "",
        "summary": "",
        "genres": [],
        "release_date": "",
        "franchise": None,
        "igdb_id": None,
        "barcode": None,
        "tags": [],
        "shared_notes": "",
        "owned": 0,
        "copy": None,
        "location": [],
        "platform": None,
        "play_status": None,
        "wishlist": False,
        "wishlist_buy": False,
        "rating": None,
        "playtime_minutes": None,
        "started_at": None,
        "completed_at": None,
        "last_played_at": None,
        "completion_count": None,
        "review": "",
        "needs_details": True,
    }


# ── Cell readers ─────────────────────────────────────────────────────────────


def _cell(row: dict[str, Any], name: str) -> str:
    value = row.get(name)
    return value.strip() if isinstance(value, str) else ""


def _int(value: str) -> int | None:
    value = value.strip()
    if re.fullmatch(r"\d+", value):
        return int(value)
    return None


def _float(value: str) -> float | None:
    try:
        number = float(value.strip())
    except ValueError:
        return None
    return number if number == number and abs(number) != float("inf") else None


def _date(value: str) -> str | None:
    """``YYYY/MM/DD`` or ``YYYY-MM-DD`` to ``YYYY-MM-DD``."""
    value = value.strip().replace("/", "-")
    match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", value)
    if not match:
        return None
    try:
        return date(
            int(match.group(1)), int(match.group(2)), int(match.group(3))
        ).isoformat()
    except ValueError:
        return None


def _split(value: str, sep: str = ",") -> list[str]:
    out: list[str] = []
    for part in value.split(sep):
        part = part.strip()
        if part and part not in out:
            out.append(part)
    return out


def _rating(value: str) -> int | None:
    number = _float(value)
    if number is None or number <= 0:
        return None
    return max(1, min(5, int(number + 0.5)))


def _reader(text: str) -> csv.DictReader[str]:
    if text.startswith("﻿"):
        text = text[1:]
    return csv.DictReader(io.StringIO(text, newline=""))


def _rows(text: str, required: str) -> list[dict[str, Any]]:
    try:
        reader = _reader(text)
        fields = reader.fieldnames or []
        if required not in fields:
            raise LibraryError("csv_unreadable", column=required)
        return list(reader)
    except csv.Error as err:
        raise LibraryError("csv_unreadable", column=required) from err


# ── Parsers ──────────────────────────────────────────────────────────────────


_RECORD_ID_RE = re.compile(r"[0-9a-f]{32}")


def _bool_cell(value: str) -> bool:
    return value.strip().casefold() in ("true", "yes", "1")


def _record_id(value: str) -> str | None:
    """*value* if it has the form of a record id (:func:`models.new_id`), else None.

    A cover file name starts with the game id, so an id from a file must not
    hold a path.
    """
    return value if _RECORD_ID_RE.fullmatch(value) else None


def parse_library(text: str) -> list[dict[str, Any]]:
    """Import rows from a library export: 1 row for each copy."""
    rows = []
    for index, raw in enumerate(_rows(text, "title"), start=1):
        row = empty_row(index)
        row["game_id"] = _record_id(_cell(raw, "game_id"))
        for field in ("title", "summary", "release_date", "shared_notes"):
            row[field] = _cell(raw, field)
        row["genres"] = _split(_cell(raw, "genres"), LIST_SEP.strip())
        row["tags"] = _split(_cell(raw, "tags"), LIST_SEP.strip())
        row["franchise"] = _cell(raw, "franchise") or None
        row["igdb_id"] = _int(_cell(raw, "igdb_id")) or None
        row["barcode"] = clean_barcode(_cell(raw, "barcode")) or None
        platform = _cell(raw, "platform")
        row["platform"] = platform if platform in PLATFORMS else None
        fmt = _cell(raw, "format")
        if fmt in FORMATS:
            copy: dict[str, Any] = {"id": _record_id(_cell(raw, "copy_id"))}
            copy["format"] = fmt
            copy["platform"] = platform or None
            for field in ("storefront", "region", "edition"):
                copy[field] = _cell(raw, field)
            copy["steelbook"] = _bool_cell(_cell(raw, "steelbook"))
            copy["condition"] = _cell(raw, "condition") or None
            copy["acquired"] = _date(_cell(raw, "acquired"))
            copy["acquired_from"] = _cell(raw, "acquired_from")
            copy["price"] = _money_cell(_cell(raw, "price"))
            copy["value"] = _money_cell(_cell(raw, "value"))
            copy["note"] = _cell(raw, "copy_note")
            row["copy"] = copy
            row["owned"] = 1
        location = _cell(raw, "location")
        row["location"] = location.split(PATH_SEP) if location else []
        status = _cell(raw, "play_status")
        row["play_status"] = status if status in PLAY_STATUSES else None
        if row["play_status"] is not None:
            row["rating"] = _rating(_cell(raw, "rating"))
            row["playtime_minutes"] = _int(_cell(raw, "playtime_minutes"))
            for field in _ROW_DATES:
                row[field] = _date(_cell(raw, field))
            row["completion_count"] = _int(_cell(raw, "completion_count"))
        row["review"] = _cell(raw, "review")
        row["wishlist"] = _bool_cell(_cell(raw, "wishlist"))
        row["wishlist_buy"] = _bool_cell(_cell(raw, "wishlist_buy"))
        row["needs_details"] = False
        rows.append(row)
    return rows


_ROW_DATES = ("started_at", "completed_at", "last_played_at")


def _money_cell(value: str) -> float | int | None:
    number = _float(value)
    if number is None or number < 0:
        return None
    return int(number) if number.is_integer() else number


def parse(text: str) -> list[dict[str, Any]]:
    """Import rows from CSV *text*."""
    return parse_library(text)


# ── Import ───────────────────────────────────────────────────────────────────


class _Index:
    """The match keys of the games: id, the barcode of a copy, then title."""

    def __init__(self, games: dict[str, dict[str, Any]], copies: Any = ()) -> None:
        self.by_id: set[str] = set()
        self.barcode: dict[str, str] = {}
        self.title: dict[str, str] = {}
        for game in games.values():
            self.add(game)
        for copy in copies:
            self.add_barcode(copy.get("barcode"), copy.get("game_id"))

    def add_barcode(self, code: Any, game_id: Any) -> None:
        """Map the barcode of a copy to its game. The first copy wins."""
        if code and game_id:
            self.barcode.setdefault(str(code), str(game_id))

    def add(self, game: dict[str, Any]) -> None:
        self.by_id.add(game["id"])
        key = title_key(game["title"])
        if key:
            self.title.setdefault(key, game["id"])

    def match(self, row: dict[str, Any]) -> tuple[str | None, str]:
        """``(game_id, action)``: ``existing``, ``title_match`` or ``new``."""
        if row["game_id"] and row["game_id"] in self.by_id:
            return str(row["game_id"]), ACTION_EXISTING
        if row["barcode"] and row["barcode"] in self.barcode:
            return self.barcode[row["barcode"]], ACTION_EXISTING
        found = self.title.get(title_key(row["title"]))
        return found, ACTION_TITLE_MATCH if found else ACTION_NEW


# The game fields of an import row.
_ROW_GAME_FIELDS = (
    "title",
    "summary",
    "genres",
    "release_date",
    "franchise",
    "igdb_id",
    "tags",
    "shared_notes",
)


def _new_game(row: dict[str, Any], now: str) -> dict[str, Any]:
    data = {
        field: row[field]
        for field in _ROW_GAME_FIELDS
        if row.get(field) not in (None, "", [])
    }
    data["needs_details"] = bool(row.get("needs_details", True))
    game = build_game(data, now=now)
    if row.get("game_id"):
        game["id"] = str(row["game_id"])
    return game


ACTION_NEW = "new"
ACTION_EXISTING = "existing"
ACTION_TITLE_MATCH = "title_match"
ACTION_ERROR = "error"
COUNT_KEYS = (
    "rows",
    "backlog",
    "playing",
    "completed",
    "abandoned",
    "wishlist",
    "copies",
    "tags",
    "errors",
    "existing",
    "new",
    "title_match",
)


def summary_of(counts: dict[str, int], kept: int) -> dict[str, int]:
    """The summary of the ``import_completed`` event, from the import counts."""
    return {
        "rows": counts["rows"],
        "games_added": counts["new"],
        "games_matched": counts["existing"] + counts["title_match"],
        "copies_added": counts["copies"],
        "progress_set": sum(counts[status] for status in PLAY_STATUSES),
        "progress_kept": kept,
        "wishlist_added": counts["wishlist"],
        "errors": counts["errors"],
    }


def apply_import(
    state: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    person_id: str,
    shelf_id: str | None,
    import_review: bool,
    replace_progress: bool,
    now: str,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    """Apply import rows to a copy of *state*.

    Return ``(new_state, counts, results)``. ``counts`` has the keys of
    :data:`COUNT_KEYS` and ``progress_kept``. Each result has ``line``, ``title``,
    ``barcode``, ``game_id`` and ``action`` (``new``, ``existing``,
    ``title_match`` or ``error``). An error result also has ``error`` (a
    translation key) and ``placeholders``.
    """
    new = clone(state)
    index = _Index(new["games"], new["copies"].values())
    progress = new["progress"].setdefault(person_id, {})
    copy_ids = set(new["copies"])
    owned_games = {c.get("game_id") for c in new["copies"].values()}
    progress_done: set[tuple[str, str]] = set()
    counts = dict.fromkeys(COUNT_KEYS, 0)
    counts["rows"] = len(rows)
    counts["progress_kept"] = 0
    results: list[dict[str, Any]] = []
    for row in rows:
        result: dict[str, Any] = {
            "line": row["line"],
            "title": row["title"],
            "barcode": row["barcode"],
            "game_id": None,
            "action": ACTION_NEW,
        }
        try:
            # Check the copy first, so a row with a bad copy changes no record.
            copy_data = row.get("copy") or {}
            for field in COPY_FIELDS:
                if copy_data.get(field) is not None:
                    copy_field(field, copy_data[field])
            game_id, action = index.match(row)
            if game_id is None:
                game = _new_game(row, now)
                new["games"][game["id"]] = game
                index.add(game)
                game_id = game["id"]
                if row["tags"]:
                    counts["tags"] += 1
            else:
                game = new["games"][game_id]
                extra = [t for t in row["tags"] if t not in game["tags"]]
                if extra:
                    game["tags"] = [*game["tags"], *extra]
                    counts["tags"] += 1
            owner = index.barcode.get(row["barcode"] or "")
            if row["copy"] is not None and owner not in (None, game_id):
                raise LibraryError("duplicate_barcode", barcode=row["barcode"])
            counts[action] += 1
            result["action"] = action
            result["game_id"] = game_id
            if _import_copy(new, row, game_id, shelf_id, copy_ids, owned_games, now):
                counts["copies"] += 1
                index.add_barcode(row["barcode"], game_id)
            # A library file has 1 row for each copy. The first row of a game
            # and a platform sets the progress on that platform.
            platform = row["platform"] or DEFAULT_PLATFORM
            if row["play_status"] and (game_id, platform) not in progress_done:
                progress_done.add((game_id, platform))
                rows_of_game = progress.setdefault(game_id, {})
                if platform in rows_of_game and not replace_progress:
                    counts["progress_kept"] += 1
                else:
                    rows_of_game[platform] = _progress_row(row, import_review, now)
                    counts[row["play_status"]] += 1
            if (
                row["wishlist"]
                and game_id not in owned_games
                and not new["games"][game_id]["wishlist"]
            ):
                entry = build_wishlist(
                    person_id, buy=bool(row["wishlist_buy"]), now=now
                )
                new["games"][game_id]["wishlist"] = entry
                counts["wishlist"] += 1
        except LibraryError as err:
            result["action"] = ACTION_ERROR
            result["error"] = err.key
            result["placeholders"] = err.placeholders
            counts["errors"] += 1
        results.append(result)
    for game_id in [g for g, rows in progress.items() if not rows]:
        del progress[game_id]
    if not progress:
        new["progress"].pop(person_id, None)
    return new, counts, results


def _import_copy(
    new: dict[str, Any],
    row: dict[str, Any],
    game_id: str,
    shelf_id: str | None,
    copy_ids: set[str],
    owned_games: set[Any],
    now: str,
) -> bool:
    """Add the copy of a row, if the row has one and it is not in the library.

    A row with a copy id adds its copy unless a copy with that id exists. A row
    with no copy id adds 1 copy only to a game with no copy. Return whether a
    copy was added.
    """
    copy = row.get("copy")
    if copy is None:
        return False
    copy_id = copy.get("id")
    if copy_id is not None:
        if copy_id in copy_ids:
            return False
    elif game_id in owned_games:
        return False
    location = row.get("location") or []
    target = find_shelf_by_path(new, location) if location else None
    data = {k: v for k, v in copy.items() if k != "id" and v is not None}
    data["barcode"] = row.get("barcode")
    data["game_id"] = game_id
    data["shelf_id"] = target or (shelf_id if shelf_id in new["shelves"] else None)
    record = build_copy(data, now=now)
    if copy_id:
        record["id"] = str(copy_id)
    new["copies"][record["id"]] = record
    copy_ids.add(record["id"])
    owned_games.add(game_id)
    return True


def _progress_row(row: dict[str, Any], import_review: bool, now: str) -> dict[str, Any]:
    progress = empty_progress(now=now)
    progress["play_status"] = row["play_status"]
    for field in ("rating", "playtime_minutes", *_ROW_DATES):
        progress[field] = row.get(field)
    count = row["completion_count"]
    if count is None:
        count = 1 if row["play_status"] == "completed" else 0
    progress["completion_count"] = count
    if import_review:
        progress["review"] = row["review"]
    return progress


_ROW_PROGRESS_FIELDS = (
    "play_status",
    "rating",
    "playtime_minutes",
    *_ROW_DATES,
    "completion_count",
    "review",
)


def _set_row_progress(row: dict[str, Any], progress: dict[str, Any] | None) -> None:
    """Write a progress row into an export row."""
    if not progress:
        return
    for field in _ROW_PROGRESS_FIELDS:
        row[field] = progress.get(field)
    row["review"] = progress.get("review", "")


# ── Export ───────────────────────────────────────────────────────────────────


def rows_from_state(
    state: dict[str, Any], person_id: str | None
) -> list[dict[str, Any]]:
    """Import rows that describe the library, for :func:`write`.

    There is 1 row for each copy, and 1 row for a game with no copy. The first
    row of a platform has the progress of *person_id* on that platform. A
    platform with progress and no copy gets 1 more row with no copy. With no
    *person_id*, the rows have no progress.
    """
    copies: dict[str, list[dict[str, Any]]] = {}
    for copy in sorted(
        state["copies"].values(), key=lambda c: (str(c.get("created_at")), c["id"])
    ):
        copies.setdefault(copy["game_id"], []).append(copy)
    progress = state["progress"].get(person_id, {}) if person_id else {}
    rows: list[dict[str, Any]] = []
    games = sorted(
        state["games"].values(),
        key=lambda b: (b["title"].casefold(), b["id"]),
    )
    for game in games:
        base = empty_row(len(rows) + 1)
        for field in (*_ROW_GAME_FIELDS, "needs_details"):
            base[field] = clone(game[field])
        base["game_id"] = game["id"]
        wish = game["wishlist"]
        if wish and (person_id is None or wish.get("person_id") == person_id):
            base["wishlist"] = True
            base["wishlist_buy"] = bool(wish.get("buy"))
        game_copies = copies.get(game["id"], [])
        base["owned"] = len(game_copies)
        left = dict(progress.get(game["id"]) or {})
        if not game_copies and not left:
            rows.append(base)
            continue
        for copy in game_copies:
            row = clone(base)
            row["line"] = len(rows) + 1
            row["copy"] = {
                "id": copy["id"],
                **{field: copy.get(field) for field in _COPY_COLUMNS},
            }
            row["platform"] = copy.get("platform")
            _set_row_progress(row, left.pop(str(copy.get("platform")), None))
            row["barcode"] = copy.get("barcode")
            row["location"] = location_path(state, copy.get("shelf_id"))
            rows.append(row)
        for platform in sorted(left):
            row = clone(base)
            row["line"] = len(rows) + 1
            row["platform"] = platform
            _set_row_progress(row, left[platform])
            rows.append(row)
    return rows


def _write_cells(fieldnames: tuple[str, ...], cells: list[dict[str, str]]) -> str:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fieldnames, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(cells)
    return out.getvalue()


def _num(value: Any) -> str:
    return "" if value is None else str(value)


def _bool_text(value: Any) -> str:
    return "true" if value else "false"


def _library_cells(row: dict[str, Any]) -> dict[str, str]:
    copy = row["copy"] or {}
    return {
        "game_id": row["game_id"] or "",
        "title": row["title"],
        "summary": row["summary"],
        "genres": LIST_SEP.join(row["genres"] or []),
        "release_date": row["release_date"],
        "franchise": row["franchise"] or "",
        "igdb_id": _num(row["igdb_id"]),
        "tags": LIST_SEP.join(row["tags"] or []),
        "shared_notes": row["shared_notes"],
        "copy_id": copy.get("id") or "",
        "platform": copy.get("platform") or row["platform"] or "",
        "format": copy.get("format") or "",
        "storefront": copy.get("storefront") or "",
        "region": copy.get("region") or "",
        "edition": copy.get("edition") or "",
        "steelbook": _bool_text(copy.get("steelbook")) if copy else "",
        "barcode": row["barcode"] or "",
        "condition": copy.get("condition") or "",
        "acquired": copy.get("acquired") or "",
        "acquired_from": copy.get("acquired_from") or "",
        "price": _num(copy.get("price")),
        "value": _num(copy.get("value")),
        "copy_note": copy.get("note") or "",
        "location": PATH_SEP.join(row["location"] or []),
        "play_status": row["play_status"] or "",
        "rating": _num(row["rating"]),
        "playtime_minutes": _num(row["playtime_minutes"]),
        "started_at": row["started_at"] or "",
        "completed_at": row["completed_at"] or "",
        "last_played_at": row["last_played_at"] or "",
        "completion_count": _num(row["completion_count"]),
        "review": row["review"],
        "wishlist": _bool_text(row["wishlist"]),
        "wishlist_buy": _bool_text(row["wishlist_buy"]),
    }


def write(rows: list[dict[str, Any]]) -> str:
    """CSV text for import rows."""
    return _write_cells(LIBRARY_COLUMNS, [_library_cells(r) for r in rows])


def export(state: dict[str, Any], person_id: str | None) -> str:
    """CSV text of the library."""
    return write(rows_from_state(state, person_id))


def export_filename(today: str) -> str:
    """The file name of an export, such as ``games-2026-10-05.csv``."""
    return f"games-{today}.csv"


__all__ = [
    "LIBRARY_COLUMNS",
    "apply_import",
    "empty_row",
    "export",
    "export_filename",
    "parse",
    "parse_library",
    "rows_from_state",
    "write",
]
