"""Exact shapes of the records and replies that the pure core builds.

A round trip passes when a key has a wrong name on both sides. These tests pin
each key and each default, so a renamed key or a changed default fails.
"""

from __future__ import annotations

import ex.csv_io as cio
import ex.models as m
import ex.projections as pr
import pytest

NOW = "2026-10-05T12:00:00+00:00"


def _raises(fn, *args, **kwargs) -> m.LibraryError:
    with pytest.raises(m.LibraryError) as info:
        fn(*args, **kwargs)
    return info.value


def test_empty_row() -> None:
    assert cio.empty_row(7) == {
        "line": 7,
        "game_id": None,
        "title": "",
        "summary": "",
        "genres": [],
        "release_date": "",
        "franchise": None,
        "igdb_id": None,
        "barcode": None,
        "tags": [],
        "shared_notes": "",
        "owned": 0,
        "copy": None,
        "location": [],
        "status": None,
        "wishlist": False,
        "wishlist_buy": False,
        "rating": None,
        "page": None,
        "started": None,
        "finished": None,
        "read_count": None,
        "notes": "",
        "needs_details": True,
    }


def test_build_game_shape() -> None:
    game = m.build_game({"title": "Dune"}, now=NOW)
    assert game == {
        "id": game["id"],
        "title": "Dune",
        "summary": "",
        "genres": [],
        "release_date": "",
        "franchise": None,
        "igdb_id": None,
        "tags": [],
        "shared_notes": "",
        "cover": {"kind": "none", "file": None},
        "needs_details": False,
        "created_at": NOW,
        "updated_at": NOW,
        "wishlist": None,
    }


def test_location_shapes() -> None:
    room = m.build_room({"name": "Den", "area_id": "office"}, order=2)
    assert room == {"id": room["id"], "name": "Den", "area_id": "office", "order": 2}
    case = m.build_unit({"room_id": "r", "name": "Left"}, order=1)
    assert case == {
        "id": case["id"],
        "room_id": "r",
        "name": "Left",
        "note": "",
        "order": 1,
    }
    shelf = m.build_shelf({"unit_id": "k", "name": "Top", "order": 4}, order=0)
    assert shelf == {"id": shelf["id"], "unit_id": "k", "name": "Top", "order": 4}


def test_copy_and_loan_shapes() -> None:
    copy = m.build_copy({"game_id": "b"}, now=NOW)
    assert copy == {
        "id": copy["id"],
        "game_id": "b",
        "shelf_id": None,
        "platform": "other",
        "format": "physical",
        "storefront": "",
        "region": "",
        "edition": "",
        "steelbook": False,
        "barcode": None,
        "condition": None,
        "acquired": None,
        "acquired_from": "",
        "price": None,
        "value": None,
        "note": "",
        "created_at": NOW,
    }
    loan = m.build_loan(
        {"direction": "out", "copy_id": "c", "game_id": "b", "party": " Al "},
        today="2026-10-05",
    )
    assert loan == {
        "id": loan["id"],
        "direction": "out",
        "game_id": "b",
        "copy_id": "c",
        "party": "Al",
        "person_id": None,
        "format": None,
        "started": "2026-10-05",
        "due": None,
        "returned": None,
        "note": "",
        "hk_task_id": None,
        "add_task": True,
        "overdue_fired": False,
    }
    err = _raises(m.build_loan, {}, today="x")
    assert err.key == "invalid_choice" and err.placeholders["field"] == "direction"
    err = _raises(
        m.build_loan,
        {"direction": "out", "copy_id": "c", "party": "x"},
        today="2026-10-05",
    )
    assert err.placeholders == {"field": "game_id"}
    err = _raises(
        m.build_loan,
        {"direction": "out", "copy_id": "c", "game_id": "b", "party": "x", "due": 3},
        today="2026-10-05",
    )
    assert err.key == "invalid_date" and err.placeholders == {"field": "due"}
    err = _raises(
        m.build_loan,
        {"direction": "out", "copy_id": "c", "game_id": "b", "party": "x", "note": 5j},
        today="2026-10-05",
    )
    assert err.placeholders == {"field": "note"}
    loan = m.build_loan(
        {
            "direction": "in",
            "game_id": "b",
            "party": "x",
            "person_id": "p",
            "copy_id": "c",
            "started": "2026-01-01",
            "note": "n",
        },
        today="2026-10-05",
    )
    assert loan["copy_id"] is None and loan["started"] == "2026-01-01"
    assert loan["note"] == "n"


def test_field_names_in_errors() -> None:
    def key(fn, *args, **kwargs):
        with pytest.raises(m.LibraryError) as info:
            fn(*args, **kwargs)
        return info.value.key, info.value.placeholders

    assert key(m.build_room, {"name": "x", "area_id": []}, order=0) == (
        "invalid_field",
        {"field": "area_id"},
    )
    assert key(m.build_unit, {"room_id": "r", "name": "x", "note": []}, order=0)[1] == {
        "field": "note"
    }
    assert key(m.build_shelf, {"unit_id": "k", "name": ""}, order=0)[1] == {
        "field": "name"
    }
    assert key(m.build_copy, {"game_id": "b", "price": -1}, now=NOW)[1]["field"] == (
        "price"
    )
    assert key(m.build_copy, {"game_id": "b", "value": "x"}, now=NOW)[1] == {
        "field": "value"
    }
    assert key(m.copy_field, "condition", "mint")[1]["field"] == "condition"
    assert key(m.copy_field, "acquired", "soon")[1] == {"field": "acquired"}
    assert key(m.copy_field, "steelbook", 1)[1] == {"field": "steelbook"}
    assert key(m.copy_field, "platform", "wii")[1]["field"] == "platform"
    assert key(m.copy_field, "storefront", [])[1] == {"field": "storefront"}
    assert key(m.copy_field, "region", "x" * 21)[1]["field"] == "region"
    for gone in ("signed", "first_edition"):
        assert key(m.copy_field, gone, True)[1] == {"field": gone}
    assert key(m.copy_field, "note", [])[1] == {"field": "note"}
    assert key(m.copy_field, "acquired_from", [])[1] == {"field": "acquired_from"}
    assert key(m.copy_field, "barcode", [])[1] == {"field": "barcode"}
    assert key(m.game_field, "barcode", "1")[1] == {"field": "barcode"}
    assert key(m.game_field, "barcode", True)[1] == {"field": "barcode"}
    assert key(m.copy_field, "barcode", "a b#")[1] == {"barcode": "AB#"}
    assert key(m.game_field, "catalogs", {})[1] == {"field": "catalogs"}
    assert key(m.game_field, "franchise", [1])[1] == {"field": "franchise"}
    assert key(m.game_field, "igdb_id", "x")[1] == {"field": "igdb_id"}
    assert key(m.game_field, "summary", [])[1] == {"field": "summary"}
    assert key(m.game_field, "needs_details", "yes")[1] == {"field": "needs_details"}
    assert key(m.game_field, "genres", 3)[1] == {"field": "genres"}
    for gone in ("authors", "pages", "series", "subtitle", "description"):
        assert key(m.game_field, gone, None)[1] == {"field": gone}
    assert key(m.reading_field, "started", "x")[1] == {"field": "started"}
    assert key(m.reading_field, "page", -1)[1]["field"] == "page"
    assert key(m.reading_field, "private_notes", [])[1] == {"field": "private_notes"}
    assert key(m.update_location, "room", {"name": "a"}, {"area_id": []})[1] == {
        "field": "area_id"
    }
    assert key(m.update_location, "room", {"name": "a"}, {"order": "x"})[1] == {
        "field": "order"
    }
    assert key(m.update_location, "unit", {"name": "a"}, {"note": []})[1] == {
        "field": "note"
    }
    assert key(m.update_location, "room", {"name": "a"}, {"name": "b" * 101})[1] == {
        "field": "name",
        "max": "100",
    }
    loan = {"started": "2026-10-01", "due": None}
    assert key(m.update_loan, loan, {"party": ""})[1] == {"field": "party"}
    assert key(m.update_loan, loan, {"note": []})[1] == {"field": "note"}
    assert key(m.update_loan, loan, {"format": "x"})[1]["field"] == "format"
    assert key(m.update_loan, loan, {"due": "x"})[1] == {"field": "due"}
    assert key(m.apply_person_settings, {}, {"share_reading": 1})[1] == {
        "field": "share_reading"
    }
    assert key(m.apply_person_settings, {}, {"yearly_goal": 0})[1]["field"] == (
        "yearly_goal"
    )


def test_barcode_field() -> None:
    assert m.copy_field("barcode", " 978-0441 478125 ") == "9780441478125"
    assert m.copy_field("barcode", "abc123") == "ABC123"
    assert m.copy_field("barcode", 4006381333931) == "4006381333931"
    assert m.copy_field("barcode", "") is None
    assert m.copy_field("barcode", None) is None
    assert m.copy_field("barcode", "9" * 50) == "9" * 50
    err = _raises(m.copy_field, "barcode", "9" * 51)
    assert (err.key, err.placeholders) == ("invalid_barcode", {"barcode": "9" * 50})
    err = _raises(m.copy_field, "barcode", " - ")
    assert (err.key, err.placeholders) == ("invalid_barcode", {"barcode": ""})
    assert m.game_field("franchise", " Zelda ") == "Zelda"
    assert m.game_field("franchise", "") is None
    assert m.game_field("igdb_id", "7346") == 7346
    assert m.game_field("igdb_id", None) is None
    assert m.game_field("igdb_id", 2**53) == 2**53
    err = _raises(m.game_field, "igdb_id", 0)
    assert err.key == "out_of_range" and err.placeholders["field"] == "igdb_id"
    assert _raises(m.game_field, "igdb_id", 2**53 + 1).key == "out_of_range"
    assert m.game_field("genres", ["RPG", "RPG", "Action"]) == ["RPG", "Action"]
    assert m.game_field("release_date", 2017) == "2017"


def _two_games() -> dict:
    state = m.empty_state()
    for game_id, title, stamp in (("z", "Apple", "t2"), ("a", "Zed", "t1")):
        game = m.build_game({"title": title}, now=stamp)
        game["id"] = game_id
        state["games"][game_id] = game
    for copy_id, stamp in (("c2", "t1"), ("c1", "t2")):
        copy = m.build_copy({"game_id": "a"}, now=stamp)
        copy["id"] = copy_id
        state["copies"][copy_id] = copy
    state["reading"]["p"] = {"a": {**m.empty_reading(now=NOW), "status": "read"}}
    return state


def test_rows_from_state_order_and_reading() -> None:
    state = _two_games()
    rows = cio.rows_from_state(state, "p")
    assert [(r["game_id"], (r["copy"] or {}).get("id")) for r in rows] == [
        ("z", None),
        ("a", "c2"),
        ("a", "c1"),
    ]
    assert [r["line"] for r in rows] == [1, 2, 3]
    assert rows[1]["status"] == "read" and rows[0]["status"] is None
    assert cio.rows_from_state(state, None)[1]["status"] is None
    assert [r["owned"] for r in rows] == [0, 2, 2]


def test_cells() -> None:
    row = cio.empty_row(1)
    row.update(
        title="T",
        barcode="9780441478125",
        status="read",
        rating=4,
        finished="2026-01-02",
        read_count=2,
        tags=["fav"],
        owned=1,
        copy={"format": "digital"},
        notes="n",
    )
    row.update(
        game_id="b",
        franchise="F",
        igdb_id=7346,
        copy={
            "id": "c",
            "format": "digital",
            "condition": "good",
            "acquired": "2020-01-01",
            "acquired_from": "Shop",
            "price": 3,
            "value": None,
            "platform": "ps5",
            "storefront": "PlayStation Store",
            "region": "PAL",
            "edition": "Deluxe",
            "steelbook": True,
            "note": "cn",
        },
        location=["R", "B", "S"],
        page=9,
        started="2025-12-01",
        wishlist=True,
        wishlist_buy=False,
        genres=["x", "y"],
        release_date="2001",
        summary="D",
        shared_notes="sn",
    )
    assert cio._library_cells(row) == {
        "game_id": "b",
        "title": "T",
        "summary": "D",
        "genres": "x; y",
        "release_date": "2001",
        "franchise": "F",
        "igdb_id": "7346",
        "tags": "fav",
        "shared_notes": "sn",
        "copy_id": "c",
        "platform": "ps5",
        "format": "digital",
        "storefront": "PlayStation Store",
        "region": "PAL",
        "edition": "Deluxe",
        "steelbook": "true",
        "barcode": "9780441478125",
        "condition": "good",
        "acquired": "2020-01-01",
        "acquired_from": "Shop",
        "price": "3",
        "value": "",
        "copy_note": "cn",
        "location": "R / B / S",
        "status": "read",
        "rating": "4",
        "page": "9",
        "started": "2025-12-01",
        "finished": "2026-01-02",
        "read_count": "2",
        "private_notes": "n",
        "wishlist": "true",
        "wishlist_buy": "false",
    }
    empty = cio._library_cells(cio.empty_row(1))
    assert empty["steelbook"] == "" and empty["platform"] == ""
    assert empty["game_id"] == "" and empty["franchise"] == ""
    assert empty["igdb_id"] == "" and empty["genres"] == ""
    assert empty["barcode"] == ""
    assert empty["wishlist"] == "false" and empty["format"] == ""


def test_project_state_counts_and_order() -> None:
    state = _two_games()
    state["rooms"] = {
        "r2": {"id": "r2", "name": "b", "order": 0},
        "r1": {"id": "r1", "name": "a", "order": 0},
    }
    state["units"] = {
        "k1": {"id": "k1", "room_id": "r2", "name": "x", "order": 0},
        "k2": {"id": "k2", "room_id": "r1", "name": "y", "order": 5},
        "k3": {"id": "k3", "room_id": "r1", "name": "z", "order": 1},
    }
    reply = pr.project_state(
        state,
        persons=[],
        viewer=None,
        is_admin=True,
        currency="EUR",
        tab=False,
        revision=0,
    )
    assert [r["id"] for r in reply["rooms"]] == ["r1", "r2"]
    assert [b["id"] for b in reply["units"]] == ["k3", "k2", "k1"]
    zed = next(b for b in reply["games"] if b["id"] == "a")
    assert zed["copy_count"] == 2 and zed["owned"] is True
    assert [c["id"] for c in reply["copies"]] == ["c2", "c1"]
    assert reply["me"] == {"person_id": None, "name": None, "is_admin": True}


def test_game_matches_joins_fields_with_a_space() -> None:
    state = m.empty_state()
    game = m.build_game({"title": "Dune"}, now=NOW)
    state["games"][game["id"]] = game
    copy = m.build_copy({"game_id": game["id"], "barcode": "123"}, now=NOW)
    state["copies"][copy["id"]] = copy
    assert pr.game_matches(state, game, {"query": "dune 123"})
    assert not pr.game_matches(state, game, {"query": "dune123"})
    game["franchise"] = "Chronicles"
    assert pr.game_matches(state, game, {"query": "chronicles"})
    game["genres"] = ["Strategy"]
    assert pr.game_matches(state, game, {"query": "strategy"})


def test_game_detail_order_and_projection() -> None:
    state = _two_games()
    state["loans"] = {
        "l2": {"id": "l2", "game_id": "a", "started": "2026-02-01", "party": "X"},
        "l1": {"id": "l1", "game_id": "a", "started": "2026-01-01", "party": "Y"},
        "l3": {"id": "l3", "game_id": "z", "started": "2026-01-01", "party": "Z"},
    }
    state["reading"]["q"] = {"a": {**m.empty_reading(now=NOW), "private_notes": "s"}}
    detail = pr.game_detail(state, "a", viewer="p", is_admin=False)
    assert [c["id"] for c in detail["copies"]] == ["c2", "c1"]
    assert [lo["id"] for lo in detail["loans"]] == ["l1", "l2"]
    assert "private_notes" not in detail["reading"]["q"]
    assert "party" not in detail["loans"][0]


def test_cover_url_token() -> None:
    game = {"id": "b", "cover": {"kind": "custom", "file": "b-12ab34cd.jpg"}}
    assert pr.cover_url(game) == "/api/home_keeper_games/cover/b?v=12ab34cd"
