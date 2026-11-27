"""Pure payload builders for the bus events of Home Keeper Games.

Each state change fires a ``home_keeper_games_<noun>_<verb>`` event. The store
fires it, and a builder here makes the payload, so a test and an integrator read
the payload that ships. The game events share 1 spine:
``{game_id, title, person_id, origin}``. ``origin`` is the marker that the caller
sent, or None for a user.

The catalog is ``api_surface.EVENTS`` and ``docs/EVENTS.md``.

This module imports no Home Assistant code.
"""

from __future__ import annotations

from typing import Any


def room_event_data(room: dict[str, Any], origin: str | None) -> dict[str, Any]:
    """The payload of the room events."""
    return {"room_id": room["id"], "name": room.get("name", ""), "origin": origin}


def unit_event_data(unit: dict[str, Any], origin: str | None) -> dict[str, Any]:
    """The payload of the unit events."""
    return {
        "unit_id": unit["id"],
        "room_id": unit.get("room_id"),
        "name": unit.get("name", ""),
        "origin": origin,
    }


def shelf_event_data(shelf: dict[str, Any], origin: str | None) -> dict[str, Any]:
    """The payload of the shelf events."""
    return {
        "shelf_id": shelf["id"],
        "unit_id": shelf.get("unit_id"),
        "name": shelf.get("name", ""),
        "origin": origin,
    }


def location_changed_data(
    base: dict[str, Any], changed_fields: list[str]
) -> dict[str, Any]:
    """A location payload with the list of changed fields."""
    return {**base, "changed_fields": list(changed_fields)}


def game_event_data(
    game: dict[str, Any], origin: str | None, person_id: str | None = None
) -> dict[str, Any]:
    """The spine of every game event."""
    return {
        "game_id": game["id"],
        "title": game.get("title", ""),
        "person_id": person_id,
        "origin": origin,
    }


def game_updated_event_data(
    game: dict[str, Any], changed_fields: list[str], origin: str | None
) -> dict[str, Any]:
    """The payload of ``game_updated``."""
    return {**game_event_data(game, origin), "changed_fields": list(changed_fields)}


def copy_event_data(
    game: dict[str, Any], copy: dict[str, Any], origin: str | None
) -> dict[str, Any]:
    """The payload of ``copy_added`` and ``copy_removed``."""
    return {
        **game_event_data(game, origin),
        "copy_id": copy["id"],
        "shelf_id": copy.get("shelf_id"),
    }


def copy_updated_event_data(
    game: dict[str, Any],
    copy: dict[str, Any],
    changed_fields: list[str],
    origin: str | None,
) -> dict[str, Any]:
    """The payload of ``copy_updated``. It names the fields, not their values."""
    return {
        **copy_event_data(game, copy, origin),
        "changed_fields": list(changed_fields),
    }


def copy_moved_event_data(
    game: dict[str, Any],
    copy: dict[str, Any],
    previous_shelf_id: str | None,
    origin: str | None,
) -> dict[str, Any]:
    """The payload of ``copy_moved``."""
    return {
        **copy_event_data(game, copy, origin),
        "previous_shelf_id": previous_shelf_id,
    }


def progress_changed_event_data(
    game: dict[str, Any],
    person_id: str,
    platform: str,
    play_status: str | None,
    previous_status: str | None,
    origin: str | None,
) -> dict[str, Any]:
    """The payload of ``progress_changed``. ``play_status`` is None for no row."""
    return {
        **game_event_data(game, origin, person_id),
        "platform": platform,
        "play_status": play_status,
        "previous_status": previous_status,
    }


def progress_updated_event_data(
    game: dict[str, Any],
    person_id: str,
    platform: str,
    play_status: str,
    changed_fields: list[str],
    origin: str | None,
) -> dict[str, Any]:
    """The payload of ``progress_updated``: a change that keeps the play status.

    It names the fields, so the private review of a person never goes on the bus.
    """
    return {
        **game_event_data(game, origin, person_id),
        "platform": platform,
        "play_status": play_status,
        "changed_fields": list(changed_fields),
    }


def session_event_data(
    game: dict[str, Any], session: dict[str, Any], origin: str | None
) -> dict[str, Any]:
    """The payload of ``session_logged`` and ``session_deleted``."""
    return {
        **game_event_data(game, origin, session["person_id"]),
        "session_id": session["id"],
        "platform": session["platform"],
        "source": session["source"],
        "date": session["date"],
        "minutes": session["minutes"],
    }


def game_completed_event_data(
    game: dict[str, Any],
    person_id: str,
    platform: str,
    row: dict[str, Any],
    origin: str | None,
) -> dict[str, Any]:
    """The payload of ``game_completed``."""
    return {
        **game_event_data(game, origin, person_id),
        "platform": platform,
        "completed_at": row.get("completed_at"),
        "rating": row.get("rating"),
        "completion_count": row.get("completion_count", 0),
    }


def loan_event_data(
    game: dict[str, Any], loan: dict[str, Any], origin: str | None
) -> dict[str, Any]:
    """The payload of ``loan_started``, ``loan_returned``, ``loan_overdue`` and
    ``loan_removed``.
    """
    return {
        **game_event_data(game, origin, loan.get("person_id")),
        "loan_id": loan["id"],
        "direction": loan.get("direction"),
        "copy_id": loan.get("copy_id"),
        "party": loan.get("party", ""),
        "started": loan.get("started"),
        "due": loan.get("due"),
        "returned": loan.get("returned"),
    }


def loan_updated_event_data(
    game: dict[str, Any],
    loan: dict[str, Any],
    changed_fields: list[str],
    origin: str | None,
) -> dict[str, Any]:
    """The payload of ``loan_updated``."""
    return {
        **loan_event_data(game, loan, origin),
        "changed_fields": list(changed_fields),
    }


def wishlist_event_data(
    game: dict[str, Any], entry: dict[str, Any], origin: str | None
) -> dict[str, Any]:
    """The payload of ``wishlist_added`` and ``wishlist_removed``."""
    return {
        **game_event_data(game, origin, entry.get("person_id")),
        "buy": bool(entry.get("buy")),
        "bought": bool(entry.get("bought")),
    }


def import_completed_event_data(
    summary: dict[str, Any], person_id: str | None, source: str, origin: str | None
) -> dict[str, Any]:
    """The payload of ``import_completed``."""
    return {
        "person_id": person_id,
        "source": source,
        "rows": int(summary.get("rows", 0)),
        "games_added": int(summary.get("games_added", 0)),
        "games_matched": int(summary.get("games_matched", 0)),
        "copies_added": int(summary.get("copies_added", 0)),
        "progress_set": int(summary.get("progress_set", 0)),
        "wishlist_added": int(summary.get("wishlist_added", 0)),
        "errors": int(summary.get("errors", 0)),
        "origin": origin,
    }


def data_imported_event_data(
    counts: dict[str, dict[str, int]], origin: str | None
) -> dict[str, Any]:
    """The payload of ``data_imported``: the counts of each section."""
    return {
        "counts": {
            section: {key: int(value) for key, value in numbers.items()}
            for section, numbers in counts.items()
        },
        "origin": origin,
    }


def person_settings_event_data(
    person_id: str, changed_fields: list[str], origin: str | None
) -> dict[str, Any]:
    """The payload of ``person_settings_updated``. It has no setting values."""
    return {
        "person_id": person_id,
        "changed_fields": list(changed_fields),
        "origin": origin,
    }


def settings_event_data(
    changed_fields: list[str], currency: str, origin: str | None
) -> dict[str, Any]:
    """The payload of ``settings_updated``: the options of the library."""
    return {
        "changed_fields": list(changed_fields),
        "currency": currency,
        "origin": origin,
    }
