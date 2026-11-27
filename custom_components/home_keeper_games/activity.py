"""The pure planner of the console activity listener.

A console is a media player of the PlayStation Network integration, with the
person who plays on it and the platform of the library. While the console plays
a game, the media player state is ``playing``, with the game name in
``media_title`` and the PSN title id in ``media_content_id``.

``activity_listener.py`` reads the states and calls the store. This module
decides what to do: open a session, keep it, close it, or close it and open the
next one. It also finds the game of a title. It imports no Home Assistant code.
"""

from __future__ import annotations

from typing import Any

from .models import PLATFORMS, SESSION_SOURCES, title_key

STEP_KEEP = "keep"
STEP_OPEN = "open"
STEP_CLOSE = "close"
STEP_SWITCH = "switch"

#: The states of an entity whose value is not known. A short PSN outage must not
#: split a session, so the listener waits for a known state.
UNKNOWN_STATES = ("unavailable", "unknown")

MEDIA_PLAYER_PREFIX = "media_player."

#: The platforms that a PSN console can be, in the options form.
CONSOLE_PLATFORMS = ("ps5", "ps4", "ps3", "pc")


def clean_consoles(raw: Any) -> list[dict[str, str]]:
    """The valid consoles of the options, 1 for each entity, in their order."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        entity_id = item.get("entity_id")
        person_id = item.get("person_id")
        platform = item.get("platform")
        source = item.get("source", "psn")
        if not (
            isinstance(entity_id, str)
            and entity_id.startswith(MEDIA_PLAYER_PREFIX)
            and isinstance(person_id, str)
            and person_id
            and platform in PLATFORMS
            and source in SESSION_SOURCES
            and source != "manual"
            and entity_id not in seen
        ):
            continue
        seen.add(entity_id)
        out.append(
            {
                "entity_id": entity_id,
                "person_id": person_id,
                "platform": platform,
                "source": source,
            }
        )
    return out


def now_playing(state: str | None, attributes: dict[str, Any]) -> dict[str, Any] | None:
    """``{title, title_id}`` of the game that plays, or None."""
    if state != "playing":
        return None
    title = str(attributes.get("media_title") or "").strip()
    title_id = str(attributes.get("media_content_id") or "").strip() or None
    if not title and not title_id:
        return None
    return {"title": title or str(title_id), "title_id": title_id}


def same_game(session: dict[str, Any], playing: dict[str, Any]) -> bool:
    """True if the open *session* is the game that *playing* shows."""
    if session.get("external_id") and playing.get("title_id"):
        return bool(session["external_id"] == playing["title_id"])
    return title_key(str(session.get("title") or "")) == title_key(
        str(playing.get("title") or "")
    )


def next_step(
    session: dict[str, Any] | None,
    playing: dict[str, Any] | None,
    *,
    unknown: bool,
) -> str:
    """What the listener does with the open *session* of a console.

    *session* has ``external_id`` and ``title``. *playing* is
    :func:`now_playing`. *unknown* is True for an ``unavailable`` or
    ``unknown`` state, which keeps everything as it is.
    """
    if unknown:
        return STEP_KEEP
    if session is None:
        return STEP_OPEN if playing else STEP_KEEP
    if playing is None:
        return STEP_CLOSE
    return STEP_KEEP if same_game(session, playing) else STEP_SWITCH


def match_game(
    state: dict[str, Any], playing: dict[str, Any], source: str
) -> str | None:
    """The id of the game of *playing*, or None for a game to add.

    First the game of the newest session of *source* with the same title id, so
    a game that got another title (Change IGDB game) still matches. Then the
    oldest game with the same title.
    """
    title_id = playing.get("title_id")
    games = state["games"]
    if title_id:
        newest: tuple[str, str] | None = None
        for session in state["sessions"].values():
            if not isinstance(session, dict):
                continue
            if (
                session.get("source") == source
                and session.get("external_id") == title_id
                and session.get("game_id") in games
            ):
                key = str(session.get("created_at") or "")
                if newest is None or key > newest[0]:
                    newest = (key, str(session["game_id"]))
        if newest is not None:
            return newest[1]
    wanted = title_key(str(playing.get("title") or ""))
    if not wanted:
        return None
    found = [
        game
        for game in games.values()
        if isinstance(game, dict) and title_key(str(game.get("title") or "")) == wanted
    ]
    if not found:
        return None
    found.sort(key=lambda g: (str(g.get("created_at") or ""), str(g.get("id"))))
    return str(found[0]["id"])
