"""Unit tests for the console activity planner and the live session models."""

from __future__ import annotations

import ex.activity as a
import ex.models as m
import pytest

NOW = "2026-10-05T12:00:00+00:00"
TODAY = "2026-10-05"
PS5 = "media_player.ps5"


def _console(**data) -> dict:
    return {"entity_id": PS5, "person_id": "alice", "platform": "ps5", **data}


def test_clean_consoles_keeps_the_valid_ones_once() -> None:
    raw = [
        _console(),
        _console(person_id="bob"),
        _console(entity_id="sensor.ps5"),
        _console(entity_id="media_player.ps4", person_id=""),
        _console(entity_id="media_player.ps4", platform="dreamcast"),
        _console(entity_id="media_player.ps4", source="manual"),
        _console(entity_id="media_player.ps4", source="steam"),
        "not a console",
        _console(entity_id="media_player.ps4", platform="ps4", source="psn"),
    ]
    assert a.clean_consoles(raw) == [
        {"entity_id": PS5, "person_id": "alice", "platform": "ps5", "source": "psn"},
        {
            "entity_id": "media_player.ps4",
            "person_id": "alice",
            "platform": "ps4",
            "source": "psn",
        },
    ]
    assert a.clean_consoles(None) == []
    assert a.clean_consoles({"entity_id": PS5}) == []
    assert a.clean_consoles([_console(entity_id=5)]) == []
    assert a.clean_consoles([_console(person_id=None)]) == []


def test_now_playing() -> None:
    attrs = {"media_title": " Hades ", "media_content_id": " PPSA01 "}
    assert a.now_playing("playing", attrs) == {"title": "Hades", "title_id": "PPSA01"}
    assert a.now_playing("on", attrs) is None
    assert a.now_playing("playing", {}) is None
    assert a.now_playing("playing", {"media_title": "Hades"}) == {
        "title": "Hades",
        "title_id": None,
    }
    assert a.now_playing("playing", {"media_content_id": "PPSA01"}) == {
        "title": "PPSA01",
        "title_id": "PPSA01",
    }


def test_same_game() -> None:
    session = {"external_id": "PPSA01", "title": "Hades"}
    assert a.same_game(session, {"title": "Other", "title_id": "PPSA01"})
    assert not a.same_game(session, {"title": "Hades", "title_id": "PPSA02"})
    no_id = {"external_id": None, "title": "Hades"}
    assert a.same_game(no_id, {"title": "HADES", "title_id": "PPSA02"})
    assert not a.same_game(no_id, {"title": "Celeste", "title_id": None})
    assert a.same_game(session, {"title": "hades", "title_id": None})


@pytest.mark.parametrize(
    ("session", "playing", "unknown", "step"),
    [
        (None, None, False, a.STEP_KEEP),
        (None, {"title": "Hades", "title_id": "A"}, False, a.STEP_OPEN),
        ({"external_id": "A"}, None, False, a.STEP_CLOSE),
        ({"external_id": "A"}, {"title": "x", "title_id": "A"}, False, a.STEP_KEEP),
        ({"external_id": "A"}, {"title": "x", "title_id": "B"}, False, a.STEP_SWITCH),
        ({"external_id": "A"}, None, True, a.STEP_KEEP),
        (None, {"title": "Hades", "title_id": "A"}, True, a.STEP_KEEP),
    ],
)
def test_next_step(session, playing, unknown, step) -> None:
    assert a.next_step(session, playing, unknown=unknown) == step


def _state() -> dict:
    state = m.empty_state()
    state["games"] = {
        "g1": {"id": "g1", "title": "Hades", "created_at": "2026-01-02"},
        "g2": {"id": "g2", "title": "HADES", "created_at": "2026-01-01"},
        "g3": {"id": "g3", "title": "Renamed", "created_at": "2026-01-03"},
        "bad": "not a game",
    }
    state["sessions"] = {
        "s1": {
            "source": "psn",
            "external_id": "PPSA01",
            "game_id": "g1",
            "created_at": "2026-02-01",
        },
        "s2": {
            "source": "psn",
            "external_id": "PPSA01",
            "game_id": "g3",
            "created_at": "2026-03-01",
        },
        "s3": {
            "source": "psn",
            "external_id": "PPSA01",
            "game_id": "gone",
            "created_at": "2026-04-01",
        },
        "s4": {
            "source": "manual",
            "external_id": "PPSA09",
            "game_id": "g1",
            "created_at": "2026-05-01",
        },
        "bad": "not a session",
    }
    return state


def test_match_game_by_title_id_then_title() -> None:
    state = _state()
    # The newest psn session with this title id whose game is still there.
    assert a.match_game(state, {"title": "x", "title_id": "PPSA01"}, "psn") == "g3"
    # A manual session does not count for the psn source.
    assert a.match_game(state, {"title": "nope", "title_id": "PPSA09"}, "psn") is None
    # The oldest game with the same title.
    assert a.match_game(state, {"title": "hades", "title_id": "NEW"}, "psn") == "g2"
    assert a.match_game(state, {"title": "hades", "title_id": None}, "psn") == "g2"
    assert a.match_game(state, {"title": "", "title_id": None}, "psn") is None
    assert a.match_game(state, {"title": "Celeste", "title_id": None}, "psn") is None


def test_build_live_session_shape() -> None:
    session = m.build_live_session(
        game_id="g1",
        person_id="alice",
        platform="ps5",
        source="psn",
        external_id="PPSA01",
        started_at=NOW,
    )
    assert session == {
        "id": session["id"],
        "person_id": "alice",
        "game_id": "g1",
        "platform": "ps5",
        "source": "psn",
        "external_id": "PPSA01",
        "started_at": NOW,
        "ended_at": None,
        "date": TODAY,
        "minutes": None,
        "created_at": NOW,
    }
    blank = m.build_live_session(
        game_id="g1",
        person_id="alice",
        platform="ps5",
        source="psn",
        external_id="",
        started_at=NOW,
    )
    assert blank["external_id"] is None
    with pytest.raises(m.LibraryError):
        m.build_live_session(
            game_id="g1",
            person_id="alice",
            platform="ps5",
            source="steam",
            external_id=None,
            started_at=NOW,
        )
    with pytest.raises(m.LibraryError):
        m.build_live_session(
            game_id="g1",
            person_id="alice",
            platform="atari",
            source="psn",
            external_id=None,
            started_at=NOW,
        )


def test_session_minutes() -> None:
    start = "2026-10-05T12:00:00+00:00"
    assert m.session_minutes(start, "2026-10-05T12:59:59+00:00") == 59
    assert m.session_minutes(start, "2026-10-05T13:00:00+00:00") == 60
    assert m.session_minutes(start, "2026-10-05T14:00:00+02:00") == 0
    assert m.session_minutes(start, "2026-10-05T11:00:00+00:00") == 0
    assert m.session_minutes("", start) == 0
    assert m.session_minutes(start, "soon") == 0
    assert m.session_minutes("2000-01-01T00:00:00+00:00", start) == m.MAX_PLAYTIME


def test_session_start_progress() -> None:
    row, changed = m.session_start_progress(None, TODAY, now=NOW, today=TODAY)
    assert row["play_status"] == "playing"
    assert row["started_at"] == TODAY and row["last_played_at"] == TODAY
    assert row["playtime_minutes"] is None
    assert changed == ["play_status", "started_at", "last_played_at"]
    done = {
        **m.empty_progress(now="x"),
        "play_status": "completed",
        "last_played_at": "2026-10-09",
    }
    same, changed = m.session_start_progress(done, TODAY, now=NOW, today=TODAY)
    assert (same, changed) == (done, [])
    backlog = {**m.empty_progress(now="x"), "started_at": "2026-01-01"}
    row, changed = m.session_start_progress(backlog, TODAY, now=NOW, today=TODAY)
    assert row["play_status"] == "playing" and row["started_at"] == "2026-01-01"
    assert changed == ["play_status", "last_played_at"]
