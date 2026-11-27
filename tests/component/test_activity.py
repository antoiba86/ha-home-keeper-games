"""Component tests: the console activity listener and the consoles options step."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.home_keeper_games.const import CONF_CONSOLES, CONF_CURRENCY

BOB = "p_bob"
PS5 = "media_player.ps5"
EVENT = "home_keeper_games_{}".format
HADES = {"media_title": "Hades", "media_content_id": "PPSA01"}


async def _watch(hass, entry, *consoles: dict) -> None:
    rows = consoles or ({"entity_id": PS5, "person_id": BOB, "platform": "ps5"},)
    options = {**entry.options, CONF_CONSOLES: [{**c, "source": "psn"} for c in rows]}
    hass.config_entries.async_update_entry(entry, options=options)
    await hass.async_block_till_done()


async def _set(hass, state: str, attributes: dict | None = None) -> None:
    hass.states.async_set(PS5, state, attributes or {})
    await hass.async_block_till_done()


def _sessions(entry) -> list[dict]:
    return list(entry.runtime_data.store.state["sessions"].values())


def _games(entry) -> list[dict]:
    return list(entry.runtime_data.store.state["games"].values())


async def test_a_game_on_the_console_is_a_session(hass, setup_entry, freezer) -> None:
    started = async_capture_events(hass, EVENT("session_started"))
    logged = async_capture_events(hass, EVENT("session_logged"))
    await _set(hass, "on")
    await _watch(hass, setup_entry)
    await _set(hass, "playing", HADES)
    [game] = _games(setup_entry)
    assert (game["title"], game["needs_details"]) == ("Hades", True)
    [copy] = setup_entry.runtime_data.store.state["copies"].values()
    assert (copy["platform"], copy["format"]) == ("ps5", "digital")
    [session] = _sessions(setup_entry)
    assert (session["source"], session["external_id"]) == ("psn", "PPSA01")
    assert session["minutes"] is None and session["person_id"] == BOB
    assert started[0].data["session_id"] == session["id"]
    store = setup_entry.runtime_data.store
    assert store.progress_row(BOB, game["id"], "ps5")["play_status"] == "playing"
    freezer.tick(timedelta(minutes=30))
    await _set(hass, "playing", HADES)
    freezer.tick(timedelta(minutes=15))
    await _set(hass, "on")
    [session] = _sessions(setup_entry)
    assert session["minutes"] == 45 and session["ended_at"] is not None
    assert logged[0].data["minutes"] == 45
    assert store.progress_row(BOB, game["id"], "ps5")["playtime_minutes"] == 45


async def test_an_outage_keeps_the_session_and_ends_it_at_its_start(
    hass, setup_entry, freezer
) -> None:
    await _watch(hass, setup_entry)
    await _set(hass, "playing", HADES)
    freezer.tick(timedelta(minutes=20))
    await _set(hass, "unavailable")
    freezer.tick(timedelta(minutes=50))
    await _set(hass, "playing", HADES)
    [session] = _sessions(setup_entry)
    assert session["minutes"] is None
    freezer.tick(timedelta(minutes=10))
    await _set(hass, "unknown")
    freezer.tick(timedelta(minutes=90))
    await _set(hass, "off")
    [session] = _sessions(setup_entry)
    # 20 + 50 + 10: the end is the start of the last outage.
    assert session["minutes"] == 80


async def test_a_new_game_switches_and_a_known_title_matches(
    hass, setup_entry, call, freezer
) -> None:
    celeste = (await call("add_game", {"title": "Celeste"}))["game"]
    await _watch(hass, setup_entry)
    await _set(hass, "playing", HADES)
    freezer.tick(timedelta(minutes=5))
    await _set(hass, "playing", {"media_title": "celeste", "media_content_id": "X2"})
    first, second = sorted(_sessions(setup_entry), key=lambda s: s["created_at"])
    assert first["minutes"] == 5 and second["minutes"] is None
    assert second["game_id"] == celeste["id"]
    # A game that the library has gets no new copy.
    copies = setup_entry.runtime_data.store.state["copies"].values()
    assert [c["game_id"] for c in copies] != [celeste["id"]]
    freezer.tick(timedelta(seconds=30))
    await _set(hass, "off")
    # Under 1 minute: the session is gone.
    assert [s["id"] for s in _sessions(setup_entry)] == [first["id"]]


async def test_a_renamed_game_matches_by_title_id(
    hass, setup_entry, call, freezer
) -> None:
    await _watch(hass, setup_entry)
    await _set(hass, "playing", HADES)
    freezer.tick(timedelta(minutes=3))
    await _set(hass, "off")
    [game] = _games(setup_entry)
    await call("update_game", {"game_id": game["id"], "title": "Hades (2020)"})
    await _set(hass, "playing", HADES)
    assert len(_games(setup_entry)) == 1
    assert {s["game_id"] for s in _sessions(setup_entry)} == {game["id"]}


async def test_a_reload_continues_and_a_stop_closes(hass, setup_entry, freezer) -> None:
    await _watch(hass, setup_entry)
    await _set(hass, "playing", HADES)
    [open_session] = _sessions(setup_entry)
    freezer.tick(timedelta(minutes=10))
    assert await hass.config_entries.async_reload(setup_entry.entry_id)
    await hass.async_block_till_done()
    [session] = _sessions(setup_entry)
    assert session["id"] == open_session["id"] and session["minutes"] is None
    freezer.tick(timedelta(minutes=5))
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
    await hass.async_block_till_done()
    [session] = _sessions(setup_entry)
    assert session["minutes"] == 15


async def test_an_open_session_of_a_crash_is_deleted(
    hass, setup_entry, freezer
) -> None:
    await _watch(hass, setup_entry)
    await _set(hass, "playing", HADES)
    freezer.tick(timedelta(minutes=10))
    # The console stops while the listener is off, as after a crash.
    setup_entry.runtime_data.activity.async_stop()
    await _set(hass, "off")
    await setup_entry.runtime_data.activity.async_start()
    await hass.async_block_till_done()
    assert _sessions(setup_entry) == []


async def test_other_entities_and_no_consoles_do_nothing(hass, setup_entry) -> None:
    await _set(hass, "playing", HADES)
    await _watch(
        hass,
        setup_entry,
        {"entity_id": "media_player.tv", "person_id": BOB, "platform": "ps5"},
    )
    await _set(hass, "playing", HADES)
    assert _sessions(setup_entry) == [] and _games(setup_entry) == []


async def test_options_add_keep_and_remove_a_console(hass, setup_entry) -> None:
    flows = hass.config_entries.options
    result = await flows.async_init(setup_entry.entry_id)
    result = await flows.async_configure(result["flow_id"], {CONF_CURRENCY: "eur"})
    assert result["step_id"] == "consoles"
    result = await flows.async_configure(result["flow_id"], {"entity_id": PS5})
    assert result["errors"] == {"base": "console_incomplete"}
    result = await flows.async_configure(
        result["flow_id"], {"entity_id": PS5, "person_id": BOB, "platform": "ps4"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert setup_entry.options[CONF_CURRENCY] == "EUR"
    assert setup_entry.options[CONF_CONSOLES] == [
        {"entity_id": PS5, "person_id": BOB, "platform": "ps4", "source": "psn"}
    ]
    result = await flows.async_init(setup_entry.entry_id)
    result = await flows.async_configure(result["flow_id"], {CONF_CURRENCY: "EUR"})
    result = await flows.async_configure(
        result["flow_id"], {"keep": [PS5], "entity_id": PS5, "person_id": BOB}
    )
    assert result["errors"] == {"base": "console_exists"}
    result = await flows.async_configure(result["flow_id"], {"keep": []})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert setup_entry.options[CONF_CONSOLES] == []
