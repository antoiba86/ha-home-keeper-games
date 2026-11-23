"""Component tests: the barcode scan flow and the covers."""

from __future__ import annotations

import io
from http import HTTPStatus
from pathlib import Path

import aiohttp
import pytest
from homeassistant.exceptions import ServiceValidationError
from PIL import Image

EAN = "0711719505012"


def _jpeg(size=(1600, 2400), color="red", fmt="JPEG") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, fmt)
    return out.getvalue()


async def test_scan_of_a_new_barcode_adds_a_game_that_needs_details(
    hass, setup_entry, call
) -> None:
    reply = await call(
        "scan_barcode",
        {"barcode": " 0711-7195 05012 ", "platform": "switch", "format": "physical"},
    )
    assert reply["result"] == "not_found"
    game = reply["game"]
    assert "barcode" not in game and game["title"] == EAN
    assert game["needs_details"] is True and game["owned"] is True
    assert reply["copy"]["game_id"] == game["id"]
    assert reply["copy"]["barcode"] == EAN and reply["copy"]["platform"] == "switch"
    assert reply["existing_copies"] == [] and reply["from_wishlist"] is False


async def test_scan_of_a_known_barcode_follows_on_duplicate(
    hass, setup_entry, call
) -> None:
    first = await call("scan_barcode", {"barcode": EAN})
    game_id = first["game"]["id"]
    duplicate = await call("scan_barcode", {"barcode": EAN})
    assert duplicate["result"] == "duplicate" and duplicate["copy"] is None
    assert duplicate["game"]["id"] == game_id
    assert len(duplicate["existing_copies"]) == 1
    skipped = await call("scan_barcode", {"barcode": EAN, "on_duplicate": "skip"})
    assert skipped["result"] == "skipped" and skipped["copy"] is None
    second = await call("scan_barcode", {"barcode": EAN, "on_duplicate": "add_copy"})
    assert second["result"] == "added" and len(second["existing_copies"]) == 2
    room = (await call("add_room", {"name": "Den"}))["room"]
    case = (await call("add_unit", {"room_id": room["id"], "name": "L"}))["unit"]
    shelf = (await call("add_shelf", {"unit_id": case["id"], "name": "T"}))["shelf"]
    moved = await call(
        "scan_barcode",
        {"barcode": EAN, "on_duplicate": "move", "shelf_id": shelf["id"]},
    )
    assert moved["result"] == "moved" and moved["copy"]["shelf_id"] == shelf["id"]
    locations = [row["location"] for row in moved["existing_copies"]]
    assert ["Den", "L", "T"] in locations
    games = setup_entry.runtime_data.store.state["games"]
    assert list(games) == [game_id], "a scan of a known barcode adds no game"


async def test_scan_moves_only_a_physical_copy(hass, setup_entry, call) -> None:
    first = await call("scan_barcode", {"barcode": EAN, "format": "digital"})
    assert first["copy"]["shelf_id"] is None
    room = (await call("add_room", {"name": "Den"}))["room"]
    unit = (await call("add_unit", {"room_id": room["id"], "name": "U"}))["unit"]
    shelf = (await call("add_shelf", {"unit_id": unit["id"], "name": "S"}))["shelf"]
    with pytest.raises(ServiceValidationError) as info:
        await call(
            "scan_barcode",
            {"barcode": EAN, "on_duplicate": "move", "shelf_id": shelf["id"]},
        )
    assert info.value.translation_key == "digital_copy_no_shelf"
    await call(
        "scan_barcode",
        {"barcode": EAN, "on_duplicate": "add_copy", "format": "physical"},
    )
    moved = await call(
        "scan_barcode",
        {"barcode": EAN, "on_duplicate": "move", "shelf_id": shelf["id"]},
    )
    assert moved["result"] == "moved" and moved["copy"]["format"] == "physical"
    assert moved["copy"]["shelf_id"] == shelf["id"]


async def test_scan_refuses_a_bad_barcode(hass, setup_entry, call) -> None:
    with pytest.raises(ServiceValidationError) as info:
        await call("scan_barcode", {"barcode": "12#45"})
    assert info.value.translation_key == "invalid_barcode"
    assert info.value.translation_placeholders == {"barcode": "12#45"}
    with pytest.raises(ServiceValidationError) as info:
        await call("scan_barcode", {"barcode": " - "})
    assert info.value.translation_key == "invalid_barcode"
    assert info.value.translation_placeholders == {"barcode": ""}
    with pytest.raises(ServiceValidationError) as info:
        await call("scan_barcode", {"barcode": ""})
    assert info.value.translation_key == "field_required"
    assert info.value.translation_placeholders == {"field": "barcode"}
    assert setup_entry.runtime_data.store.state["games"] == {}


async def test_add_game_by_barcode_looks_up_a_copy(hass, setup_entry, call) -> None:
    added = await call("add_game", {"barcode": EAN, "title": "Dune"})
    assert added["existing"] is False and "barcode" not in added["game"]
    # The barcode is on no copy yet, so a second call adds a second game.
    again = await call("add_game", {"barcode": EAN, "title": "Dune 2"})
    assert again["existing"] is False
    await call("add_copy", {"game_id": added["game"]["id"], "barcode": EAN})
    found = await call("add_game", {"barcode": EAN})
    assert found["existing"] is True and found["game"]["id"] == added["game"]["id"]
    bare = (await call("add_game", {"barcode": "4006381333931"}))["game"]
    assert bare["title"] == "4006381333931" and bare["needs_details"] is True
    with pytest.raises(ServiceValidationError) as info:
        await call("add_game", {"genres": ["Puzzle"]})
    assert info.value.translation_key == "barcode_or_title_required"
    with pytest.raises(ServiceValidationError) as info:
        await call("add_copy", {"game_id": bare["id"], "barcode": EAN})
    assert info.value.translation_key == "duplicate_barcode"
    assert info.value.translation_placeholders == {"barcode": EAN}
    copy = (await call("add_copy", {"game_id": bare["id"]}))["copy"]
    with pytest.raises(ServiceValidationError) as info:
        await call("update_copy", {"copy_id": copy["id"], "barcode": EAN})
    assert info.value.translation_key == "duplicate_barcode"


async def _upload(hass_client, data: bytes, name: str = "c.png"):
    client = await hass_client()
    form = aiohttp.FormData()
    form.add_field("file", data, filename=name, content_type="image/png")
    return await client.post("/api/home_keeper_games/upload", data=form)


async def test_cover_upload_and_custom_cover(
    hass, setup_entry, call, hass_client
) -> None:
    game = (await call("add_game", {"title": "Dune"}))["game"]
    png = io.BytesIO()
    Image.new("RGBA", (100, 150), (0, 0, 255, 128)).save(png, "PNG")
    response = await _upload(hass_client, png.getvalue())
    assert response.status == HTTPStatus.OK
    file_id = (await response.json())["file_id"]
    reply = await call(
        "set_cover", {"game_id": game["id"], "kind": "custom", "file_id": file_id}
    )
    assert reply["game"]["cover"]["kind"] == "custom"
    url = reply["game"]["cover_url"]
    client = await hass_client()
    assert (await client.get(url)).status == HTTPStatus.OK
    with pytest.raises(ServiceValidationError) as info:
        await call(
            "set_cover", {"game_id": game["id"], "kind": "custom", "file_id": file_id}
        )
    assert info.value.translation_key == "upload_not_found"
    with pytest.raises(ServiceValidationError) as info:
        await call("set_cover", {"game_id": game["id"], "kind": "custom"})
    assert info.value.translation_key == "field_required"
    reply = await call("get_game", {"game_id": game["id"]})
    assert reply["game"]["cover"]["kind"] == "custom", "a failed call keeps the cover"
    assert (await client.get(url)).status == HTTPStatus.OK
    reply = await call("set_cover", {"game_id": game["id"], "kind": "none"})
    assert reply["game"]["cover_url"] is None
    assert (await client.get(url)).status == HTTPStatus.NOT_FOUND
    assert (await client.get("/api/home_keeper_games/cover/nope")).status == 404


def test_reencode_leaves_no_temp_file(tmp_path, monkeypatch) -> None:
    from custom_components.home_keeper_games import covers

    def _fail(_image, path, *_args, **_kwargs):
        Path(path).write_bytes(b"part")
        raise OSError("disk full")

    data = _jpeg((10, 15))
    monkeypatch.setattr(Image.Image, "save", _fail)
    with pytest.raises(covers.CoverError):
        covers.reencode(data, tmp_path / "x.jpg")
    assert list(tmp_path.iterdir()) == []


async def test_cover_upload_rules(
    hass, setup_entry, hass_client, hass_read_only_access_token, aiohttp_client
) -> None:
    response = await _upload(hass_client, b"GIF89a not an image we take")
    assert response.status == HTTPStatus.BAD_REQUEST
    assert "JPEG, PNG or WebP" in (await response.json())["message"]
    response = await _upload(hass_client, b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    assert response.status == HTTPStatus.BAD_REQUEST
    assert (await response.json())["message"] == "The image cannot be read."
    big = b"\xff\xd8\xff" + b"0" * (10 * 1024 * 1024)
    response = await _upload(hass_client, big)
    assert response.status == HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    client = await hass_client()
    response = await client.post(
        "/api/home_keeper_games/upload",
        data=b"x",
        headers={"Content-Type": "text/plain"},
    )
    assert response.status == HTTPStatus.BAD_REQUEST
    form = aiohttp.FormData()
    form.add_field("name", "no file", content_type="text/plain")
    response = await client.post("/api/home_keeper_games/upload", data=form)
    assert (await response.json())["message"] == "The upload has no file."
    user = await hass_client(hass_read_only_access_token)
    form = aiohttp.FormData()
    form.add_field("file", _jpeg((10, 10)), filename="c.jpg")
    response = await user.post("/api/home_keeper_games/upload", data=form)
    assert response.status == HTTPStatus.UNAUTHORIZED
    webp = _jpeg((20, 20), fmt="WEBP")
    response = await _upload(hass_client, webp, "c.webp")
    assert response.status == HTTPStatus.OK


async def test_covers_dir_is_not_the_store_file(hass, setup_entry) -> None:
    from custom_components.home_keeper_games import covers

    store_file = Path(hass.config.path(".storage", "home_keeper_games"))
    directory = covers.covers_dir(hass)
    assert directory.parent == store_file.parent
    assert directory != store_file and store_file not in directory.parents


async def test_signed_cover_url_needs_no_token(
    hass, setup_entry, call, hass_client, hass_client_no_auth, hass_ws_client
) -> None:
    """The tab and the card sign a cover path, because an <img> sends no token."""
    game = (await call("add_game", {"title": "Dune"}))["game"]
    response = await _upload(hass_client, _jpeg((60, 90)))
    file_id = (await response.json())["file_id"]
    url = (
        await call(
            "set_cover", {"game_id": game["id"], "kind": "custom", "file_id": file_id}
        )
    )["game"]["cover_url"]
    anon = await hass_client_no_auth()
    assert (await anon.get(url)).status == HTTPStatus.UNAUTHORIZED
    ws = await hass_ws_client(hass)
    await ws.send_json(
        {"id": 1, "type": "auth/sign_path", "path": url, "expires": 3600}
    )
    signed = (await ws.receive_json())["result"]["path"]
    assert signed.startswith(url) and "authSig=" in signed
    assert (await anon.get(signed)).status == HTTPStatus.OK
