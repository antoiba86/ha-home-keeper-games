"""Unit tests for play sessions: the record, the play time and the privacy."""

from __future__ import annotations

import ex.events as ev
import ex.models as m
import ex.projections as pr
import pytest

NOW = "2026-10-05T12:00:00+00:00"
TODAY = "2026-10-05"


def _err(fn, *args, **kwargs) -> m.LibraryError:
    with pytest.raises(m.LibraryError) as info:
        fn(*args, **kwargs)
    return info.value


def _build(**data) -> dict:
    return m.build_session(
        {"game_id": "g1", "minutes": 45, **data},
        person_id="alice",
        platform="ps5",
        now=NOW,
        today=TODAY,
    )


def test_build_session_shape() -> None:
    session = _build(date="2026-10-01")
    assert session == {
        "id": session["id"],
        "person_id": "alice",
        "game_id": "g1",
        "platform": "ps5",
        "source": "manual",
        "external_id": None,
        "started_at": None,
        "ended_at": None,
        "date": "2026-10-01",
        "minutes": 45,
        "created_at": NOW,
    }
    assert len(session["id"]) == 32
    assert _build()["date"] == TODAY
    assert _build(minutes="30")["minutes"] == 30
    assert _build(minutes=1440)["minutes"] == 1440


@pytest.mark.parametrize(
    ("data", "key", "placeholders"),
    [
        ({"minutes": None}, "field_required", {"field": "minutes"}),
        (
            {"minutes": 0},
            "out_of_range",
            {"field": "minutes", "low": "1", "high": "1440"},
        ),
        (
            {"minutes": 1441},
            "out_of_range",
            {"field": "minutes", "low": "1", "high": "1440"},
        ),
        ({"date": "soon"}, "invalid_date", {"field": "date"}),
    ],
)
def test_build_session_refuses(data, key, placeholders) -> None:
    err = _err(_build, **data)
    assert (err.key, err.placeholders) == (key, placeholders)


def test_build_session_refuses_an_unknown_platform() -> None:
    err = _err(
        m.build_session,
        {"game_id": "g1", "minutes": 5},
        person_id="alice",
        platform="dreamcast",
        now=NOW,
        today=TODAY,
    )
    assert err.key == "invalid_choice" and err.placeholders["field"] == "platform"


def _progress(row, minutes, day="2026-10-01"):
    return m.session_progress(row, minutes, day, now=NOW, today=TODAY)


def test_a_session_starts_a_new_row() -> None:
    row, changed = _progress(None, 45)
    assert row["play_status"] == "playing"
    assert row["playtime_minutes"] == 45
    assert row["started_at"] == "2026-10-01"
    assert row["last_played_at"] == "2026-10-01"
    assert row["updated_at"] == NOW
    assert changed == [
        "play_status",
        "playtime_minutes",
        "started_at",
        "last_played_at",
    ]


def test_a_session_moves_backlog_to_playing_and_keeps_its_start() -> None:
    backlog = {**m.empty_progress(now="x"), "started_at": "2026-01-01"}
    row, changed = _progress(backlog, 10)
    assert row["play_status"] == "playing"
    assert row["started_at"] == "2026-01-01"
    assert "started_at" not in changed and "play_status" in changed


def test_a_session_keeps_a_completed_status_and_a_later_date() -> None:
    done = {
        **m.empty_progress(now="x"),
        "play_status": "completed",
        "playtime_minutes": 100,
        "last_played_at": "2026-10-03",
    }
    row, changed = _progress(done, 20, day="2026-10-01")
    assert row["play_status"] == "completed"
    assert row["playtime_minutes"] == 120
    assert row["last_played_at"] == "2026-10-03"
    assert changed == ["playtime_minutes"]
    row, changed = _progress(done, 20, day="2026-10-04")
    assert row["last_played_at"] == "2026-10-04"
    assert changed == ["playtime_minutes", "last_played_at"]


def test_a_deleted_session_takes_minutes_off_down_to_0() -> None:
    row = {
        **m.empty_progress(now="x"),
        "play_status": "backlog",
        "playtime_minutes": 30,
        "last_played_at": "2026-09-01",
    }
    after, changed = _progress(row, -20, day="2026-10-04")
    assert after["playtime_minutes"] == 10
    assert after["play_status"] == "backlog"
    assert after["last_played_at"] == "2026-09-01"
    assert changed == ["playtime_minutes"]
    after, _ = _progress(row, -50)
    assert after["playtime_minutes"] == 0


def test_play_time_stops_at_the_maximum() -> None:
    row = {**m.empty_progress(now="x"), "playtime_minutes": m.MAX_PLAYTIME}
    after, changed = _progress(row, 5)
    assert after["playtime_minutes"] == m.MAX_PLAYTIME
    assert "playtime_minutes" not in changed


def _state() -> dict:
    state = m.empty_state()
    state["games"]["g1"] = {"id": "g1", "title": "Hades"}
    state["games"]["g2"] = {"id": "g2", "title": "Celeste"}
    rows = [
        ("s1", "alice", "g1", "2026-10-01", "2026-10-01T10:00:00+00:00"),
        ("s2", "bob", "g1", "2026-10-03", "2026-10-03T10:00:00+00:00"),
        ("s3", "alice", "g2", "2026-10-03", "2026-10-03T11:00:00+00:00"),
        ("s4", "carol", "g2", "2026-09-01", "2026-09-01T10:00:00+00:00"),
        ("gone", "bob", "g9", "2026-08-01", "2026-08-01T10:00:00+00:00"),
    ]
    for sid, person, game, day, created in rows:
        state["sessions"][sid] = {
            "id": sid,
            "person_id": person,
            "game_id": game,
            "platform": "ps5",
            "source": "manual",
            "started_at": None,
            "ended_at": None,
            "date": day,
            "minutes": 10,
            "created_at": created,
        }
    state["sessions"]["bad"] = "not a record"
    state["people"]["carol"] = {"share_progress": False}
    return state


def test_sessions_of_filters_and_sorts_the_newest_first() -> None:
    state = _state()
    ids = [s["id"] for s in m.sessions_of(state)]
    assert ids == ["s3", "s2", "s1", "s4", "gone"]
    assert [s["id"] for s in m.sessions_of(state, game_id="g1")] == ["s2", "s1"]
    assert [s["id"] for s in m.sessions_of(state, person_id="alice")] == ["s3", "s1"]
    assert m.sessions_of(state, game_id="g2", person_id="bob") == []


def _visible(viewer, is_admin=False, limit=50, **filters) -> list[str]:
    rows = pr.visible_sessions(
        _state(), viewer=viewer, is_admin=is_admin, limit=limit, **filters
    )
    return [r["id"] for r in rows]


def test_visible_sessions_follow_the_progress_privacy() -> None:
    # Carol does not share: only Carol and an admin read her session.
    assert _visible("alice") == ["s3", "s2", "s1", "gone"]
    assert _visible("carol") == ["s3", "s2", "s1", "s4", "gone"]
    assert _visible(None, is_admin=True) == ["s3", "s2", "s1", "s4", "gone"]
    assert _visible("alice", person_id="carol") == []
    assert _visible("alice", limit=2) == ["s3", "s2"]
    assert _visible("alice", is_admin=True, limit=1, game_id="g2") == ["s3"]


def test_visible_sessions_add_the_title_and_copy_the_record() -> None:
    state = _state()
    rows = pr.visible_sessions(state, viewer="alice", is_admin=False, limit=50)
    assert rows[0]["title"] == "Celeste"
    assert rows[-1]["title"] == ""
    rows[0]["minutes"] = 99
    assert state["sessions"]["s3"]["minutes"] == 10
    assert "title" not in state["sessions"]["s3"]


def test_session_event_data() -> None:
    session = _build(date="2026-10-01")
    data = ev.session_event_data({"id": "g1", "title": "Hades"}, session, "bot")
    assert data == {
        "game_id": "g1",
        "title": "Hades",
        "person_id": "alice",
        "origin": "bot",
        "session_id": session["id"],
        "platform": "ps5",
        "source": "manual",
        "date": "2026-10-01",
        "minutes": 45,
    }
