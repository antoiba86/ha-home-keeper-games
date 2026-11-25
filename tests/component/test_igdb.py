"""Component tests: the IGDB keys, ``search_catalog`` and ``add_game`` from IGDB.

``aioclient_mock`` replaces the shared aiohttp session, so the real client code
sends each request to a fake Twitch and a fake IGDB.
"""

from __future__ import annotations

import io
import json

import pytest
from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from PIL import Image
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMockResponse,
)

from custom_components.home_keeper_games import covers
from custom_components.home_keeper_games.const import (
    DOMAIN,
    IGDB_API_URL,
    IGDB_IMAGES_URL,
    IGDB_TOKEN_URL,
)
from custom_components.home_keeper_games.diagnostics import (
    async_get_config_entry_diagnostics,
)

GAMES = f"{IGDB_API_URL}/games"
COVER = f"{IGDB_IMAGES_URL}/t_cover_big/co3p2d.jpg"
KEYS = {"igdb_client_id": "cid", "igdb_client_secret": "s3cret-value"}
ZELDA = {
    "id": 7346,
    "name": "The Legend of Zelda: Breath of the Wild",
    "summary": "Step into a world of discovery.",
    "first_release_date": 1488499200,
    "genres": [{"name": "Adventure"}],
    "franchises": [{"name": "The Legend of Zelda"}],
    "cover": {"image_id": "co3p2d"},
    "platforms": [130, 41],
}
HADES = {"id": 113112, "name": "Hades", "platforms": [6]}


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (264, 374), "green").save(out, "JPEG")
    return out.getvalue()


def _token(aioclient_mock, status: int = 200, **kwargs) -> None:
    body = {"access_token": "tok", "expires_in": 5000000, "token_type": "bearer"}
    aioclient_mock.post(IGDB_TOKEN_URL, status=status, json=body, **kwargs)


def _igdb(aioclient_mock) -> None:
    """A fake IGDB: a search finds Zelda and Hades; an id read finds Zelda only."""

    async def games(method, url, data):
        body = data.decode()
        if body.startswith("search"):
            found = [ZELDA, HADES]
        elif "where id = 7346;" in body:
            found = [ZELDA]
        elif "where id = 113112;" in body:
            found = [HADES]
        else:
            found = []
        return AiohttpClientMockResponse(method, url, json=found)

    _token(aioclient_mock)
    aioclient_mock.post(GAMES, side_effect=games)
    aioclient_mock.get(COVER, content=_jpeg())


@pytest.fixture
async def igdb_entry(hass, setup_entry):
    """The set-up library with the IGDB keys in the entry data."""
    hass.config_entries.async_update_entry(setup_entry, data=dict(KEYS))
    await hass.async_block_till_done()
    return setup_entry


def _calls(aioclient_mock, url: str) -> list:
    return [c for c in aioclient_mock.mock_calls if str(c[1]) == url]


async def _key(call, service: str, data: dict, as_: str = "admin") -> str:
    with pytest.raises(ServiceValidationError) as info:
        await call(service, data, as_=as_)
    return info.value.translation_key


# ── search_catalog ───────────────────────────────────────────────────────────


async def test_search_needs_the_keys(hass, setup_entry, call, aioclient_mock) -> None:
    assert (
        await _key(call, "search_catalog", {"query": "zelda"}) == "igdb_not_configured"
    )
    assert aioclient_mock.call_count == 0


async def test_a_non_admin_user_can_search(
    hass, igdb_entry, call, aioclient_mock
) -> None:
    _igdb(aioclient_mock)
    reply = await call(
        "search_catalog", {"query": "zelda", "platform": "switch"}, as_="user"
    )
    assert reply["candidates"] == [
        {
            "igdb_id": 7346,
            "title": "The Legend of Zelda: Breath of the Wild",
            "release_year": 2017,
            "platforms": ["switch"],
            "cover_url": COVER,
            "in_library": None,
        },
        {
            "igdb_id": 113112,
            "title": "Hades",
            "release_year": None,
            "platforms": ["pc"],
            "cover_url": None,
            "in_library": None,
        },
    ]
    _method, _url, data, headers = _calls(aioclient_mock, GAMES)[0]
    assert data.decode().startswith('search "zelda";')
    assert "platforms = (130)" in data.decode()
    assert headers["Client-ID"] == "cid"
    assert headers["Authorization"] == "Bearer tok"
    # The secret goes only in the body of the token request.
    token_call = _calls(aioclient_mock, IGDB_TOKEN_URL)[0]
    assert "s3cret-value" not in str(token_call[1])
    assert token_call[2]["client_secret"] == "s3cret-value"


async def test_the_token_is_kept_between_calls(
    hass, igdb_entry, call, aioclient_mock
) -> None:
    _igdb(aioclient_mock)
    await call("search_catalog", {"query": "zelda"})
    await call("search_catalog", {"query": "hades", "limit": 2})
    assert len(_calls(aioclient_mock, IGDB_TOKEN_URL)) == 1
    assert "limit 2;" in _calls(aioclient_mock, GAMES)[1][2].decode()


async def test_new_keys_get_a_new_token(hass, igdb_entry, call, aioclient_mock) -> None:
    _igdb(aioclient_mock)
    await call("search_catalog", {"query": "zelda"})
    hass.config_entries.async_update_entry(
        igdb_entry, data={**KEYS, "igdb_client_secret": "other"}
    )
    await call("search_catalog", {"query": "zelda"})
    assert len(_calls(aioclient_mock, IGDB_TOKEN_URL)) == 2


async def test_search_marks_a_game_in_the_library(
    hass, igdb_entry, call, aioclient_mock
) -> None:
    _igdb(aioclient_mock)
    game = (await call("add_game", {"title": "Mine", "igdb_id": 113112}))["game"]
    reply = await call("search_catalog", {"query": "hades"})
    assert [c["in_library"] for c in reply["candidates"]] == [None, game["id"]]


async def test_an_empty_search_sends_nothing(
    hass, igdb_entry, call, aioclient_mock
) -> None:
    _igdb(aioclient_mock)
    assert await call("search_catalog", {"query": ' " '}) == {"candidates": []}
    assert aioclient_mock.call_count == 0


@pytest.mark.parametrize("limit", [0, 21])
async def test_search_limit_range(hass, igdb_entry, call, limit) -> None:
    import voluptuous as vol

    with pytest.raises(vol.Invalid):
        await call("search_catalog", {"query": "x", "limit": limit})


# ── add_game ─────────────────────────────────────────────────────────────────


async def test_add_by_igdb_id_fills_the_game_and_the_cover(
    hass, igdb_entry, call, aioclient_mock
) -> None:
    _igdb(aioclient_mock)
    reply = await call("add_game", {"igdb_id": 7346, "tags": ["owned"]})
    game = reply["game"]
    assert reply["existing"] is False
    assert game["title"] == "The Legend of Zelda: Breath of the Wild"
    assert game["summary"] == "Step into a world of discovery."
    assert game["genres"] == ["Adventure"]
    assert game["release_date"] == "2017-03-03"
    assert game["franchise"] == "The Legend of Zelda"
    assert game["igdb_id"] == 7346
    assert game["tags"] == ["owned"]
    assert game["needs_details"] is False
    stored = igdb_entry.runtime_data.store.game(game["id"])
    assert stored["cover"]["kind"] == "igdb"
    path = covers.covers_dir(hass) / stored["cover"]["file"]
    assert await hass.async_add_executor_job(path.is_file)
    assert game["cover_url"].startswith("/api/home_keeper_games/cover/")


async def test_the_fields_of_the_caller_win(
    hass, igdb_entry, call, aioclient_mock
) -> None:
    _igdb(aioclient_mock)
    game = (
        await call("add_game", {"igdb_id": 7346, "title": "BotW", "franchise": "Zelda"})
    )["game"]
    assert (game["title"], game["franchise"]) == ("BotW", "Zelda")
    assert game["summary"] == "Step into a world of discovery."


async def test_add_by_igdb_id_twice_returns_the_game(
    hass, igdb_entry, call, aioclient_mock
) -> None:
    _igdb(aioclient_mock)
    first = (await call("add_game", {"igdb_id": 7346}))["game"]
    reply = await call("add_game", {"igdb_id": 7346})
    assert reply == {"game": reply["game"], "existing": True}
    assert reply["game"]["id"] == first["id"]
    assert len(_calls(aioclient_mock, GAMES)) == 1


async def test_add_by_an_unknown_igdb_id(
    hass, igdb_entry, call, aioclient_mock
) -> None:
    _igdb(aioclient_mock)
    assert await _key(call, "add_game", {"igdb_id": 999}) == "igdb_not_found"
    assert igdb_entry.runtime_data.store.state["games"] == {}


async def test_add_by_igdb_id_needs_the_keys(hass, setup_entry, call) -> None:
    assert await _key(call, "add_game", {"igdb_id": 7346}) == "igdb_not_configured"


async def test_a_barcode_of_a_copy_wins_over_the_igdb_id(
    hass, igdb_entry, call, aioclient_mock
) -> None:
    _igdb(aioclient_mock)
    game = (await call("add_game", {"title": "Boxed"}))["game"]
    await call("add_copy", {"game_id": game["id"], "barcode": "0711719505012"})
    reply = await call("add_game", {"igdb_id": 7346, "barcode": "0711719505012"})
    assert (reply["game"]["id"], reply["existing"]) == (game["id"], True)
    assert aioclient_mock.call_count == 0


async def test_lookup_uses_an_exact_match(
    hass, igdb_entry, call, aioclient_mock
) -> None:
    _igdb(aioclient_mock)
    reply = await call("add_game", {"title": "hades", "lookup": True, "platform": "pc"})
    game = reply["game"]
    assert (game["title"], game["igdb_id"], game["needs_details"]) == (
        "Hades",
        113112,
        False,
    )
    # Hades has no cover in the fake.
    assert game["cover_url"] is None
    again = await call("add_game", {"title": "Hades", "lookup": True})
    assert (again["game"]["id"], again["existing"]) == (game["id"], True)


@pytest.mark.parametrize(
    "data",
    [
        {"title": "Zelda", "lookup": True},
        {"title": "Hades", "lookup": True, "platform": "switch"},
    ],
)
async def test_lookup_with_no_match_adds_the_title_only(
    hass, igdb_entry, call, aioclient_mock, data
) -> None:
    _igdb(aioclient_mock)
    game = (await call("add_game", data))["game"]
    assert game["title"] == data["title"]
    assert game["igdb_id"] is None
    assert game["needs_details"] is True


async def test_with_no_lookup_the_title_is_not_searched(
    hass, igdb_entry, call, aioclient_mock
) -> None:
    _igdb(aioclient_mock)
    game = (await call("add_game", {"title": "Hades"}))["game"]
    assert (game["igdb_id"], game["needs_details"]) == (None, False)
    assert aioclient_mock.call_count == 0


@pytest.mark.parametrize(
    "cover",
    [{"status": 404}, {"content": b"not an image"}, {"exc": ClientError()}],
)
async def test_a_failed_cover_download_keeps_the_game(
    hass, igdb_entry, call, aioclient_mock, cover
) -> None:
    _token(aioclient_mock)
    aioclient_mock.post(GAMES, json=[ZELDA])
    aioclient_mock.get(COVER, **cover)
    reply = await call("add_game", {"igdb_id": 7346})
    assert reply["game"]["igdb_id"] == 7346
    assert reply["game"]["cover_url"] is None


async def test_an_igdb_cover_never_replaces_an_upload(
    hass, igdb_entry, call, aioclient_mock
) -> None:
    _igdb(aioclient_mock)
    coordinator = igdb_entry.runtime_data
    game = (await call("add_game", {"title": "Mine"}))["game"]
    await coordinator.store.set_cover(game["id"], "custom", "f.jpg")
    stored = await covers.async_store_igdb_cover(
        hass, coordinator, game["id"], "co3p2d"
    )
    assert stored is False
    assert coordinator.store.game(game["id"])["cover"] == {
        "kind": "custom",
        "file": "f.jpg",
    }
    assert (
        await covers.async_store_igdb_cover(hass, coordinator, "nope", "co3p2d")
        is False
    )
    assert aioclient_mock.call_count == 0


async def test_set_cover_does_not_take_the_igdb_kind(hass, setup_entry, call) -> None:
    import voluptuous as vol

    game = (await call("add_game", {"title": "Mine"}))["game"]
    with pytest.raises(vol.Invalid):
        await call("set_cover", {"game_id": game["id"], "kind": "igdb"})


# ── Errors of the client ─────────────────────────────────────────────────────


async def test_a_401_gets_a_new_token_once(
    hass, igdb_entry, call, aioclient_mock
) -> None:
    replies = iter([401, 200])

    async def games(method, url, data):
        status = next(replies, 401)
        return AiohttpClientMockResponse(method, url, status=status, json=[HADES])

    _token(aioclient_mock)
    aioclient_mock.post(GAMES, side_effect=games)
    reply = await call("search_catalog", {"query": "hades"})
    assert [c["igdb_id"] for c in reply["candidates"]] == [113112]
    assert len(_calls(aioclient_mock, IGDB_TOKEN_URL)) == 2
    # 2 refusals in a row: the keys are wrong.
    replies = iter([401, 401])
    assert await _key(call, "search_catalog", {"query": "x"}) == "invalid_igdb_auth"


@pytest.mark.parametrize(
    ("token", "games", "key"),
    [
        ({"status": 400}, {"json": []}, "invalid_igdb_auth"),
        ({"status": 403}, {"json": []}, "invalid_igdb_auth"),
        ({"status": 500}, {"json": []}, "igdb_unavailable"),
        ({"exc": ClientError()}, {"json": []}, "igdb_unavailable"),
        ({"exc": TimeoutError()}, {"json": []}, "igdb_unavailable"),
        ({"text": "not json"}, {"json": []}, "igdb_unavailable"),
        ({"json": {"expires_in": 60}}, {"json": []}, "igdb_unavailable"),
        ({}, {"status": 403, "json": []}, "invalid_igdb_auth"),
        ({}, {"status": 429, "json": []}, "igdb_unavailable"),
        ({}, {"status": 500, "json": []}, "igdb_unavailable"),
        ({}, {"exc": ClientError()}, "igdb_unavailable"),
        ({}, {"text": "<html>"}, "igdb_unavailable"),
    ],
)
async def test_client_errors(
    hass, igdb_entry, call, aioclient_mock, token, games, key
) -> None:
    if not token:
        _token(aioclient_mock)
    else:
        aioclient_mock.post(IGDB_TOKEN_URL, **token)
    aioclient_mock.post(GAMES, **games)
    assert await _key(call, "search_catalog", {"query": "x"}) == key


async def test_a_bad_reply_shape_finds_nothing(
    hass, igdb_entry, call, aioclient_mock
) -> None:
    _token(aioclient_mock)
    aioclient_mock.post(GAMES, json={"message": "odd"})
    assert await call("search_catalog", {"query": "x"}) == {"candidates": []}


# ── Keys in the flows ────────────────────────────────────────────────────────


async def _user_flow(hass, data: dict) -> dict:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"currency": "EUR", **data}
    )


async def test_user_flow_stores_checked_keys(
    hass, persons, hk_entry, aioclient_mock
) -> None:
    _token(aioclient_mock)
    result = await _user_flow(
        hass, {"igdb_client_id": " cid ", "igdb_client_secret": "s"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"igdb_client_id": "cid", "igdb_client_secret": "s"}
    assert result["options"] == {"currency": "EUR"}


async def test_user_flow_with_no_keys(hass, persons, hk_entry, aioclient_mock) -> None:
    result = await _user_flow(hass, {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {}
    assert aioclient_mock.call_count == 0


@pytest.mark.parametrize(
    ("data", "token", "error"),
    [
        ({"igdb_client_id": "cid"}, None, "igdb_keys_incomplete"),
        ({"igdb_client_secret": "s"}, None, "igdb_keys_incomplete"),
        (
            {"igdb_client_id": "cid", "igdb_client_secret": "s"},
            {"status": 400},
            "invalid_igdb_auth",
        ),
        (
            {"igdb_client_id": "cid", "igdb_client_secret": "s"},
            {"exc": ClientError()},
            "cannot_connect",
        ),
    ],
)
async def test_user_flow_key_errors(
    hass, persons, hk_entry, aioclient_mock, data, token, error
) -> None:
    if token is not None:
        aioclient_mock.post(IGDB_TOKEN_URL, **token)
    result = await _user_flow(hass, data)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}
    # The form keeps the client ID, never the secret.
    schema = result["data_schema"].schema
    key = next(k for k in schema if str(k) == "igdb_client_id")
    assert key.description == {"suggested_value": data.get("igdb_client_id", "")}


async def _options(hass, entry, data: dict) -> dict:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"currency": "EUR", **data}
    )


async def test_options_flow_adds_changes_and_removes_the_keys(
    hass, setup_entry, aioclient_mock
) -> None:
    _token(aioclient_mock)
    result = await _options(
        hass, setup_entry, {"igdb_client_id": "cid", "igdb_client_secret": "s"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert dict(setup_entry.data) == {
        "igdb_client_id": "cid",
        "igdb_client_secret": "s",
    }
    assert setup_entry.runtime_data.igdb_keys == ("cid", "s")
    # The form shows the client ID, and an empty secret keeps the stored one.
    form = await hass.config_entries.options.async_init(setup_entry.entry_id)
    key = next(k for k in form["data_schema"].schema if str(k) == "igdb_client_id")
    assert key.description == {"suggested_value": "cid"}
    hass.config_entries.options.async_abort(form["flow_id"])
    result = await _options(hass, setup_entry, {"igdb_client_id": "cid"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert dict(setup_entry.data) == {
        "igdb_client_id": "cid",
        "igdb_client_secret": "s",
    }
    assert len(_calls(aioclient_mock, IGDB_TOKEN_URL)) == 1
    # A new client ID needs its secret.
    result = await _options(hass, setup_entry, {"igdb_client_id": "new"})
    assert result["errors"] == {"base": "igdb_keys_incomplete"}
    # An empty client ID removes both keys.
    result = await _options(hass, setup_entry, {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert dict(setup_entry.data) == {}
    assert setup_entry.runtime_data.igdb_keys is None


async def test_options_flow_refuses_bad_keys(hass, setup_entry, aioclient_mock) -> None:
    aioclient_mock.post(IGDB_TOKEN_URL, status=403)
    result = await _options(
        hass, setup_entry, {"igdb_client_id": "c", "igdb_client_secret": "s"}
    )
    assert result["errors"] == {"base": "invalid_igdb_auth"}
    assert dict(setup_entry.data) == {}


async def test_the_secret_is_not_in_the_diagnostics(hass, igdb_entry) -> None:
    found = await async_get_config_entry_diagnostics(hass, igdb_entry)
    assert "s3cret-value" not in json.dumps(found, default=str)
