"""Unit tests for the pure event payload builders."""

from __future__ import annotations

import ex.events as ev

GAME = {"id": "b1", "title": "Dune"}
COPY = {"id": "c1", "shelf_id": "s1"}
LOAN = {
    "id": "l1",
    "direction": "in",
    "copy_id": None,
    "party": "Alex",
    "person_id": "p1",
    "started": "2026-10-01",
    "due": "2026-10-10",
    "returned": None,
}


def test_location_payloads() -> None:
    assert ev.room_event_data({"id": "r", "name": "Den"}, "o") == {
        "room_id": "r",
        "name": "Den",
        "origin": "o",
    }
    assert ev.unit_event_data({"id": "k", "room_id": "r", "name": "L"}, None) == {
        "unit_id": "k",
        "room_id": "r",
        "name": "L",
        "origin": None,
    }
    assert ev.shelf_event_data({"id": "s", "unit_id": "k", "name": "T"}, None) == {
        "shelf_id": "s",
        "unit_id": "k",
        "name": "T",
        "origin": None,
    }
    fields = ["name"]
    data = ev.location_changed_data({"a": 1}, fields)
    assert data == {"a": 1, "changed_fields": ["name"]}
    fields.append("x")
    assert data["changed_fields"] == ["name"], "the payload must not alias the list"


def test_game_payloads() -> None:
    assert ev.game_event_data(GAME, None) == {
        "game_id": "b1",
        "title": "Dune",
        "person_id": None,
        "origin": None,
    }
    assert ev.game_event_data({"id": "b2"}, "o", "p")["title"] == ""
    assert ev.game_updated_event_data(GAME, ["title"], "o")["changed_fields"] == [
        "title"
    ]
    assert ev.copy_event_data(GAME, COPY, None)["copy_id"] == "c1"
    moved = ev.copy_moved_event_data(GAME, COPY, "s0", None)
    assert moved["shelf_id"] == "s1" and moved["previous_shelf_id"] == "s0"


def test_progress_payloads() -> None:
    changed = ev.progress_changed_event_data(
        GAME, "p1", "ps5", "completed", "playing", "o"
    )
    assert changed == {
        "game_id": "b1",
        "title": "Dune",
        "person_id": "p1",
        "origin": "o",
        "platform": "ps5",
        "play_status": "completed",
        "previous_status": "playing",
    }
    row = {"completed_at": "2026-10-05", "rating": 4, "completion_count": 2}
    completed = ev.game_completed_event_data(GAME, "p1", "switch", row, None)
    assert completed["platform"] == "switch"
    assert completed["completed_at"] == "2026-10-05"
    assert completed["rating"] == 4 and completed["completion_count"] == 2
    empty = ev.game_completed_event_data(GAME, "p1", "ps5", {}, None)
    assert empty["completion_count"] == 0


def test_loan_and_wishlist_payloads() -> None:
    loan = ev.loan_event_data(GAME, LOAN, None)
    assert loan["person_id"] == "p1" and loan["loan_id"] == "l1"
    assert loan["direction"] == "in" and loan["party"] == "Alex"
    assert loan["started"] == "2026-10-01" and loan["due"] == "2026-10-10"
    assert loan["returned"] is None and loan["copy_id"] is None
    wish = ev.wishlist_event_data(GAME, {"person_id": "p2", "buy": 1}, None)
    assert wish["person_id"] == "p2" and wish["buy"] is True
    assert wish["bought"] is False


def test_import_payload() -> None:
    data = ev.import_completed_event_data(
        {"rows": 3, "games_added": 2, "errors": 1}, "p", "csv", None
    )
    assert data == {
        "person_id": "p",
        "source": "csv",
        "rows": 3,
        "games_added": 2,
        "games_matched": 0,
        "copies_added": 0,
        "progress_set": 0,
        "wishlist_added": 0,
        "errors": 1,
        "origin": None,
    }


def test_change_payloads_name_the_fields() -> None:
    fields = ["note", "price"]
    copy = ev.copy_updated_event_data(GAME, COPY, fields, "o")
    assert copy == {
        "game_id": "b1",
        "title": "Dune",
        "person_id": None,
        "origin": "o",
        "copy_id": "c1",
        "shelf_id": "s1",
        "changed_fields": ["note", "price"],
    }
    progress = ev.progress_updated_event_data(GAME, "p1", "pc", "playing", fields, "o")
    assert progress == {
        "game_id": "b1",
        "title": "Dune",
        "person_id": "p1",
        "origin": "o",
        "platform": "pc",
        "play_status": "playing",
        "changed_fields": ["note", "price"],
    }
    loan = ev.loan_updated_event_data(GAME, LOAN, fields, "o")
    assert loan == {**ev.loan_event_data(GAME, LOAN, "o"), "changed_fields": fields}
    person = ev.person_settings_event_data("p1", fields, "o")
    assert person == {"person_id": "p1", "changed_fields": fields, "origin": "o"}
    settings = ev.settings_event_data(fields, "EUR", None)
    assert settings == {"changed_fields": fields, "currency": "EUR", "origin": None}
    fields.append("x")
    for payload in (copy, progress, loan, person, settings):
        assert payload["changed_fields"] == ["note", "price"], "no alias"


def test_data_imported_payload() -> None:
    counts = {"games": {"created": 2, "updated": True, "skipped": 0}}
    data = ev.data_imported_event_data(counts, "home_keeper")
    assert data == {
        "counts": {"games": {"created": 2, "updated": 1, "skipped": 0}},
        "origin": "home_keeper",
    }
    assert type(data["counts"]["games"]["updated"]) is int
    # The payload has its own copy of the counts.
    counts["games"]["created"] = 9
    assert data["counts"]["games"]["created"] == 2
