"""Component tests: the export_data and import_data services."""

from __future__ import annotations

import io
import shutil
from pathlib import Path

import pytest
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from homeassistant.helpers import area_registry as ar
from PIL import Image
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.home_keeper_games import models
from custom_components.home_keeper_games.const import PANEL_VERSION

ALICE = "p_alice"
BOB = "p_bob"
BUNDLES = (".storage", "home_keeper_import_export")


@pytest.fixture(autouse=True)
def _clean_bundles(hass):
    """The config directory of the harness is shared, so remove the bundles."""
    root = Path(hass.config.path(*BUNDLES))
    shutil.rmtree(root, ignore_errors=True)
    yield
    shutil.rmtree(root, ignore_errors=True)


def coordinator(entry):
    """The coordinator of the entry."""
    return entry.runtime_data


def _fake(hass) -> dict:
    return hass.data["home_keeper_fake"]


def _jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (20, 30), (200, 10, 10)).save(out, "JPEG")
    return out.getvalue()


async def _todo_items(hass, entity: str) -> list[dict]:
    items = await hass.services.async_call(
        "todo",
        "get_items",
        {"entity_id": entity},
        blocking=True,
        return_response=True,
    )
    return items[entity]["items"]


async def _library(hass, call, todo_list) -> dict:
    """A library with a room in an area, a shelf, 2 games, a copy, loans and reading."""
    area = ar.async_get(hass).async_create("Living room")
    room = (await call("add_room", {"name": "Study", "area_id": area.id}))["room"]
    case = (await call("add_unit", {"room_id": room["id"], "name": "Oak"}))["unit"]
    shelf = (await call("add_shelf", {"unit_id": case["id"], "name": "Top"}))["shelf"]
    dune = (
        await call(
            "add_game",
            {"title": "Dune", "authors": ["Frank Herbert"]},
        )
    )["game"]
    copy = (await call("add_copy", {"game_id": dune["id"], "shelf_id": shelf["id"]}))[
        "copy"
    ]
    loan = (
        await call(
            "lend_game", {"copy_id": copy["id"], "party": "Sam", "due": "2026-12-01"}
        )
    )["loan"]
    await call(
        "set_reading", {"game_id": dune["id"], "person_id": ALICE, "status": "read"}
    )
    await call("set_person_settings", {"person_id": BOB, "wishlist_todo": todo_list})
    emma = (
        await call(
            "add_game",
            {"title": "Emma", "authors": ["Jane Austen"]},
        )
    )["game"]
    await call(
        "add_to_wishlist", {"game_id": emma["id"], "person_id": BOB, "buy": True}
    )
    await hass.async_block_till_done(wait_background_tasks=True)
    return {
        "area": area.id,
        "room": room["id"],
        "dune": dune["id"],
        "emma": emma["id"],
        "copy": copy["id"],
        "loan": loan["id"],
    }


async def _forget_install(hass, entry, todo_list) -> None:
    """Make the library look like a new install: no records, tasks or to-do items."""
    store = coordinator(entry).store
    store.state = models.empty_state()
    await store._commit([])
    _fake(hass)["tasks"].clear()
    items = await _todo_items(hass, todo_list)
    if items:
        await hass.services.async_call(
            "todo",
            "remove_item",
            {"entity_id": todo_list, "item": [i["uid"] for i in items]},
            blocking=True,
        )
    await hass.async_block_till_done()


async def test_export_data_reply(hass, setup_entry, call, todo_list) -> None:
    ids = await _library(hass, call, todo_list)
    reply = await call("export_data")
    assert reply["format"] == 1
    assert reply["version"] == PANEL_VERSION
    assert reply["skipped"] == {"covers": 0}
    data = reply["data"]
    assert data["rooms"][0]["area_id"] == ids["area"]
    assert data["rooms"][0]["area_name"] == "Living room"
    assert data["reading"][0]["person_name"] == "Alice"
    people = {p["person_id"]: p for p in data["people"]}
    assert people[BOB]["wishlist_todo"] == todo_list
    assert people[BOB]["wishlist_todo_name"] == "Books"
    loan = data["loans"][0]
    assert loan["id"] == ids["loan"]
    assert "hk_task_id" not in loan
    emma = next(b for b in data["games"] if b["id"] == ids["emma"])
    assert emma["wishlist"]["person_name"] == "Bob"
    assert "todo_uid" not in emma["wishlist"]
    # The store keeps the values of this install.
    stored = coordinator(setup_entry).store.state
    assert stored["loans"][ids["loan"]]["hk_task_id"]
    assert stored["games"][ids["emma"]]["wishlist"]["todo_uid"]


async def test_import_data_into_a_new_install(
    hass, setup_entry, call, todo_list
) -> None:
    ids = await _library(hass, call, todo_list)
    exported = (await call("export_data"))["data"]
    await _forget_install(hass, setup_entry, todo_list)

    preview = await call("import_data", {"document": exported, "dry_run": True})
    assert preview["ok"] is True and preview["dry_run"] is True
    assert preview["problems"] == []
    assert preview["counts"]["games"] == {"created": 2, "updated": 0, "skipped": 0}
    assert preview["counts"]["covers"] == {"imported": 0, "skipped": 0}
    assert coordinator(setup_entry).store.state["games"] == {}

    imported = async_capture_events(hass, "home_keeper_games_data_imported")
    added = async_capture_events(hass, "home_keeper_games_game_added")
    reply = await call("import_data", {"document": exported})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert reply["ok"] is True and reply["dry_run"] is False
    assert reply["counts"]["loans"]["created"] == 1
    assert {r["section"] for r in reply["records"]} >= {"rooms", "games", "loans"}
    assert len(imported) == 1
    assert imported[0].data["counts"]["games"]["created"] == 2
    assert imported[0].data["origin"] is None
    assert added == [], "an import fires only data_imported"

    state = coordinator(setup_entry).store.state
    assert set(state["games"]) == {ids["dune"], ids["emma"]}
    assert state["rooms"][ids["room"]]["area_id"] == ids["area"]
    assert state["reading"][ALICE][ids["dune"]]["status"] == "read"
    # The loan sync made the Home Keeper task again.
    task_id = state["loans"][ids["loan"]]["hk_task_id"]
    assert task_id in _fake(hass)["tasks"]
    assert _fake(hass)["tasks"][task_id]["source"] == {
        "home_keeper_games": {"loan_id": ids["loan"]}
    }
    # The wishlist sync made the to-do item again.
    items = await _todo_items(hass, todo_list)
    assert [i["summary"] for i in items] == ["Emma by Jane Austen"]
    assert state["games"][ids["emma"]]["wishlist"]["todo_uid"] == items[0]["uid"]
    # The export of the new install is the same document.
    again = (await call("export_data"))["data"]
    assert again == exported


async def test_import_data_reports_problems(hass, setup_entry, call) -> None:
    reply = await call(
        "import_data", {"document": {"format": 2, "games": [{"title": "X"}]}}
    )
    assert reply["ok"] is False
    assert reply["problems"] == [
        {
            "level": "error",
            "path": "format",
            "message": "The document has format 2. This version reads format 1 or "
            "lower.",
        }
    ]
    assert coordinator(setup_entry).store.state["games"] == {}

    reply = await call(
        "import_data",
        {
            "document": {
                "games": [{"title": "A"}, {"title": "B", "pages": 0}],
                "reading": [{"person_id": "gone", "person_name": "Zed", "games": []}],
            }
        },
    )
    assert reply["ok"] is False
    assert reply["problems"] == [
        {
            "level": "error",
            "path": "games[1].pages",
            "message": "pages must be from 1 to 100000.",
        },
        {
            "level": "warning",
            "path": "reading[0].person_id",
            "message": "No person matches Zed.",
        },
    ]
    assert coordinator(setup_entry).store.state["games"] == {}, "an error blocks all"


async def test_services_refuse_a_non_admin_user(hass, setup_entry, call, ws) -> None:
    with pytest.raises(Unauthorized):
        await call("export_data", as_="user")
    with pytest.raises(Unauthorized):
        await call("import_data", {"document": {}}, as_="user")
    client = await ws("user")
    await client.send_json_auto_id({"type": "home_keeper_games/export_data"})
    reply = await client.receive_json()
    assert reply["success"] is False
    assert reply["error"]["code"] == "unauthorized"
    await client.send_json_auto_id(
        {"type": "home_keeper_games/import_data", "document": {"games": []}}
    )
    reply = await client.receive_json()
    assert reply["error"]["code"] == "unauthorized"


async def test_websocket_twin_for_an_admin(hass, setup_entry, call, ws) -> None:
    await call("add_game", {"title": "Dune"})
    client = await ws("admin")
    await client.send_json_auto_id({"type": "home_keeper_games/export_data"})
    reply = await client.receive_json()
    assert reply["success"] is True
    assert [b["title"] for b in reply["result"]["data"]["games"]] == ["Dune"]
    assert reply["result"]["data"]["copies"] == []


@pytest.mark.parametrize(
    "files_dir",
    [
        "/tmp/elsewhere",
        ".storage/home_keeper_import_export/../home_keeper_games_covers",
        ".storage",
    ],
)
async def test_files_dir_outside_the_bundles_is_refused(
    hass, setup_entry, call, files_dir
) -> None:
    for service, data in (
        ("export_data", {"files_dir": files_dir}),
        ("import_data", {"document": {}, "files_dir": files_dir}),
    ):
        with pytest.raises(ServiceValidationError) as err:
            await call(service, data)
        assert err.value.translation_key == "files_dir_invalid"


async def test_symbolic_link_out_of_the_bundles_is_refused(
    hass, setup_entry, call, tmp_path
) -> None:
    root = Path(hass.config.path(*BUNDLES))
    # Test setup on an empty temporary directory: a short blocking call is fine.
    root.mkdir(parents=True, exist_ok=True)  # noqa: ASYNC240
    link = root / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ServiceValidationError) as err:
        await call("export_data", {"files_dir": str(link)})
    assert err.value.translation_key == "files_dir_invalid"


async def test_covers_travel_in_a_bundle(hass, setup_entry, call, todo_list) -> None:
    from custom_components.home_keeper_games.covers import covers_dir

    game = (await call("add_game", {"title": "Dune"}))["game"]
    plain = (await call("add_game", {"title": "Emma"}))["game"]
    directory = covers_dir(hass)
    directory.mkdir(parents=True, exist_ok=True)
    name = f"{game['id']}-0a1b2c3d.jpg"
    (directory / name).write_bytes(_jpeg())
    await coordinator(setup_entry).store.set_cover(game["id"], "custom", name)

    without = await call("export_data")
    assert without["skipped"] == {"covers": 1}
    dune = next(b for b in without["data"]["games"] if b["id"] == game["id"])
    assert dune["cover"] is None

    bundle = Path(hass.config.path(*BUNDLES, "export-1"))
    reply = await call("export_data", {"files_dir": str(bundle)})
    assert reply["skipped"] == {"covers": 0}
    dune = next(b for b in reply["data"]["games"] if b["id"] == game["id"])
    assert dune["cover"] == {"kind": "custom", "file": f"covers/{game['id']}.jpg"}
    emma = next(b for b in reply["data"]["games"] if b["id"] == plain["id"])
    assert emma["cover"] is None
    copied = bundle / "covers" / f"{game['id']}.jpg"
    assert copied.read_bytes() == (directory / name).read_bytes()

    await _forget_install(hass, setup_entry, todo_list)
    (directory / name).unlink()
    before = set(directory.glob("*.jpg"))
    no_files = await call("import_data", {"document": reply["data"], "dry_run": True})
    assert no_files["counts"]["covers"] == {"imported": 0, "skipped": 1}

    relative = ".storage/home_keeper_import_export/export-1"
    preview = await call(
        "import_data",
        {"document": reply["data"], "dry_run": True, "files_dir": relative},
    )
    assert preview["counts"]["covers"] == {"imported": 1, "skipped": 0}
    assert set(directory.glob("*.jpg")) == before, "a dry run writes no file"

    result = await call(
        "import_data", {"document": reply["data"], "files_dir": str(bundle)}
    )
    assert result["ok"] is True
    assert result["counts"]["covers"] == {"imported": 1, "skipped": 0}
    cover = coordinator(setup_entry).store.state["games"][game["id"]]["cover"]
    assert cover["kind"] == "custom"
    assert cover["file"] != name
    stored = directory / cover["file"]
    with Image.open(stored) as image:
        assert image.format == "JPEG"
        assert image.size == (20, 30)
    stored.unlink()


async def test_bad_cover_file_is_a_warning(hass, setup_entry, call) -> None:
    bundle = Path(hass.config.path(*BUNDLES, "bad"))
    (bundle / "covers").mkdir(parents=True)
    (bundle / "covers" / "x.jpg").write_bytes(b"not an image")
    big = bundle / "covers" / "big.jpg"
    big.write_bytes(b"\xff\xd8\xff" + b"0" * (10 * 1024 * 1024))
    document = {
        "games": [
            {"title": "A", "cover": {"kind": "custom", "file": "covers/x.jpg"}},
            {"title": "B", "cover": {"kind": "custom", "file": "covers/none.jpg"}},
            {"title": "C", "cover": {"kind": "custom", "file": "covers/big.jpg"}},
        ]
    }
    reply = await call("import_data", {"document": document, "files_dir": str(bundle)})
    assert reply["ok"] is True
    assert reply["counts"]["covers"] == {"imported": 0, "skipped": 3}
    assert [p["path"] for p in reply["problems"]] == [
        "games[0].cover.file",
        "games[1].cover.file",
        "games[2].cover.file",
    ]
    assert reply["problems"][0] == {
        "level": "warning",
        "path": "games[0].cover.file",
        "message": "The cover file covers/x.jpg is not a valid image.",
    }
    games = coordinator(setup_entry).store.state["games"].values()
    assert sorted(b["title"] for b in games) == ["A", "B", "C"]
    assert all(b["cover"] == {"kind": "none", "file": None} for b in games)
