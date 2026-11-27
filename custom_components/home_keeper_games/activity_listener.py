"""The Home Assistant side of the console activity listener.

The pure planner is ``activity.py``. For each console of the options, this
module watches the media player and opens or closes a play session in the
store. The open sessions are in the store, so a reload of the entry continues
them. When Home Assistant stops, each open session closes, so a restart splits a
session and loses no time.

A game that the library does not have is added with the ``add_game`` service
(with IGDB when the keys are set, else with the title only) and a digital copy
on the platform of the console.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from . import activity
from .const import CONF_CONSOLES, DOMAIN
from .models import LibraryError

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .coordinator import LibraryCoordinator

_LOGGER = logging.getLogger(__name__)
ORIGIN = "activity"


class _Track:
    """The open session of 1 console, in memory."""

    def __init__(self, console: dict[str, str]) -> None:
        self.console = console
        self.session_id: str | None = None
        # ``title`` and ``external_id`` of the open session, for same_game.
        self.session: dict[str, Any] | None = None
        # The open session came from the store at the start: its end is not known
        # if the console does not play it now.
        self.restored = False
        self.unknown_since: str | None = None


class ActivityListener:
    """Opens and closes play sessions from the console media players."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: LibraryCoordinator,
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self._lock = asyncio.Lock()
        self._tracks: dict[str, _Track] = {}
        self._unsubs: list[Callable[[], None]] = []

    @property
    def consoles(self) -> list[dict[str, str]]:
        """The valid consoles of the options."""
        return activity.clean_consoles(self._entry.options.get(CONF_CONSOLES))

    async def async_start(self) -> None:
        """Restore the open sessions and watch the consoles."""
        self._tracks = {c["entity_id"]: _Track(c) for c in self.consoles}
        if not self._tracks:
            return
        self._restore()
        self._unsubs.append(
            async_track_state_change_event(
                self._hass, list(self._tracks), self._state_changed
            )
        )
        self._unsubs.append(
            self._hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, self._on_stop)
        )
        self._unsubs.append(async_at_started(self._hass, self._check_all))

    async def _check_all(self, _hass: HomeAssistant) -> None:
        """Read each console once, when Home Assistant runs."""
        for entity_id in list(self._tracks):
            await self._handle(entity_id)

    @callback
    def async_stop(self) -> None:
        """Stop watching. The open sessions stay open in the store."""
        while self._unsubs:
            self._unsubs.pop()()
        self._tracks = {}

    def _restore(self) -> None:
        store = self._coordinator.store
        for track in self._tracks.values():
            c = track.console
            for session in store.state["sessions"].values():
                if (
                    session.get("minutes") is None
                    and session.get("source") == c["source"]
                    and session.get("person_id") == c["person_id"]
                    and session.get("platform") == c["platform"]
                ):
                    game = store.state["games"].get(session.get("game_id")) or {}
                    track.session_id = session["id"]
                    track.session = {
                        "external_id": session.get("external_id"),
                        "title": game.get("title", ""),
                    }
                    track.restored = True
                    break

    @callback
    def _state_changed(self, event: Event[Any]) -> None:
        entity_id = event.data["entity_id"]
        self._hass.async_create_task(
            self._handle(entity_id), f"{DOMAIN} activity {entity_id}"
        )

    async def _on_stop(self, _event: Event[Any]) -> None:
        async with self._lock:
            now = dt_util.utcnow().isoformat()
            for track in self._tracks.values():
                if track.session_id is not None:
                    await self._close(track, track.unknown_since or now)

    async def _handle(self, entity_id: str) -> None:
        async with self._lock:
            track = self._tracks.get(entity_id)
            if track is None:
                return
            state = self._hass.states.get(entity_id)
            value = state.state if state else None
            attributes = dict(state.attributes) if state else {}
            unknown = state is None or value in activity.UNKNOWN_STATES
            playing = activity.now_playing(value, attributes)
            now = dt_util.utcnow().isoformat()
            step = activity.next_step(track.session, playing, unknown=unknown)
            if unknown:
                if track.session_id is not None and track.unknown_since is None:
                    track.unknown_since = now
                return
            ended_at = track.unknown_since or now
            track.unknown_since = None
            if step == activity.STEP_KEEP:
                track.restored = False
                return
            if step in (activity.STEP_CLOSE, activity.STEP_SWITCH):
                await self._close(track, ended_at)
            if step in (activity.STEP_OPEN, activity.STEP_SWITCH) and playing:
                await self._open(track, playing, now)

    async def _close(self, track: _Track, ended_at: str) -> None:
        store = self._coordinator.store
        session_id, restored = track.session_id, track.restored
        track.session_id, track.session, track.restored = None, None, False
        if session_id is None or session_id not in store.state["sessions"]:
            return
        try:
            if restored:
                # A session from before a crash: its end is not known.
                await store.delete_session(session_id, origin=ORIGIN)
            else:
                await store.end_session(session_id, ended_at, origin=ORIGIN)
        except (HomeAssistantError, LibraryError) as err:
            _LOGGER.warning("Cannot close the play session %s: %s", session_id, err)

    async def _open(self, track: _Track, playing: dict[str, Any], now: str) -> None:
        c = track.console
        store = self._coordinator.store
        try:
            game_id = activity.match_game(store.state, playing, c["source"])
            if game_id is None:
                game_id = await self._add_game(playing["title"], c["platform"])
            session = await store.start_session(
                game_id=game_id,
                person_id=c["person_id"],
                platform=c["platform"],
                source=c["source"],
                external_id=playing.get("title_id"),
                started_at=now,
                origin=ORIGIN,
            )
        except (HomeAssistantError, LibraryError) as err:
            _LOGGER.warning("Cannot start a play session of %s: %s", playing, err)
            return
        track.session_id = session["id"]
        track.session = {
            "external_id": session["external_id"],
            "title": playing["title"],
        }
        track.restored = False

    async def _add_game(self, title: str, platform: str) -> str:
        """Add the game with IGDB if it can, else with the title only."""
        try:
            reply = await self._call(
                "add_game", {"title": title, "lookup": True, "platform": platform}
            )
        except HomeAssistantError:
            reply = await self._call(
                "add_game", {"title": title, "needs_details": True}
            )
        game = reply["game"]
        if not reply.get("existing"):
            await self._call(
                "add_copy",
                {"game_id": game["id"], "platform": platform, "format": "digital"},
            )
        return str(game["id"])

    async def _call(self, service: str, data: dict[str, Any]) -> dict[str, Any]:
        reply = await self._hass.services.async_call(
            DOMAIN, service, data, blocking=True, return_response=True
        )
        return dict(reply or {})
