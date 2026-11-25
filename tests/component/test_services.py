"""Component tests: the services, their gates, their events and their replies."""

from __future__ import annotations

import pytest
from homeassistant.exceptions import ServiceValidationError, Unauthorized
from pytest_homeassistant_custom_component.common import async_capture_events

from custom_components.home_keeper_games.api_surface import SERVICES

ALICE = "p_alice"
BOB = "p_bob"
CAROL = "p_carol"
EVENT = "home_keeper_games_{}".format

# The smallest valid data for each admin-only service. A non-admin user must
# get Unauthorized before the data is even read.
_ADMIN_DATA = {
    "add_room": {"name": "x"},
    "update_room": {"room_id": "x"},
    "delete_room": {"room_id": "x"},
    "add_unit": {"room_id": "x", "name": "x"},
    "update_unit": {"unit_id": "x"},
    "delete_unit": {"unit_id": "x"},
    "add_shelf": {"unit_id": "x", "name": "x"},
    "update_shelf": {"shelf_id": "x"},
    "delete_shelf": {"shelf_id": "x"},
    "add_game": {"title": "x"},
    "update_game": {"game_id": "x"},
    "set_igdb_game": {"game_id": "x", "igdb_id": 1},
    "delete_game": {"game_id": "x"},
    "scan_barcode": {"barcode": "0711719505012"},
    "add_copy": {"game_id": "x"},
    "update_copy": {"copy_id": "x"},
    "move_copy": {"copy_id": "x"},
    "delete_copy": {"copy_id": "x"},
    "set_cover": {"game_id": "x", "kind": "none"},
    "lend_game": {"copy_id": "x", "party": "x"},
    "borrow_game": {"title": "x", "party": "x", "person_id": BOB},
    "return_loan": {"loan_id": "x"},
    "update_loan": {"loan_id": "x"},
    "delete_loan": {"loan_id": "x"},
    "add_to_wishlist": {"title": "x", "person_id": BOB},
    "update_wishlist": {"game_id": "x"},
    "remove_from_wishlist": {"game_id": "x"},
    "got_wishlist_game": {"game_id": "x"},
    "import_csv": {"content": "title\nx\n", "person_id": BOB},
    "export_csv": {},
    "export_data": {},
    "import_data": {"document": {}},
    "set_settings": {"currency": "USD"},
}


def test_every_admin_service_has_gate_data() -> None:
    admin = {spec.name for spec in SERVICES if spec.admin_only}
    assert admin == set(_ADMIN_DATA)


@pytest.mark.parametrize("service", sorted(_ADMIN_DATA))
async def test_admin_services_reject_a_non_admin_user(
    hass, setup_entry, call, service
) -> None:
    with pytest.raises(Unauthorized):
        await call(service, _ADMIN_DATA[service], as_="user")


async def _shelf(call) -> dict:
    room = (await call("add_room", {"name": "Den"}))["room"]
    case = (await call("add_unit", {"room_id": room["id"], "name": "Left"}))["unit"]
    return (await call("add_shelf", {"unit_id": case["id"], "name": "Top"}))["shelf"]


async def _game(call, **data) -> dict:
    return (await call("add_game", {"title": "Dune", **data}))["game"]


async def test_locations_and_delete_rules(hass, setup_entry, call) -> None:
    added = async_capture_events(hass, EVENT("room_added"))
    updated = async_capture_events(hass, EVENT("room_updated"))
    removed = async_capture_events(hass, EVENT("shelf_removed"))
    moved = async_capture_events(hass, EVENT("copy_moved"))
    shelf = await _shelf(call)
    case_id = shelf["unit_id"]
    room_id = setup_entry.runtime_data.store.state["units"][case_id]["room_id"]
    assert added[0].data == {"room_id": room_id, "name": "Den", "origin": None}
    second = (await call("add_room", {"name": "Attic"}))["room"]
    assert second["order"] == 1
    reply = await call("update_room", {"room_id": room_id, "name": "Study"})
    assert reply["room"]["name"] == "Study"
    assert updated[0].data["changed_fields"] == ["name"]
    game = await _game(call)
    copy = (await call("add_copy", {"game_id": game["id"], "shelf_id": shelf["id"]}))[
        "copy"
    ]
    with pytest.raises(ServiceValidationError) as info:
        await call("delete_room", {"room_id": room_id})
    assert info.value.translation_key == "room_not_empty"
    assert info.value.translation_placeholders == {"count": "1"}
    with pytest.raises(ServiceValidationError) as info:
        await call("delete_unit", {"unit_id": case_id})
    assert info.value.translation_key == "unit_not_empty"
    with pytest.raises(ServiceValidationError) as info:
        await call("delete_shelf", {"shelf_id": shelf["id"]})
    assert info.value.translation_key == "shelf_not_empty"
    await call("delete_room", {"room_id": room_id, "force": True})
    state = setup_entry.runtime_data.store.state
    assert state["copies"][copy["id"]]["shelf_id"] is None
    assert state["shelves"] == {} and state["units"] == {}
    assert removed[0].data["shelf_id"] == shelf["id"]
    assert moved[0].data["previous_shelf_id"] == shelf["id"]
    assert moved[0].data["shelf_id"] is None
    with pytest.raises(ServiceValidationError) as info:
        await call("update_room", {"room_id": "nope", "name": "x"})
    assert info.value.translation_key == "room_not_found"
    with pytest.raises(ServiceValidationError) as info:
        await call("add_unit", {"room_id": "nope", "name": "x"})
    assert info.value.translation_key == "room_not_found"


async def test_move_unit_and_shelf(hass, setup_entry, call) -> None:
    shelf = await _shelf(call)
    other = (await call("add_room", {"name": "Attic"}))["room"]
    case = await call(
        "update_unit", {"unit_id": shelf["unit_id"], "room_id": other["id"]}
    )
    assert case["unit"]["room_id"] == other["id"]
    new_case = (await call("add_unit", {"room_id": other["id"], "name": "B"}))["unit"]
    moved = await call(
        "update_shelf", {"shelf_id": shelf["id"], "unit_id": new_case["id"]}
    )
    assert moved["shelf"]["unit_id"] == new_case["id"]
    await call("delete_shelf", {"shelf_id": shelf["id"]})
    await call("delete_unit", {"unit_id": new_case["id"]})


async def test_games_and_duplicates(hass, setup_entry, call) -> None:
    added = async_capture_events(hass, EVENT("game_added"))
    game = await _game(call)
    assert "barcode" not in game and game["title"] == "Dune"
    assert game["owned"] is False and game["cover_url"] is None
    await call("add_copy", {"game_id": game["id"], "barcode": "9780441478125"})
    again = await call("add_game", {"barcode": "978-0-441-47812-5"})
    assert again["existing"] is True and again["game"]["id"] == game["id"]
    assert len(added) == 1
    with pytest.raises(ServiceValidationError) as info:
        await call("add_game", {})
    assert info.value.translation_key == "barcode_or_title_required"
    with pytest.raises(ServiceValidationError) as info:
        await call("add_game", {"barcode": "12#3"})
    assert info.value.translation_key == "invalid_barcode"
    updated = async_capture_events(hass, EVENT("game_updated"))
    reply = await call("update_game", {"game_id": game["id"], "igdb_id": 7346})
    assert reply["game"]["igdb_id"] == 7346
    assert updated[0].data["changed_fields"] == ["igdb_id"]
    other = await _game(call, title="Other")
    with pytest.raises(ServiceValidationError) as info:
        await call("add_copy", {"game_id": other["id"], "barcode": "9780441478125"})
    assert info.value.translation_key == "duplicate_barcode"
    with pytest.raises(ServiceValidationError) as info:
        await call("update_game", {"game_id": game["id"], "igdb_id": 0})
    assert info.value.translation_key == "out_of_range"


async def test_delete_game_cascades(hass, setup_entry, call) -> None:
    game = await _game(call)
    copy = (await call("add_copy", {"game_id": game["id"]}))["copy"]
    await call("set_progress", {"game_id": game["id"], "play_status": "playing"})
    await call("lend_game", {"copy_id": copy["id"], "party": "Zed", "add_task": False})
    removed = async_capture_events(hass, EVENT("game_removed"))
    copies_removed = async_capture_events(hass, EVENT("copy_removed"))
    await call("delete_game", {"game_id": game["id"]})
    state = setup_entry.runtime_data.store.state
    assert state["games"] == {} and state["copies"] == {}
    assert state["loans"] == {} and state["progress"] == {}
    assert removed[0].data["game_id"] == game["id"]
    assert copies_removed[0].data["copy_id"] == copy["id"]


async def test_copies(hass, setup_entry, call) -> None:
    shelf = await _shelf(call)
    game = await _game(call)
    added = async_capture_events(hass, EVENT("copy_added"))
    moved = async_capture_events(hass, EVENT("copy_moved"))
    copy = (
        await call(
            "add_copy",
            {
                "game_id": game["id"],
                "format": "physical",
                "platform": "ps5",
                "region": "PAL",
                "price": 12.5,
                "steelbook": True,
            },
        )
    )["copy"]
    assert copy["price"] == 12.5 and copy["steelbook"] is True
    assert copy["platform"] == "ps5" and copy["region"] == "PAL"
    assert added[0].data["copy_id"] == copy["id"]
    reply = await call("move_copy", {"copy_id": copy["id"], "shelf_id": shelf["id"]})
    assert reply["copy"]["shelf_id"] == shelf["id"]
    assert moved[0].data["previous_shelf_id"] is None
    reply = await call("update_copy", {"copy_id": copy["id"], "condition": "good"})
    assert reply["copy"]["condition"] == "good" and len(moved) == 1
    with pytest.raises(ServiceValidationError) as info:
        await call("add_copy", {"game_id": game["id"], "shelf_id": "nope"})
    assert info.value.translation_key == "shelf_not_found"
    digital = (
        await call(
            "add_copy",
            {"game_id": game["id"], "format": "digital", "shelf_id": shelf["id"]},
        )
    )["copy"]
    assert digital["shelf_id"] is None
    with pytest.raises(ServiceValidationError) as info:
        await call("move_copy", {"copy_id": digital["id"], "shelf_id": shelf["id"]})
    assert info.value.translation_key == "digital_copy_no_shelf"
    reply = await call("move_copy", {"copy_id": digital["id"], "shelf_id": None})
    assert reply["copy"]["shelf_id"] is None
    await call("lend_game", {"copy_id": copy["id"], "party": "Zed", "add_task": False})
    with pytest.raises(ServiceValidationError) as info:
        await call("delete_copy", {"copy_id": copy["id"]})
    assert info.value.translation_key == "copy_on_loan"
    with pytest.raises(ServiceValidationError) as info:
        await call("lend_game", {"copy_id": copy["id"], "party": "Al"})
    assert info.value.translation_key == "copy_on_loan"


async def test_set_progress_gates_and_events(hass, setup_entry, call) -> None:
    game = await _game(call)
    changed = async_capture_events(hass, EVENT("progress_changed"))
    completed = async_capture_events(hass, EVENT("game_completed"))
    key = {"game_id": game["id"], "platform": "switch"}
    reply = await call("set_progress", {**key, "play_status": "completed"}, as_="user")
    assert reply["person_id"] == BOB and reply["progress"]["completion_count"] == 1
    assert reply["progress"]["platform"] == "switch"
    assert changed[0].data["play_status"] == "completed"
    assert changed[0].data["platform"] == "switch"
    assert changed[0].data["previous_status"] is None
    assert completed[0].data["person_id"] == BOB
    assert completed[0].data["platform"] == "switch"
    same = await call("set_progress", {**key, "play_status": "completed"}, as_="user")
    assert same["progress"]["platform"] == "switch" and len(changed) == 1
    with pytest.raises(Unauthorized):
        await call("set_progress", {**key, "person_id": ALICE}, as_="user")
    reply = await call("set_progress", {**key, "person_id": CAROL, "rating": 4})
    assert reply["progress"]["rating"] == 4
    assert reply["progress"]["play_status"] == "backlog"
    with pytest.raises(ServiceValidationError) as info:
        await call("set_progress", key, as_=None)
    assert info.value.translation_key == "no_person"
    with pytest.raises(ServiceValidationError) as info:
        await call("set_progress", {**key, "person_id": "ghost"})
    assert info.value.translation_key == "person_not_found"
    with pytest.raises(ServiceValidationError) as info:
        await call("set_progress", {"game_id": game["id"], "play_status": "playing"})
    assert info.value.translation_key == "platform_required"
    reply = await call("set_progress", {**key, "play_status": "none"}, as_="user")
    assert reply["progress"] is None
    assert changed[-1].data["play_status"] is None
    assert changed[-1].data["previous_status"] == "completed"
    reply = await call("set_progress", {**key, "play_status": "none"}, as_="user")
    assert reply["progress"] is None and len(changed) == 3
    rows = setup_entry.runtime_data.store.state["progress"]
    assert BOB not in rows and set(rows[CAROL][game["id"]]) == {"switch"}


async def test_read_services_project_for_a_non_admin(hass, setup_entry, call) -> None:
    shelf = await _shelf(call)
    game = await _game(call)
    await call(
        "add_copy",
        {
            "game_id": game["id"],
            "shelf_id": shelf["id"],
            "price": 10,
            "value": 20,
            "acquired_from": "Shop",
        },
    )
    copy_id = next(iter(setup_entry.runtime_data.store.state["copies"]))
    await call("lend_game", {"copy_id": copy_id, "party": "Zed", "add_task": False})
    for person in (ALICE, CAROL):
        await call(
            "set_progress",
            {
                "game_id": game["id"],
                "person_id": person,
                "play_status": "completed",
                "review": "secret",
            },
        )
    await call("set_person_settings", {"person_id": CAROL, "share_progress": False})
    user_games = await call("list_games", {}, as_="user")
    text = str(user_games)
    for secret in ("Zed", "Shop", "secret", "'price'", "'value'"):
        assert secret not in text, secret
    assert set(user_games["games"][0]["progress"]) == {ALICE}
    detail = await call("get_game", {"game_id": game["id"]}, as_="user")
    assert "party" not in detail["game"]["loans"][0]
    assert "price" not in detail["game"]["copies"][0]
    assert detail["game"]["copies"][0]["location"] == ["Den", "Left", "Top"]
    admin = await call("get_game", {"game_id": game["id"]})
    assert admin["game"]["loans"][0]["party"] == "Zed"
    assert admin["game"]["progress"][CAROL]["other"]["review"] == "secret"
    loans = await call("list_loans", {"status": "open"}, as_="user")
    assert loans["loans"][0]["title"] == "Dune" and "party" not in loans["loans"][0]
    assert (await call("list_loans", {"status": "returned"}))["loans"] == []
    assert (await call("list_loans", {"direction": "in"}))["loans"] == []
    filtered = await call(
        "list_games", {"play_status": "completed", "person_id": CAROL}, as_="user"
    )
    assert filtered == {"games": []}
    own = await call(
        "list_games", {"play_status": "completed", "person_id": ALICE}, as_="user"
    )
    assert len(own["games"]) == 1
    locations = await call("list_locations", {}, as_="user")
    assert locations["rooms"][0]["units"][0]["shelves"][0]["copies"] == 1
    assert locations["no_shelf"] == 0
    people = await call("list_people", {}, as_="user")
    rows = {p["person_id"]: p for p in people["people"]}
    assert rows[CAROL]["share_progress"] is False
    assert "wishlist_todo" not in rows[CAROL] and "wishlist_todo" in rows[BOB]
    with pytest.raises(ServiceValidationError) as info:
        await call("get_game", {"game_id": "nope"}, as_="user")
    assert info.value.translation_key == "game_not_found"


async def test_person_settings(hass, setup_entry, call, todo_list) -> None:
    reply = await call(
        "set_person_settings", {"person_id": BOB, "yearly_goal": 20}, as_="user"
    )
    assert reply["settings"]["yearly_goal"] == 20
    with pytest.raises(Unauthorized):
        await call(
            "set_person_settings",
            {"person_id": BOB, "wishlist_todo": todo_list},
            as_="user",
        )
    with pytest.raises(Unauthorized):
        await call("set_person_settings", {"person_id": ALICE}, as_="user")
    with pytest.raises(ServiceValidationError) as info:
        await call(
            "set_person_settings", {"person_id": BOB, "wishlist_todo": "todo.none"}
        )
    assert info.value.translation_key == "todo_entity_not_found"
    reply = await call(
        "set_person_settings", {"person_id": BOB, "wishlist_todo": todo_list}
    )
    assert reply["settings"]["wishlist_todo"] == todo_list


async def test_wishlist_services(hass, setup_entry, call) -> None:
    shelf = await _shelf(call)
    added = async_capture_events(hass, EVENT("wishlist_added"))
    removed = async_capture_events(hass, EVENT("wishlist_removed"))
    reply = await call(
        "add_to_wishlist",
        {"title": "Emma", "person_id": BOB, "buy": True},
    )
    game = reply["game"]
    assert game["wishlist"]["person_id"] == BOB and game["wishlist"]["buy"] is True
    assert game["needs_details"] is False
    assert added[0].data["buy"] is True
    with pytest.raises(ServiceValidationError) as info:
        await call("add_to_wishlist", {"game_id": game["id"], "person_id": BOB})
    assert info.value.translation_key == "already_on_wishlist"
    # A title that matches a stored game gives that game.
    with pytest.raises(ServiceValidationError) as info:
        await call(
            "add_to_wishlist",
            {"title": "emma", "person_id": BOB},
        )
    assert info.value.translation_key == "already_on_wishlist"
    reply = await call("update_wishlist", {"game_id": game["id"], "buy": False})
    assert reply["game"]["wishlist"]["buy"] is False
    copy = await call(
        "got_wishlist_game",
        {"game_id": game["id"], "shelf_id": shelf["id"], "format": "physical"},
    )
    assert copy["copy"]["shelf_id"] == shelf["id"]
    state = setup_entry.runtime_data.store.state
    assert state["games"][game["id"]]["wishlist"] is None
    assert removed[0].data["game_id"] == game["id"]
    with pytest.raises(ServiceValidationError) as info:
        await call("remove_from_wishlist", {"game_id": game["id"]})
    assert info.value.translation_key == "not_on_wishlist"
    await call("add_to_wishlist", {"game_id": game["id"], "person_id": CAROL})
    await call("remove_from_wishlist", {"game_id": game["id"]})
    assert len(removed) == 2


async def test_import_and_export(hass, setup_entry, call) -> None:
    shelf = await _shelf(call)
    csv_text = (
        "title,genres,barcode,rating,play_status,format,completed_at,wishlist\n"
        "Dune,Strategy,9780441013593,5,completed,physical,2024-01-02,false\n"
        "Emma,Puzzle,,,,,,true\n"
    )
    done = async_capture_events(hass, EVENT("import_completed"))
    dry = await call(
        "import_csv",
        {
            "content": csv_text,
            "person_id": BOB,
            "shelf_id": shelf["id"],
            "dry_run": True,
        },
    )
    assert dry["dry_run"] is True and dry["counts"] == {
        "rows": 2,
        "backlog": 0,
        "playing": 0,
        "completed": 1,
        "abandoned": 0,
        "wishlist": 1,
        "copies": 1,
        "tags": 0,
        "errors": 0,
        "existing": 0,
        "new": 2,
        "title_match": 0,
    }
    assert dry["rows"][0] == {
        "line": 1,
        "title": "Dune",
        "barcode": "9780441013593",
        "game_id": dry["rows"][0]["game_id"],
        "action": "new",
        "message": "",
    }
    assert setup_entry.runtime_data.store.state["games"] == {}
    assert done == []
    real = await call(
        "import_csv",
        {
            "content": csv_text,
            "person_id": BOB,
            "shelf_id": shelf["id"],
        },
    )
    assert real["counts"]["copies"] == 1 and real["truncated"] is False
    assert [row["action"] for row in real["rows"]] == ["new", "new"]
    assert done[0].data["games_added"] == 2 and done[0].data["person_id"] == BOB
    state = setup_entry.runtime_data.store.state
    assert len(state["games"]) == 2 and len(state["copies"]) == 1
    exported = await call("export_csv", {"person_id": BOB})
    assert exported["filename"].startswith("games-")
    assert exported["content"].startswith("game_id,title")
    assert ",9780441013593," in exported["content"]
    assert ",completed," in exported["content"]
    with pytest.raises(ServiceValidationError) as info:
        await call(
            "import_csv",
            {"content": "Name\nx\n", "person_id": BOB},
        )
    assert info.value.translation_key == "csv_unreadable"
    with pytest.raises(ServiceValidationError) as info:
        await call(
            "import_csv",
            {
                "content": "x" * (5 * 1024 * 1024 + 1),
                "person_id": BOB,
            },
        )
    assert info.value.translation_key == "csv_too_large"


async def test_service_without_a_loaded_entry(hass, setup_entry, call) -> None:
    from custom_components.home_keeper_games import services

    await hass.config_entries.async_unload(setup_entry.entry_id)
    with pytest.raises(ServiceValidationError) as info:
        services.coordinator_or_error(hass)
    assert info.value.translation_key == "not_loaded"


async def test_import_row_error_message(hass, setup_entry, call) -> None:
    reply = await call(
        "import_csv",
        {
            "content": "title,genres\n,Puzzle\n",
            "person_id": BOB,
            "dry_run": True,
        },
    )
    assert reply["rows"][0]["action"] == "error"
    assert reply["rows"][0]["message"] == "title is required."


async def test_set_settings_changes_the_currency(hass, setup_entry, call, ws) -> None:
    client = await ws("admin")
    await client.send_json_auto_id({"type": "home_keeper_games/subscribe"})
    first = await client.receive_json()
    reply = await call("set_settings", {"currency": "usd"})
    assert reply == {"currency": "USD"}
    assert setup_entry.options["currency"] == "USD"
    assert setup_entry.runtime_data.currency == "USD"
    pushed = await client.receive_json()
    assert pushed["event"]["revision"] == first["result"]["revision"] + 1
    with pytest.raises(ServiceValidationError) as info:
        await call("set_settings", {"currency": "dollars"})
    assert info.value.translation_key == "invalid_currency"
    assert info.value.translation_placeholders == {"currency": "dollars"}
