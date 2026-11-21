"""Component tests: each change that keeps the record fires an event.

A copy change with no move, a loan change, a deleted loan, a reading change
that keeps the status, the settings of a person and the currency each fire a
``home_keeper_games_<noun>_<verb>`` event from the store.
"""

from __future__ import annotations

from pytest_homeassistant_custom_component.common import async_capture_events

BOB = "p_bob"
EVENT = "home_keeper_games_{}".format


async def _game(call) -> dict:
    return (await call("add_game", {"title": "Dune"}))["game"]


async def test_copy_updated(hass, setup_entry, call) -> None:
    updated = async_capture_events(hass, EVENT("copy_updated"))
    moved = async_capture_events(hass, EVENT("copy_moved"))
    game = await _game(call)
    copy = (await call("add_copy", {"game_id": game["id"]}))["copy"]
    await call("update_copy", {"copy_id": copy["id"], "price": 12, "signed": True})
    assert [e.data for e in updated] == [
        {
            "game_id": game["id"],
            "title": "Dune",
            "person_id": None,
            "origin": None,
            "copy_id": copy["id"],
            "shelf_id": None,
            "changed_fields": ["price", "signed"],
        }
    ]
    assert "price" not in updated[0].data and moved == []
    # No change fires nothing.
    await call("update_copy", {"copy_id": copy["id"], "price": 12})
    assert len(updated) == 1


async def test_loan_updated_and_removed(hass, setup_entry, call) -> None:
    updated = async_capture_events(hass, EVENT("loan_updated"))
    removed = async_capture_events(hass, EVENT("loan_removed"))
    game = await _game(call)
    copy = (await call("add_copy", {"game_id": game["id"]}))["copy"]
    loan = (
        await call(
            "lend_game", {"copy_id": copy["id"], "party": "Zed", "add_task": False}
        )
    )["loan"]
    await call("update_loan", {"loan_id": loan["id"], "due": "2099-01-01"})
    assert len(updated) == 1
    assert updated[0].data["loan_id"] == loan["id"]
    assert updated[0].data["due"] == "2099-01-01"
    assert updated[0].data["changed_fields"] == ["due"]
    assert "note" not in updated[0].data
    await call("update_loan", {"loan_id": loan["id"], "due": "2099-01-01"})
    assert len(updated) == 1
    await call("delete_loan", {"loan_id": loan["id"]})
    assert [e.data["loan_id"] for e in removed] == [loan["id"]]
    assert removed[0].data["game_id"] == game["id"]
    assert "changed_fields" not in removed[0].data


async def test_reading_updated_keeps_the_notes_private(hass, setup_entry, call) -> None:
    updated = async_capture_events(hass, EVENT("reading_updated"))
    changed = async_capture_events(hass, EVENT("reading_changed"))
    game = await _game(call)
    await call(
        "set_reading", {"game_id": game["id"], "person_id": BOB, "status": "reading"}
    )
    assert len(changed) == 1 and updated == []
    await call(
        "set_reading",
        {
            "game_id": game["id"],
            "person_id": BOB,
            "page": 40,
            "private_notes": "secret",
        },
    )
    assert len(changed) == 1
    assert [e.data for e in updated] == [
        {
            "game_id": game["id"],
            "title": "Dune",
            "person_id": BOB,
            "origin": None,
            "status": "reading",
            "changed_fields": ["page", "private_notes"],
        }
    ]
    assert "secret" not in str(updated[0].data)
    await call("set_reading", {"game_id": game["id"], "person_id": BOB, "page": 40})
    assert len(updated) == 1


async def test_person_settings_updated(hass, setup_entry, call, todo_list) -> None:
    updated = async_capture_events(hass, EVENT("person_settings_updated"))
    await call(
        "set_person_settings",
        {"person_id": BOB, "share_reading": False, "wishlist_todo": todo_list},
    )
    assert [e.data for e in updated] == [
        {
            "person_id": BOB,
            "changed_fields": ["share_reading", "wishlist_todo"],
            "origin": None,
        }
    ]
    await call("set_person_settings", {"person_id": BOB, "share_reading": False})
    assert len(updated) == 1


async def test_settings_updated(hass, setup_entry, call) -> None:
    updated = async_capture_events(hass, EVENT("settings_updated"))
    await call("set_settings", {"currency": "usd"})
    await hass.async_block_till_done()
    assert [e.data for e in updated] == [
        {"changed_fields": ["currency"], "currency": "USD", "origin": None}
    ]
    await call("set_settings", {"currency": "USD"})
    await hass.async_block_till_done()
    assert len(updated) == 1
    # The options flow fires it too.
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {"currency": "GBP"}
    )
    await hass.async_block_till_done()
    assert [e.data["currency"] for e in updated] == ["USD", "GBP"]
