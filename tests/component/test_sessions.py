"""Component tests: the play session services, their gates and their events."""

from __future__ import annotations

import pytest
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from pytest_homeassistant_custom_component.common import async_capture_events

ALICE = "p_alice"
BOB = "p_bob"
CAROL = "p_carol"
EVENT = "home_keeper_games_{}".format


async def _game(call) -> dict:
    game = (await call("add_game", {"title": "Hades"}))["game"]
    await call("add_copy", {"game_id": game["id"], "platform": "ps5"})
    return game


async def test_log_session_adds_play_time_and_fires_events(
    hass, setup_entry, call
) -> None:
    game = await _game(call)
    logged = async_capture_events(hass, EVENT("session_logged"))
    changed = async_capture_events(hass, EVENT("progress_changed"))
    updated = async_capture_events(hass, EVENT("progress_updated"))
    reply = await call(
        "log_session",
        {"game_id": game["id"], "minutes": 45, "date": "2026-10-01"},
        as_="user",
    )
    session = reply["session"]
    assert (session["person_id"], session["platform"]) == (BOB, "ps5")
    assert (session["source"], session["minutes"]) == ("manual", 45)
    progress = reply["progress"]
    assert progress["play_status"] == "playing"
    assert progress["playtime_minutes"] == 45
    assert progress["last_played_at"] == "2026-10-01"
    assert logged[0].data == {
        "game_id": game["id"],
        "title": "Hades",
        "person_id": BOB,
        "origin": None,
        "session_id": session["id"],
        "platform": "ps5",
        "source": "manual",
        "date": "2026-10-01",
        "minutes": 45,
    }
    assert changed[0].data["play_status"] == "playing"
    await call(
        "log_session",
        {"game_id": game["id"], "minutes": 30, "date": "2026-09-01"},
        as_="user",
    )
    assert updated[-1].data["changed_fields"] == ["playtime_minutes"]
    row = setup_entry.runtime_data.store.progress_row(BOB, game["id"], "ps5")
    assert row["playtime_minutes"] == 75 and row["last_played_at"] == "2026-10-01"
    assert len(changed) == 1


async def test_log_session_gates_and_errors(hass, setup_entry, call) -> None:
    game = await _game(call)
    data = {"game_id": game["id"], "minutes": 10}
    with pytest.raises(Unauthorized):
        await call("log_session", {**data, "person_id": ALICE}, as_="user")
    reply = await call("log_session", {**data, "person_id": CAROL})
    assert reply["session"]["person_id"] == CAROL
    with pytest.raises(ServiceValidationError) as info:
        await call("log_session", data, as_=None)
    assert info.value.translation_key == "no_person"
    with pytest.raises(ServiceValidationError) as info:
        await call("log_session", {**data, "minutes": 0}, as_="user")
    assert info.value.translation_key == "out_of_range"
    with pytest.raises(ServiceValidationError) as info:
        await call("log_session", {**data, "game_id": "nope"}, as_="user")
    assert info.value.translation_key == "game_not_found"


async def test_delete_session_takes_the_minutes_off(hass, setup_entry, call) -> None:
    game = await _game(call)
    data = {"game_id": game["id"], "minutes": 20}
    mine = (await call("log_session", data, as_="user"))["session"]
    other = (await call("log_session", {**data, "person_id": CAROL}))["session"]
    deleted = async_capture_events(hass, EVENT("session_deleted"))
    with pytest.raises(Unauthorized):
        await call("delete_session", {"session_id": other["id"]}, as_="user")
    reply = await call("delete_session", {"session_id": mine["id"]}, as_="user")
    assert reply["session"]["id"] == mine["id"]
    assert deleted[0].data["session_id"] == mine["id"]
    assert deleted[0].data["minutes"] == 20
    row = setup_entry.runtime_data.store.progress_row(BOB, game["id"], "ps5")
    assert row["playtime_minutes"] == 0 and row["play_status"] == "playing"
    await call("delete_session", {"session_id": other["id"]})
    with pytest.raises(ServiceValidationError) as info:
        await call("delete_session", {"session_id": other["id"]})
    assert info.value.translation_key == "session_not_found"


async def test_delete_session_of_a_removed_row_keeps_no_row(
    hass, setup_entry, call
) -> None:
    game = await _game(call)
    session = (
        await call("log_session", {"game_id": game["id"], "minutes": 5}, as_="user")
    )["session"]
    await call(
        "set_progress",
        {"game_id": game["id"], "platform": "ps5", "play_status": "none"},
        as_="user",
    )
    await call("delete_session", {"session_id": session["id"]}, as_="user")
    store = setup_entry.runtime_data.store
    assert store.progress_row(BOB, game["id"], "ps5") is None


async def test_list_sessions_follows_the_progress_privacy(
    hass, setup_entry, call
) -> None:
    game = await _game(call)
    for person, day in ((BOB, "2026-10-01"), (CAROL, "2026-10-02")):
        await call(
            "log_session",
            {"game_id": game["id"], "minutes": 15, "date": day, "person_id": person},
        )
    rows = (await call("list_sessions", {}, as_="user"))["sessions"]
    assert [r["person_id"] for r in rows] == [CAROL, BOB]
    assert rows[0]["title"] == "Hades"
    await call("set_person_settings", {"person_id": CAROL, "share_progress": False})
    rows = (await call("list_sessions", {}, as_="user"))["sessions"]
    assert [r["person_id"] for r in rows] == [BOB]
    rows = (await call("list_sessions", {"person_id": CAROL}))["sessions"]
    assert [r["person_id"] for r in rows] == [CAROL]
    rows = (await call("list_sessions", {"limit": 1}))["sessions"]
    assert len(rows) == 1
    rows = (await call("list_sessions", {"game_id": "other"}))["sessions"]
    assert rows == []


async def test_deleting_a_game_deletes_its_sessions(hass, setup_entry, call) -> None:
    game = await _game(call)
    await call("log_session", {"game_id": game["id"], "minutes": 5}, as_="user")
    await call("delete_game", {"game_id": game["id"]})
    assert setup_entry.runtime_data.store.state["sessions"] == {}
