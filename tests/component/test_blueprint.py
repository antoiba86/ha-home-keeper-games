"""Component tests: the Telegram blueprint in a real Home Assistant.

The test copies ``blueprints/automation/home_keeper_games/telegram_add_game.yaml``
into the config dir, sets up an automation from it, and fires the events of the
Telegram bot integration. Fake ``telegram_bot`` actions keep each reply, and
``aioclient_mock`` is a fake IGDB.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)

from custom_components.home_keeper_games.const import (
    IGDB_API_URL,
    IGDB_IMAGES_URL,
    IGDB_TOKEN_URL,
)

BLUEPRINT = (
    Path(__file__).resolve().parents[2]
    / "blueprints"
    / "automation"
    / "home_keeper_games"
    / "telegram_add_game.yaml"
)
CHAT = 42
HADES = {"id": 113112, "name": "Hades", "platforms": [6, 130]}
KEYS = {"igdb_client_id": "cid", "igdb_client_secret": "secret"}

pytestmark = pytest.mark.skipif(
    tuple(int(p) for p in HA_VERSION.split(".")[:2]) < (2026, 3),
    reason="the blueprint needs Home Assistant 2026.3 or later",
)


@pytest.fixture
def telegram(hass) -> dict[str, list[dict]]:
    """Fake telegram_bot actions. Each list keeps the data of each call."""
    calls: dict[str, list[dict]] = {
        "send_message": [],
        "answer_callback_query": [],
        "edit_message": [],
    }
    for name, kept in calls.items():

        async def _keep(call, kept=kept) -> None:
            kept.append(dict(call.data))

        hass.services.async_register("telegram_bot", name, _keep)
    return calls


@pytest.fixture
def igdb(aioclient_mock) -> None:
    """A fake IGDB: each search finds Hades."""

    async def games(method, url, data):
        found = [HADES] if data.decode().lower().startswith('search "hades"') else []
        return AiohttpClientMockResponse(method, url, json=found)

    token = {"access_token": "tok", "expires_in": 5000000, "token_type": "bearer"}
    aioclient_mock.post(IGDB_TOKEN_URL, json=token)
    aioclient_mock.post(f"{IGDB_API_URL}/games", side_effect=games)
    aioclient_mock.get(f"{IGDB_IMAGES_URL}/t_cover_big/x.jpg", status=404)


async def _automation(hass, **inputs) -> None:
    folder = Path(hass.config.path("blueprints/automation/home_keeper_games"))
    await hass.async_add_executor_job(lambda: folder.mkdir(parents=True, exist_ok=True))
    await hass.async_add_executor_job(shutil.copy, BLUEPRINT, folder / BLUEPRINT.name)
    config = {
        "automation": {
            "use_blueprint": {
                "path": f"home_keeper_games/{BLUEPRINT.name}",
                "input": {"chat_ids": [str(CHAT)], **inputs},
            }
        }
    }
    assert await async_setup_component(hass, "automation", config)
    await hass.async_block_till_done()


async def _command(hass, *args: str, chat: int = CHAT, command="/juego") -> None:
    data = {"command": command, "args": list(args), "chat_id": chat}
    hass.bus.async_fire("telegram_command", data)
    await hass.async_block_till_done()


async def _button(hass, data: str, text: str = "Added: X") -> None:
    message = {"message_id": 7, "text": text}
    event = {"id": "cb1", "data": data, "chat_id": CHAT, "message": message}
    hass.bus.async_fire("telegram_callback", event)
    await hass.async_block_till_done()


def _games(entry) -> list[dict]:
    return list(entry.runtime_data.store.state["games"].values())


def _copies(entry) -> list[dict]:
    return list(entry.runtime_data.store.state["copies"].values())


async def test_a_title_and_a_platform_add_the_igdb_game_and_a_copy(
    hass, setup_entry, call, telegram, igdb
) -> None:
    hass.config_entries.async_update_entry(setup_entry, data=dict(KEYS))
    room = (await call("add_room", {"name": "Living room"}))["room"]
    unit = (await call("add_unit", {"room_id": room["id"], "name": "TV"}))["unit"]
    shelf = (await call("add_shelf", {"unit_id": unit["id"], "name": "Top"}))["shelf"]
    await _automation(hass, shelf_id=shelf["id"], ha_url=" https://home.example.org/ ")
    await _command(hass, "hades", "PC")
    [game] = _games(setup_entry)
    assert game["title"] == "Hades"
    assert game["igdb_id"] == 113112
    assert game["needs_details"] is False
    [copy] = _copies(setup_entry)
    assert copy["game_id"] == game["id"]
    assert (copy["platform"], copy["format"]) == ("pc", "physical")
    assert copy["shelf_id"] == shelf["id"]
    [reply] = telegram["send_message"]
    assert reply["chat_id"] == CHAT
    assert reply["parse_mode"] == "plain_text"
    assert reply["message"] == "Added: Hades (PC)"
    assert reply["inline_keyboard"] == [
        f"Undo:/hkg_g {game['id']},"
        f"Edit:https://home.example.org/home-keeper/games/games/{game['id']}"
    ]


async def test_a_2_word_platform_and_no_igdb_match(
    hass, setup_entry, telegram, igdb
) -> None:
    hass.config_entries.async_update_entry(setup_entry, data=dict(KEYS))
    await _automation(hass, ha_url="http://not-https.example")
    await _command(hass, "Zelda", "Echoes", "Switch", "2")
    [game] = _games(setup_entry)
    assert game["title"] == "Zelda Echoes"
    assert game["needs_details"] is True
    assert _copies(setup_entry)[0]["platform"] == "switch2"
    [reply] = telegram["send_message"]
    assert reply["message"] == (
        "Added: Zelda Echoes (Switch 2)\n"
        "IGDB has no game with this title. Find it with Edit."
    )
    # An Edit button needs an https URL.
    assert reply["inline_keyboard"] == [f"Undo:/hkg_g {game['id']}"]


async def test_with_no_igdb_keys_the_title_is_added_with_the_default_platform(
    hass, setup_entry, telegram
) -> None:
    await _automation(
        hass, default_platform="switch", copy_format="digital", shelf_id="nope"
    )
    await _command(hass, "Celeste")
    [game] = _games(setup_entry)
    assert (game["title"], game["needs_details"]) == ("Celeste", True)
    [copy] = _copies(setup_entry)
    assert (copy["platform"], copy["format"], copy["shelf_id"]) == (
        "switch",
        "digital",
        None,
    )
    assert telegram["send_message"][0]["message"] == (
        "Added: Celeste (Switch)\nIGDB is not available. Find the game in IGDB later."
    )


async def test_a_game_in_the_library_gets_a_copy_and_undo_removes_only_it(
    hass, setup_entry, telegram, igdb
) -> None:
    hass.config_entries.async_update_entry(setup_entry, data=dict(KEYS))
    await _automation(hass)
    await _command(hass, "Hades", "pc")
    await _command(hass, "Hades", "switch")
    [game] = _games(setup_entry)
    first, second = _copies(setup_entry)
    reply = telegram["send_message"][1]
    assert reply["message"] == (
        "Copy added: Hades (Switch)\nThe game was already in the library."
    )
    assert reply["inline_keyboard"] == [f"Undo:/hkg_c {second['id']}"]
    await _button(hass, f"/hkg_c {second['id']}", text=reply["message"])
    assert [c["id"] for c in _copies(setup_entry)] == [first["id"]]
    assert [g["id"] for g in _games(setup_entry)] == [game["id"]]
    assert telegram["answer_callback_query"] == [
        {"callback_query_id": "cb1", "message": "Undone."}
    ]
    [edit] = telegram["edit_message"]
    assert (edit["chat_id"], edit["message_id"]) == (CHAT, 7)
    assert edit["message"] == reply["message"] + "\nUndone."


async def test_undo_of_a_new_game_deletes_it_and_a_second_undo_is_no_error(
    hass, setup_entry, telegram
) -> None:
    await _automation(hass)
    await _command(hass, "Celeste", "pc")
    [game] = _games(setup_entry)
    await _button(hass, f"/hkg_g {game['id']}")
    assert _games(setup_entry) == [] and _copies(setup_entry) == []
    await _button(hass, f"/hkg_g {game['id']}")
    assert len(telegram["answer_callback_query"]) == 2


async def test_other_chats_commands_and_buttons_do_nothing(
    hass, setup_entry, telegram
) -> None:
    await _automation(hass)
    await _command(hass, "Celeste", chat=99)
    await _command(hass, "Celeste", command="/start")
    hass.bus.async_fire(
        "telegram_callback",
        {"id": "x", "data": "/other 1", "chat_id": CHAT, "message": {}},
    )
    await hass.async_block_till_done()
    assert _games(setup_entry) == []
    assert all(not kept for kept in telegram.values())


async def test_a_command_in_a_group_and_a_message_with_no_title(
    hass, setup_entry, telegram
) -> None:
    await _automation(hass)
    await _command(hass, command="/juego@HomeBot")
    assert _games(setup_entry) == []
    assert telegram["send_message"][0]["message"] == (
        "Write the title after the command: /juego Hades switch"
    )
    await _command(hass, "Astro", "Bot", "ps5", command="/juego@HomeBot")
    assert [g["title"] for g in _games(setup_entry)] == ["Astro Bot"]
