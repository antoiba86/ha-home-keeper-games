"""The library store: the 1 write path for library data.

Every change goes through a method of :class:`LibraryStore`. Each method checks
the input with the pure ``models`` functions, changes the document, saves it,
fires the bus events of the change and then tells the listeners (the
coordinator, the ``subscribe`` command and the syncs). Entities, the tab and the
card read the document and never write it.

``revision`` goes up by 1 on each change. The ``subscribe`` websocket command
sends it, and the client then reads ``get_state`` again.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from . import events, models
from .const import (
    EVENT_COPY_ADDED,
    EVENT_COPY_MOVED,
    EVENT_COPY_REMOVED,
    EVENT_COPY_UPDATED,
    EVENT_DATA_IMPORTED,
    EVENT_GAME_ADDED,
    EVENT_GAME_COMPLETED,
    EVENT_GAME_REMOVED,
    EVENT_GAME_UPDATED,
    EVENT_IMPORT_COMPLETED,
    EVENT_LOAN_OVERDUE,
    EVENT_LOAN_REMOVED,
    EVENT_LOAN_RETURNED,
    EVENT_LOAN_STARTED,
    EVENT_LOAN_UPDATED,
    EVENT_PERSON_SETTINGS_UPDATED,
    EVENT_PROGRESS_CHANGED,
    EVENT_PROGRESS_UPDATED,
    EVENT_ROOM_ADDED,
    EVENT_ROOM_REMOVED,
    EVENT_ROOM_UPDATED,
    EVENT_SESSION_DELETED,
    EVENT_SESSION_LOGGED,
    EVENT_SESSION_STARTED,
    EVENT_SETTINGS_UPDATED,
    EVENT_SHELF_ADDED,
    EVENT_SHELF_REMOVED,
    EVENT_SHELF_UPDATED,
    EVENT_UNIT_ADDED,
    EVENT_UNIT_REMOVED,
    EVENT_UNIT_UPDATED,
    EVENT_WISHLIST_ADDED,
    EVENT_WISHLIST_REMOVED,
    STORAGE_KEY,
    STORAGE_MINOR_VERSION,
    STORAGE_VERSION,
)
from .models import LibraryError
from .wishlist import SyncPlan

_LOGGER = logging.getLogger(__name__)

Event = tuple[str, dict[str, Any]]


class _LibraryStorage(Store[dict[str, Any]]):
    """The storage file, with the migration hook."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Return the document in the current version.

        Version 1.1 is the first version. ``models.normalize_state`` adds each
        missing section, so a new section needs no migration step.
        """
        return models.normalize_state(old_data)


def today() -> str:
    """Today in the time zone of Home Assistant, as ``YYYY-MM-DD``."""
    return dt_util.now().date().isoformat()


def now() -> str:
    """The time now, aware, in ISO 8601."""
    return dt_util.now().isoformat()


class LibraryStore:
    """Loads, saves and changes the library document, and fires the events."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._storage = _LibraryStorage(
            hass, STORAGE_VERSION, STORAGE_KEY, minor_version=STORAGE_MINOR_VERSION
        )
        self.state: dict[str, Any] = models.empty_state()
        self.revision = 0
        self._listeners: list[Callable[[], None]] = []
        # The cover files that a change made unused. ``covers.py`` deletes them.
        self.on_cover_released: Callable[[str], None] | None = None

    async def load(self) -> None:
        """Load the document, or start an empty one."""
        self.state = models.normalize_state(await self._storage.async_load())

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Call *listener* after each change. Return a callable that removes it."""
        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    @callback
    def async_notify(self) -> None:
        """Tell the listeners about a change outside the document, such as the
        currency option. The revision goes up."""
        self.revision += 1
        self._notify_listeners()

    def _notify_listeners(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:
                _LOGGER.exception("A library store listener failed")

    @callback
    def async_settings_updated(
        self, changed_fields: list[str], currency: str, *, origin: str | None = None
    ) -> None:
        """Fire ``settings_updated`` for a change of the entry options.

        The options are on the config entry, not in the document, so there is
        nothing to save. The listeners hear about the change.
        """
        payload = events.settings_event_data(changed_fields, currency, origin)
        self.hass.bus.async_fire(EVENT_SETTINGS_UPDATED, payload)
        self.async_notify()

    async def _commit(self, fired: list[Event]) -> None:
        """Save, fire the events and tell the listeners."""
        await self._storage.async_save(self.state)
        self.revision += 1
        for name, data in fired:
            self.hass.bus.async_fire(name, data)
        self._notify_listeners()

    # ── Lookups ──────────────────────────────────────────────────────────────

    def _get(self, section: str, key: str, record_id: str) -> dict[str, Any]:
        record = self.state[section].get(record_id)
        if record is None:
            raise LibraryError(f"{key}_not_found", id=record_id)
        return dict(record)

    def room(self, room_id: str) -> dict[str, Any]:
        """The room, or ``room_not_found``."""
        return self._get("rooms", "room", room_id)

    def unit(self, unit_id: str) -> dict[str, Any]:
        """The unit, or ``unit_not_found``."""
        return self._get("units", "unit", unit_id)

    def shelf(self, shelf_id: str) -> dict[str, Any]:
        """The shelf, or ``shelf_not_found``."""
        return self._get("shelves", "shelf", shelf_id)

    def game(self, game_id: str) -> dict[str, Any]:
        """The game, or ``game_not_found``."""
        return self._get("games", "game", game_id)

    def copy(self, copy_id: str) -> dict[str, Any]:
        """The copy, or ``copy_not_found``."""
        return self._get("copies", "copy", copy_id)

    def loan(self, loan_id: str) -> dict[str, Any]:
        """The loan, or ``loan_not_found``."""
        return self._get("loans", "loan", loan_id)

    def session(self, session_id: str) -> dict[str, Any]:
        """The play session, or ``session_not_found``."""
        return self._get("sessions", "session", session_id)

    def check_shelf(self, shelf_id: str | None) -> str | None:
        """*shelf_id* if it is None or a known shelf, else ``shelf_not_found``."""
        if shelf_id:
            self.shelf(shelf_id)
        return shelf_id or None

    def progress_row(
        self, person_id: str, game_id: str, platform: str
    ) -> dict[str, Any] | None:
        """The progress row of a person for a game on a platform."""
        games = self.state["progress"].get(person_id) or {}
        row = (games.get(game_id) or {}).get(platform)
        return dict(row) if row else None

    # ── Rooms, units and shelves ─────────────────────────────────────────

    async def add_room(
        self, data: dict[str, Any], *, origin: str | None = None
    ) -> dict[str, Any]:
        """Add a room."""
        room = models.build_room(data, order=models.next_order(self.state["rooms"]))
        self.state["rooms"][room["id"]] = room
        await self._commit([(EVENT_ROOM_ADDED, events.room_event_data(room, origin))])
        return dict(room)

    async def update_room(
        self, room_id: str, data: dict[str, Any], *, origin: str | None = None
    ) -> dict[str, Any]:
        """Change a room."""
        updated, changed = models.update_location("room", self.room(room_id), data)
        if not changed:
            return updated
        self.state["rooms"][room_id] = updated
        payload = events.location_changed_data(
            events.room_event_data(updated, origin), changed
        )
        await self._commit([(EVENT_ROOM_UPDATED, payload)])
        return dict(updated)

    async def add_unit(
        self, data: dict[str, Any], *, origin: str | None = None
    ) -> dict[str, Any]:
        """Add a unit to a room."""
        self.room(str(data.get("room_id")))
        order = models.next_order(self.state["units"], room_id=data["room_id"])
        unit = models.build_unit(data, order=order)
        self.state["units"][unit["id"]] = unit
        fired = [(EVENT_UNIT_ADDED, events.unit_event_data(unit, origin))]
        await self._commit(fired)
        return dict(unit)

    async def update_unit(
        self, unit_id: str, data: dict[str, Any], *, origin: str | None = None
    ) -> dict[str, Any]:
        """Change a unit. A new ``room_id`` moves it to another room."""
        if "room_id" in data:
            self.room(str(data["room_id"]))
        updated, changed = models.update_location("unit", self.unit(unit_id), data)
        if not changed:
            return updated
        self.state["units"][unit_id] = updated
        payload = events.location_changed_data(
            events.unit_event_data(updated, origin), changed
        )
        await self._commit([(EVENT_UNIT_UPDATED, payload)])
        return dict(updated)

    async def add_shelf(
        self, data: dict[str, Any], *, origin: str | None = None
    ) -> dict[str, Any]:
        """Add a shelf to a unit."""
        self.unit(str(data.get("unit_id")))
        order = models.next_order(self.state["shelves"], unit_id=data["unit_id"])
        shelf = models.build_shelf(data, order=order)
        self.state["shelves"][shelf["id"]] = shelf
        await self._commit(
            [(EVENT_SHELF_ADDED, events.shelf_event_data(shelf, origin))]
        )
        return dict(shelf)

    async def update_shelf(
        self, shelf_id: str, data: dict[str, Any], *, origin: str | None = None
    ) -> dict[str, Any]:
        """Change a shelf. A new ``unit_id`` moves it to another unit."""
        if "unit_id" in data:
            self.unit(str(data["unit_id"]))
        updated, changed = models.update_location("shelf", self.shelf(shelf_id), data)
        if not changed:
            return updated
        self.state["shelves"][shelf_id] = updated
        payload = events.location_changed_data(
            events.shelf_event_data(updated, origin), changed
        )
        await self._commit([(EVENT_SHELF_UPDATED, payload)])
        return dict(updated)

    def _remove_shelf(
        self, shelf_id: str, fired: list[Event], origin: str | None
    ) -> None:
        """Remove a shelf and move its copies to no shelf. No save."""
        shelf = self.state["shelves"].pop(shelf_id)
        for copy in self.state["copies"].values():
            if copy.get("shelf_id") != shelf_id:
                continue
            copy["shelf_id"] = None
            game = self._game_or_stub(copy["game_id"])
            fired.append(
                (
                    EVENT_COPY_MOVED,
                    events.copy_moved_event_data(game, copy, shelf_id, origin),
                )
            )
        fired.append((EVENT_SHELF_REMOVED, events.shelf_event_data(shelf, origin)))

    def _remove_unit(
        self, unit_id: str, fired: list[Event], origin: str | None
    ) -> None:
        """Remove a unit with its shelves. No save."""
        for shelf_id in [
            s["id"]
            for s in self.state["shelves"].values()
            if s.get("unit_id") == unit_id
        ]:
            self._remove_shelf(shelf_id, fired, origin)
        unit = self.state["units"].pop(unit_id)
        fired.append((EVENT_UNIT_REMOVED, events.unit_event_data(unit, origin)))

    async def delete_room(
        self, room_id: str, *, force: bool = False, origin: str | None = None
    ) -> dict[str, Any]:
        """Delete a room. A room with units needs *force*."""
        room = self.room(room_id)
        children = [
            b["id"] for b in self.state["units"].values() if b.get("room_id") == room_id
        ]
        if children and not force:
            raise LibraryError("room_not_empty", count=len(children))
        fired: list[Event] = []
        for unit_id in children:
            self._remove_unit(unit_id, fired, origin)
        del self.state["rooms"][room_id]
        fired.append((EVENT_ROOM_REMOVED, events.room_event_data(room, origin)))
        await self._commit(fired)
        return room

    async def delete_unit(
        self, unit_id: str, *, force: bool = False, origin: str | None = None
    ) -> dict[str, Any]:
        """Delete a unit. A unit with shelves needs *force*."""
        unit = self.unit(unit_id)
        count = sum(
            1 for s in self.state["shelves"].values() if s.get("unit_id") == unit_id
        )
        if count and not force:
            raise LibraryError("unit_not_empty", count=count)
        fired: list[Event] = []
        self._remove_unit(unit_id, fired, origin)
        await self._commit(fired)
        return unit

    async def delete_shelf(
        self, shelf_id: str, *, force: bool = False, origin: str | None = None
    ) -> dict[str, Any]:
        """Delete a shelf. A shelf with copies needs *force*."""
        shelf = self.shelf(shelf_id)
        count = sum(
            1 for c in self.state["copies"].values() if c.get("shelf_id") == shelf_id
        )
        if count and not force:
            raise LibraryError("shelf_not_empty", count=count)
        fired: list[Event] = []
        self._remove_shelf(shelf_id, fired, origin)
        await self._commit(fired)
        return shelf

    # ── Games ────────────────────────────────────────────────────────────────

    async def add_game(
        self, data: dict[str, Any], *, origin: str | None = None
    ) -> tuple[dict[str, Any], bool]:
        """Add a game. Return ``(game, existing)``, where ``existing`` is False."""
        game = models.build_game(data, now=now())
        self.state["games"][game["id"]] = game
        await self._commit([(EVENT_GAME_ADDED, events.game_event_data(game, origin))])
        return dict(game), False

    async def update_game(
        self, game_id: str, data: dict[str, Any], *, origin: str | None = None
    ) -> dict[str, Any]:
        """Change the fields of a game."""
        updated, changed = models.update_game(self.game(game_id), data, now=now())
        return await self._replace_game(updated, changed, origin)

    async def _replace_game(
        self, updated: dict[str, Any], changed: list[str], origin: str | None
    ) -> dict[str, Any]:
        if not changed:
            return updated
        self.state["games"][updated["id"]] = updated
        payload = events.game_updated_event_data(updated, changed, origin)
        await self._commit([(EVENT_GAME_UPDATED, payload)])
        return dict(updated)

    async def set_cover(
        self,
        game_id: str,
        kind: str,
        file: str | None,
        *,
        origin: str | None = None,
    ) -> dict[str, Any]:
        """Set the cover of a game. The previous file is released."""
        game = self.game(game_id)
        models.choice(kind, "kind", models.COVER_KINDS)
        cover = {"kind": kind, "file": file if kind != "none" else None}
        old = (game.get("cover") or {}).get("file")
        if cover == game.get("cover"):
            return game
        game["cover"] = cover
        game["updated_at"] = now()
        self.state["games"][game_id] = game
        payload = events.game_updated_event_data(game, ["cover"], origin)
        await self._commit([(EVENT_GAME_UPDATED, payload)])
        if old and old != cover["file"]:
            self._release_cover(old)
        return dict(game)

    def _release_cover(self, file: str) -> None:
        if self.on_cover_released is not None:
            self.on_cover_released(file)

    async def delete_game(
        self, game_id: str, *, origin: str | None = None
    ) -> dict[str, Any]:
        """Delete a game with its copies, progress rows and loans."""
        game = self.game(game_id)
        fired: list[Event] = []
        for copy_id in [
            c["id"] for c in self.state["copies"].values() if c["game_id"] == game_id
        ]:
            copy = self.state["copies"].pop(copy_id)
            fired.append(
                (EVENT_COPY_REMOVED, events.copy_event_data(game, copy, origin))
            )
        for games in self.state["progress"].values():
            games.pop(game_id, None)
        self.state["progress"] = {p: g for p, g in self.state["progress"].items() if g}
        for loan_id in [
            lo["id"] for lo in self.state["loans"].values() if lo["game_id"] == game_id
        ]:
            del self.state["loans"][loan_id]
        for session_id in [
            s["id"] for s in self.state["sessions"].values() if s["game_id"] == game_id
        ]:
            del self.state["sessions"][session_id]
        self._orphan_item(game.get("wishlist"))
        del self.state["games"][game_id]
        fired.append((EVENT_GAME_REMOVED, events.game_event_data(game, origin)))
        await self._commit(fired)
        if file := (game.get("cover") or {}).get("file"):
            self._release_cover(file)
        return game

    # ── Copies ───────────────────────────────────────────────────────────────

    def _check_barcode(self, code: str | None, game_id: str) -> None:
        """Refuse a barcode that a copy of another game has: 1 code is 1 game."""
        other = models.find_game_by_barcode(self.state, code)
        if other is not None and other["id"] != game_id:
            raise LibraryError("duplicate_barcode", barcode=str(code))

    def _copy_record(self, data: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        game = self.game(str(data.get("game_id")))
        self.check_shelf(data.get("shelf_id"))
        record = models.build_copy(data, now=now())
        self._check_barcode(record["barcode"], game["id"])
        return record, game

    async def add_copy(
        self, data: dict[str, Any], *, origin: str | None = None
    ) -> dict[str, Any]:
        """Add a copy of a game.

        The first copy of a game on the wishlist takes it off the wishlist, as
        ``got_wishlist_game`` does. The wishlist sync then removes its to-do
        item.
        """
        record, game = self._copy_record(data)
        clears = models.copy_clears_wishlist(self.state, game["id"])
        self.state["copies"][record["id"]] = record
        fired: list[Event] = [
            (EVENT_COPY_ADDED, events.copy_event_data(game, record, origin))
        ]
        if clears:
            entry = game["wishlist"]
            self._orphan_item(entry)
            game["wishlist"] = None
            self.state["games"][game["id"]] = game
            payload = events.wishlist_event_data(game, entry, origin)
            fired.append((EVENT_WISHLIST_REMOVED, payload))
        await self._commit(fired)
        return dict(record)

    async def update_copy(
        self, copy_id: str, data: dict[str, Any], *, origin: str | None = None
    ) -> dict[str, Any]:
        """Change a copy.

        A new shelf fires ``copy_moved``. A change of the other fields fires
        ``copy_updated`` with the names of those fields.
        """
        record = self.copy(copy_id)
        if "shelf_id" in data:
            self.check_shelf(data["shelf_id"])
        updated, changed = models.update_copy(record, data)
        if not changed:
            return updated
        if "barcode" in changed:
            self._check_barcode(updated["barcode"], updated["game_id"])
        self.state["copies"][copy_id] = updated
        fired: list[Event] = []
        game = self.game(updated["game_id"])
        if "shelf_id" in changed:
            fired.append(
                (
                    EVENT_COPY_MOVED,
                    events.copy_moved_event_data(
                        game, updated, record.get("shelf_id"), origin
                    ),
                )
            )
        if other := [f for f in changed if f != "shelf_id"]:
            payload = events.copy_updated_event_data(game, updated, other, origin)
            fired.append((EVENT_COPY_UPDATED, payload))
        await self._commit(fired)
        return dict(updated)

    async def move_copy(
        self, copy_id: str, shelf_id: str | None, *, origin: str | None = None
    ) -> dict[str, Any]:
        """Move a copy to a shelf, or to no shelf. A digital copy has no shelf."""
        if shelf_id and self.copy(copy_id).get("format") == "digital":
            raise LibraryError("digital_copy_no_shelf")
        return await self.update_copy(copy_id, {"shelf_id": shelf_id}, origin=origin)

    async def delete_copy(
        self, copy_id: str, *, origin: str | None = None
    ) -> dict[str, Any]:
        """Delete a copy. A copy that is lent out cannot be deleted."""
        record = self.copy(copy_id)
        if models.open_loan_of_copy(self.state, copy_id):
            raise LibraryError("copy_on_loan")
        del self.state["copies"][copy_id]
        game = self.game(record["game_id"])
        payload = events.copy_event_data(game, record, origin)
        await self._commit([(EVENT_COPY_REMOVED, payload)])
        return record

    # ── Progress ─────────────────────────────────────────────────────────────

    def _progress_events(
        self,
        game: dict[str, Any],
        person_id: str,
        platform: str,
        row: dict[str, Any] | None,
        previous: str | None,
        origin: str | None,
    ) -> list[Event]:
        status = row["play_status"] if row else None
        fired: list[Event] = [
            (
                EVENT_PROGRESS_CHANGED,
                events.progress_changed_event_data(
                    game, person_id, platform, status, previous, origin
                ),
            )
        ]
        if row is not None and status == "completed" and previous != "completed":
            fired.append(
                (
                    EVENT_GAME_COMPLETED,
                    events.game_completed_event_data(
                        game, person_id, platform, row, origin
                    ),
                )
            )
        return fired

    async def set_progress(
        self,
        game_id: str,
        person_id: str,
        data: dict[str, Any],
        *,
        origin: str | None = None,
    ) -> dict[str, Any] | None:
        """Set the progress row of a person on a platform.

        ``play_status: none`` removes the row. With no ``platform``, the row is on
        the platform of the copies (:func:`models.progress_platform`). The reply
        has the ``platform`` of the row.
        """
        game = self.game(game_id)
        platform = models.progress_platform(self.state, game_id, data.get("platform"))
        current = self.progress_row(person_id, game_id, platform)
        previous = current["play_status"] if current else None
        if data.get("play_status") == models.STATUS_NONE:
            if current is None:
                return None
            games = self.state["progress"][person_id]
            del games[game_id][platform]
            if not games[game_id]:
                del games[game_id]
            if not games:
                del self.state["progress"][person_id]
            fired = self._progress_events(
                game, person_id, platform, None, previous, origin
            )
            await self._commit(fired)
            return None
        row, changed = models.apply_progress(current, data, now=now(), today=today())
        if not changed:
            return {**row, "platform": platform}
        games = self.state["progress"].setdefault(person_id, {})
        games.setdefault(game_id, {})[platform] = row
        if "play_status" in changed:
            fired = self._progress_events(
                game, person_id, platform, row, previous, origin
            )
        else:
            payload = events.progress_updated_event_data(
                game, person_id, platform, row["play_status"], changed, origin
            )
            fired = [(EVENT_PROGRESS_UPDATED, payload)]
        await self._commit(fired)
        return {**row, "platform": platform}

    # ── Play sessions ────────────────────────────────────────────────────────

    def _session_progress(
        self,
        game: dict[str, Any],
        session: dict[str, Any],
        minutes: int,
        origin: str | None,
    ) -> list[Event]:
        """Add or take the minutes of *session* on its progress row.

        A deleted session of a row that is gone changes nothing.
        """
        person_id, platform = session["person_id"], session["platform"]
        current = self.progress_row(person_id, game["id"], platform)
        if current is None and minutes < 0:
            return []
        row, changed = models.session_progress(
            current, minutes, session["date"], now=now(), today=today()
        )
        if not changed:
            return []
        games = self.state["progress"].setdefault(person_id, {})
        games.setdefault(game["id"], {})[platform] = row
        previous = current["play_status"] if current else None
        if "play_status" in changed:
            return self._progress_events(
                game, person_id, platform, row, previous, origin
            )
        payload = events.progress_updated_event_data(
            game, person_id, platform, row["play_status"], changed, origin
        )
        return [(EVENT_PROGRESS_UPDATED, payload)]

    async def log_session(
        self,
        data: dict[str, Any],
        person_id: str,
        *,
        origin: str | None = None,
    ) -> dict[str, Any]:
        """Add a closed play session and its minutes to the progress row.

        With no ``platform``, the session is on the platform of the copies
        (:func:`models.progress_platform`).
        """
        game = self.game(str(data.get("game_id")))
        platform = models.progress_platform(
            self.state, game["id"], data.get("platform")
        )
        session = models.build_session(
            {**data, "game_id": game["id"]},
            person_id=person_id,
            platform=platform,
            now=now(),
            today=today(),
        )
        self.state["sessions"][session["id"]] = session
        fired: list[Event] = [
            (EVENT_SESSION_LOGGED, events.session_event_data(game, session, origin))
        ]
        fired += self._session_progress(game, session, session["minutes"], origin)
        await self._commit(fired)
        return dict(session)

    async def start_session(
        self,
        *,
        game_id: str,
        person_id: str,
        platform: str,
        source: str,
        external_id: str | None,
        started_at: str,
        origin: str | None = None,
    ) -> dict[str, Any]:
        """Open a session that a console listener measures.

        A new or ``backlog`` progress row becomes ``playing``. The play time
        changes when :meth:`end_session` closes the session.
        """
        game = self.game(game_id)
        session = models.build_live_session(
            game_id=game_id,
            person_id=person_id,
            platform=platform,
            source=source,
            external_id=external_id,
            started_at=started_at,
        )
        self.state["sessions"][session["id"]] = session
        fired: list[Event] = [
            (EVENT_SESSION_STARTED, events.session_event_data(game, session, origin))
        ]
        current = self.progress_row(person_id, game_id, session["platform"])
        row, changed = models.session_start_progress(
            current, session["date"], now=now(), today=today()
        )
        if changed:
            games = self.state["progress"].setdefault(person_id, {})
            games.setdefault(game_id, {})[session["platform"]] = row
            previous = current["play_status"] if current else None
            if "play_status" in changed:
                fired += self._progress_events(
                    game, person_id, session["platform"], row, previous, origin
                )
            else:
                payload = events.progress_updated_event_data(
                    game,
                    person_id,
                    session["platform"],
                    row["play_status"],
                    changed,
                    origin,
                )
                fired.append((EVENT_PROGRESS_UPDATED, payload))
        await self._commit(fired)
        return dict(session)

    async def end_session(
        self, session_id: str, ended_at: str, *, origin: str | None = None
    ) -> dict[str, Any] | None:
        """Close an open session and add its minutes to the progress row.

        A session of less than 1 minute is deleted, and the reply is None. A
        closed session stays as it is.
        """
        session = self.session(session_id)
        if session["minutes"] is not None:
            return session
        game = self.game(session["game_id"])
        minutes = models.session_minutes(session["started_at"] or "", ended_at)
        if minutes < 1:
            del self.state["sessions"][session_id]
            await self._commit(
                [
                    (
                        EVENT_SESSION_DELETED,
                        events.session_event_data(game, session, origin),
                    )
                ]
            )
            return None
        session = {**session, "ended_at": ended_at, "minutes": minutes}
        self.state["sessions"][session_id] = session
        fired: list[Event] = [
            (EVENT_SESSION_LOGGED, events.session_event_data(game, session, origin))
        ]
        fired += self._session_progress(game, session, minutes, origin)
        await self._commit(fired)
        return dict(session)

    async def delete_session(
        self, session_id: str, *, origin: str | None = None
    ) -> dict[str, Any]:
        """Delete a play session and take its minutes off the progress row."""
        session = self.session(session_id)
        game = self.game(session["game_id"])
        del self.state["sessions"][session_id]
        fired: list[Event] = [
            (EVENT_SESSION_DELETED, events.session_event_data(game, session, origin))
        ]
        if session["minutes"]:
            fired += self._session_progress(game, session, -session["minutes"], origin)
        await self._commit(fired)
        return session

    # ── Loans ────────────────────────────────────────────────────────────────

    async def add_loan(
        self, data: dict[str, Any], *, origin: str | None = None
    ) -> dict[str, Any]:
        """Start a loan.

        ``out`` lends a copy, and the copy keeps its shelf. ``in`` borrows a game.
        """
        if data.get("direction") == "out":
            copy = self.copy(str(data.get("copy_id")))
            if models.open_loan_of_copy(self.state, copy["id"]):
                raise LibraryError("copy_on_loan")
            data = {**data, "game_id": copy["game_id"]}
        loan = models.build_loan(data, today=today())
        game = self.game(loan["game_id"])
        self.state["loans"][loan["id"]] = loan
        fired: list[Event] = [
            (EVENT_LOAN_STARTED, events.loan_event_data(game, loan, origin))
        ]
        await self._commit(fired)
        return dict(loan)

    async def return_loan(
        self, loan_id: str, returned: str | None = None, *, origin: str | None = None
    ) -> dict[str, Any]:
        """Return a loan. A returned loan stays returned."""
        loan = self.loan(loan_id)
        if not models.is_open(loan):
            return loan
        loan["returned"] = models.iso_date(returned, "returned") or today()
        self.state["loans"][loan_id] = loan
        game = self.game(loan["game_id"])
        payload = events.loan_event_data(game, loan, origin)
        await self._commit([(EVENT_LOAN_RETURNED, payload)])
        return dict(loan)

    async def update_loan(
        self, loan_id: str, data: dict[str, Any], *, origin: str | None = None
    ) -> dict[str, Any]:
        """Change the party, the dates, the format or the note of a loan."""
        updated, changed = models.update_loan(self.loan(loan_id), data)
        if not changed:
            return updated
        self.state["loans"][loan_id] = updated
        payload = events.loan_updated_event_data(
            self._game_or_stub(updated["game_id"]), updated, changed, origin
        )
        await self._commit([(EVENT_LOAN_UPDATED, payload)])
        return dict(updated)

    async def delete_loan(
        self, loan_id: str, *, origin: str | None = None
    ) -> dict[str, Any]:
        """Delete a loan. The loan sync deletes its Home Keeper task."""
        loan = self.loan(loan_id)
        del self.state["loans"][loan_id]
        payload = events.loan_event_data(
            self._game_or_stub(loan["game_id"]), loan, origin
        )
        await self._commit([(EVENT_LOAN_REMOVED, payload)])
        return loan

    def _game_or_stub(self, game_id: str) -> dict[str, Any]:
        """The game, or a record with only its id, for an event payload."""
        return self.state["games"].get(game_id) or {"id": game_id}

    async def set_loan_task(self, loan_id: str, task_id: str | None) -> None:
        """Record the Home Keeper task id of a loan."""
        loan = self.state["loans"].get(loan_id)
        if loan is None or loan.get("hk_task_id") == task_id:
            return
        loan["hk_task_id"] = task_id
        await self._commit([])

    async def forget_loan_task(self, loan_id: str, *, disable: bool) -> None:
        """Clear the task id of a loan. *disable* also turns ``add_task`` off."""
        loan = self.state["loans"].get(loan_id)
        if loan is None:
            return
        loan["hk_task_id"] = None
        if disable:
            loan["add_task"] = False
        await self._commit([])

    async def fire_overdue(self, today_: str) -> list[str]:
        """Fire ``loan_overdue`` once for each loan that passed its due date."""
        fired: list[Event] = []
        ids = []
        for loan in self.state["loans"].values():
            if not models.is_overdue(loan, today_) or loan.get("overdue_fired"):
                continue
            loan["overdue_fired"] = True
            game = self._game_or_stub(loan["game_id"])
            fired.append((EVENT_LOAN_OVERDUE, events.loan_event_data(game, loan, None)))
            ids.append(loan["id"])
        if fired:
            await self._commit(fired)
        return ids

    # ── Wishlist ─────────────────────────────────────────────────────────────

    def _orphan_item(self, entry: dict[str, Any] | None) -> None:
        """Keep the to-do item of a removed wishlist entry for the sync to remove."""
        if not entry or not entry.get("todo_uid") or not entry.get("todo_entity"):
            return
        self.state["todo_orphans"].append(
            {"entity_id": entry["todo_entity"], "uid": entry["todo_uid"]}
        )

    async def add_to_wishlist(
        self,
        game_id: str,
        person_id: str,
        *,
        buy: bool = False,
        origin: str | None = None,
    ) -> dict[str, Any]:
        """Put a game on the wishlist of a person."""
        game = self.game(game_id)
        if game.get("wishlist"):
            raise LibraryError("already_on_wishlist")
        entry = models.build_wishlist(person_id, buy=buy, now=now())
        game["wishlist"] = entry
        self.state["games"][game_id] = game
        payload = events.wishlist_event_data(game, entry, origin)
        await self._commit([(EVENT_WISHLIST_ADDED, payload)])
        return dict(game)

    async def update_wishlist(
        self, game_id: str, data: dict[str, Any], *, origin: str | None = None
    ) -> dict[str, Any]:
        """Change ``buy`` or the person of a wishlist entry."""
        game = self.game(game_id)
        entry = dict(game.get("wishlist") or {})
        if not entry:
            raise LibraryError("not_on_wishlist")
        changed = []
        if (
            "buy" in data
            and (buy := models.boolean(data["buy"], "buy")) != entry["buy"]
        ):
            entry["buy"] = buy
            changed.append("buy")
        if "person_id" in data and data["person_id"] != entry["person_id"]:
            entry["person_id"] = models.text(
                data["person_id"], "person_id", models.MAX_SHORT, required=True
            )
            changed.append("person_id")
        if not changed:
            return game
        game["wishlist"] = entry
        game["updated_at"] = now()
        self.state["games"][game_id] = game
        payload = events.game_updated_event_data(game, ["wishlist"], origin)
        await self._commit([(EVENT_GAME_UPDATED, payload)])
        return dict(game)

    async def remove_from_wishlist(
        self, game_id: str, *, origin: str | None = None
    ) -> dict[str, Any]:
        """Take a game off the wishlist."""
        game = self.game(game_id)
        entry = game.get("wishlist")
        if not entry:
            raise LibraryError("not_on_wishlist")
        self._orphan_item(entry)
        game["wishlist"] = None
        self.state["games"][game_id] = game
        payload = events.wishlist_event_data(game, entry, origin)
        await self._commit([(EVENT_WISHLIST_REMOVED, payload)])
        return dict(game)

    async def got_wishlist_game(
        self, game_id: str, data: dict[str, Any], *, origin: str | None = None
    ) -> dict[str, Any]:
        """Add a copy of a wishlist game and take it off the wishlist."""
        game = self.game(game_id)
        entry = game.get("wishlist")
        if not entry:
            raise LibraryError("not_on_wishlist")
        record, _ = self._copy_record({**data, "game_id": game_id})
        self._orphan_item(entry)
        game["wishlist"] = None
        self.state["games"][game_id] = game
        self.state["copies"][record["id"]] = record
        fired: list[Event] = [
            (EVENT_COPY_ADDED, events.copy_event_data(game, record, origin)),
            (EVENT_WISHLIST_REMOVED, events.wishlist_event_data(game, entry, origin)),
        ]
        await self._commit(fired)
        return dict(record)

    async def apply_wishlist_plan(self, plan: SyncPlan) -> None:
        """Write the store steps of a wishlist sync plan."""
        fired: list[Event] = []
        games = self.state["games"]
        for bind in plan.binds:
            entry = (games.get(bind.game_id) or {}).get("wishlist")
            if entry:
                entry["todo_entity"] = bind.entity_id
                entry["todo_uid"] = bind.uid
        for bought in plan.bought:
            game = games.get(bought.game_id)
            entry = (game or {}).get("wishlist")
            if game and entry:
                entry["bought"] = True
                entry["buy"] = False
                entry["todo_uid"] = None
                entry["todo_entity"] = None
                game["updated_at"] = now()
                fired.append(
                    (
                        EVENT_GAME_UPDATED,
                        events.game_updated_event_data(game, ["wishlist"], None),
                    )
                )
        for unbind in plan.unbinds:
            game = games.get(unbind.game_id)
            entry = (game or {}).get("wishlist")
            if game and entry:
                entry["todo_uid"] = None
                entry["todo_entity"] = None
                if unbind.buy_off and entry.get("buy"):
                    entry["buy"] = False
                    game["updated_at"] = now()
                    fired.append(
                        (
                            EVENT_GAME_UPDATED,
                            events.game_updated_event_data(game, ["wishlist"], None),
                        )
                    )
        dropped = {(d.entity_id, d.uid) for d in plan.drop_orphans}
        if dropped:
            self.state["todo_orphans"] = [
                o
                for o in self.state["todo_orphans"]
                if (o["entity_id"], o["uid"]) not in dropped
            ]
        if not plan.store_changes:
            return
        await self._commit(fired)

    # ── People ───────────────────────────────────────────────────────────────

    async def set_person_settings(
        self, person_id: str, data: dict[str, Any], *, origin: str | None = None
    ) -> dict[str, Any]:
        """Change the library settings of a person."""
        current = models.person_settings(self.state["people"], person_id)
        updated, changed = models.apply_person_settings(current, data)
        if changed:
            self.state["people"][person_id] = updated
            payload = events.person_settings_event_data(person_id, changed, origin)
            await self._commit([(EVENT_PERSON_SETTINGS_UPDATED, payload)])
        return updated

    # ── Import ───────────────────────────────────────────────────────────────

    async def commit_import(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
        summary: dict[str, Any],
        *,
        person_id: str | None,
        source: str,
        origin: str | None = None,
    ) -> None:
        """Write the result of an import.

        The import planned *after* from the snapshot *before*, and other
        changes could go on in the meantime. ``models.merge_changes`` writes
        only what the plan changed into the current document. The merge and
        the new document happen with no ``await`` between them, so no other
        change can come in the middle.

        The import fires only ``import_completed``, not 1 event for each row.
        """
        self.state = models.normalize_state(
            models.merge_changes(self.state, before, after)
        )
        payload = events.import_completed_event_data(summary, person_id, source, origin)
        await self._commit([(EVENT_IMPORT_COMPLETED, payload)])

    async def commit_data_import(
        self,
        before: dict[str, Any],
        after: dict[str, Any],
        counts: dict[str, dict[str, int]],
        *,
        origin: str | None = None,
    ) -> None:
        """Write the result of a Home Keeper import of the library section.

        The plan ran on the snapshot *before*, as for :meth:`commit_import`, and
        the merge writes only what the plan changed. The import fires only
        ``data_imported``, not 1 event for each record.
        """
        self.state = models.normalize_state(
            models.merge_changes(self.state, before, after)
        )
        payload = events.data_imported_event_data(counts, origin)
        await self._commit([(EVENT_DATA_IMPORTED, payload)])
