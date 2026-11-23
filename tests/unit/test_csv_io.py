"""Unit tests for the pure CSV import and export."""

from __future__ import annotations

import csv
import io
import string

import ex.csv_io as cio
import ex.models as m
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

NOW = "2026-10-05T12:00:00+00:00"
LEFT = "9780441478125"

LIB = (
    "\ufefftitle,franchise,barcode,genres,release_date,format,status,rating,finished,"
    "read_count,private_notes,tags,wishlist\n"
    f"The Left Hand of Darkness,Hainish,{LEFT},Science fiction,1969,paperback,read,5,"
    '2024-03-05,2,"Great\ngame",favorites,false\n'
    "Dune,,,Science fiction; Classic,,,reading,,,,,,false\n"
    "Emma,,,,,,,,,,,,true\n"
    "Persuasion,,,,,hardcover,want,,,,,,false\n"
    "Ulysses,,,,,,dnf,,,,,,false\n"
    "Notes,,,,,,,,,,,,false\n"
)


def test_parse() -> None:
    rows = cio.parse(LIB)
    assert [r["line"] for r in rows] == [1, 2, 3, 4, 5, 6]
    left = rows[0]
    assert left["title"] == "The Left Hand of Darkness"
    assert left["franchise"] == "Hainish" and left["genres"] == ["Science fiction"]
    assert left["barcode"] == LEFT
    assert left["status"] == "read" and left["rating"] == 5
    assert left["finished"] == "2024-03-05" and left["read_count"] == 2
    assert left["owned"] == 1 and left["copy"]["format"] == "paperback"
    assert left["tags"] == ["favorites"] and left["notes"] == "Great\ngame"
    assert left["release_date"] == "1969"
    dune = rows[1]
    assert (
        dune["genres"] == ["Science fiction", "Classic"] and dune["franchise"] is None
    )
    assert dune["barcode"] is None and dune["status"] == "reading"
    assert dune["rating"] is None and dune["copy"] is None and dune["owned"] == 0
    assert rows[2]["wishlist"] is True and rows[2]["status"] is None
    assert rows[3]["status"] == "want" and rows[3]["copy"]["format"] == "hardcover"
    assert rows[4]["status"] == "dnf"
    assert rows[5]["status"] is None and rows[5]["tags"] == []
    assert not any(r["needs_details"] for r in rows)


def test_parse_cleans_the_barcode() -> None:
    rows = cio.parse("title,barcode\nA, 978-0441 478125 \nB,-\n")
    assert [r["barcode"] for r in rows] == [LEFT, None]


@pytest.mark.parametrize(
    ("value", "rating"),
    [("0", None), ("", None), ("x", None), ("0.4", 1), ("2.5", 3), ("9", 5)],
)
def test_rating(value: str, rating: int | None) -> None:
    assert cio._rating(value) == rating


def test_cell_helpers() -> None:
    assert cio._date("2024/3/5") == "2024-03-05"
    assert cio._date("2024-02-30") is None
    assert cio._date("soon") is None
    assert cio._int(" 7 ") == 7 and cio._int("7.0") is None
    assert cio._float("nan") is None and cio._float("inf") is None
    assert cio._float("1.5") == 1.5
    assert cio._split("a, b,,a") == ["a", "b"]
    assert cio._money_cell("12.0") == 12 and cio._money_cell("-1") is None
    assert cio._money_cell("1.25") == 1.25 and cio._money_cell("") is None
    assert cio._bool_cell("Yes") and cio._bool_cell("true")
    assert not cio._bool_cell("no")


def test_parse_errors() -> None:
    with pytest.raises(m.LibraryError) as info:
        cio.parse("Name,Author\nx,y\n")
    assert info.value.key == "csv_unreadable"
    assert info.value.placeholders == {"column": "title"}
    assert cio.parse("title\n") == []
    with pytest.raises(m.LibraryError):
        cio.parse("")


def test_parse_library_round_trip() -> None:
    rows = cio.parse_library("title,format,location\nX,scroll,Den / Left\n")
    assert rows[0]["copy"] is None and rows[0]["location"] == ["Den", "Left"]
    assert rows[0]["needs_details"] is False


# ── Import ───────────────────────────────────────────────────────────────────


GAME_HEX = "0123456789abcdef0123456789abcdef"


def _library() -> dict:
    state = m.empty_state()
    state["rooms"]["r"] = {"id": "r", "name": "Den", "order": 0}
    state["units"]["k"] = {"id": "k", "room_id": "r", "name": "Left", "order": 0}
    state["shelves"]["s"] = {"id": "s", "unit_id": "k", "name": "Top", "order": 0}
    game = m.build_game({"title": "Persuasion", "genres": ["Romance"]}, now=NOW)
    game["id"] = "persuasion"
    state["games"]["persuasion"] = game
    return state


def test_apply_import() -> None:
    state = _library()
    rows = cio.parse(LIB)
    new, summary, results = cio.apply_import(
        state,
        rows,
        person_id="p",
        shelf_id="s",
        import_notes=True,
        replace_reading=False,
        now=NOW,
    )
    assert state["games"].keys() == {"persuasion"}, "the input must not change"
    assert summary == {
        "rows": 6,
        "read": 1,
        "reading": 1,
        "want": 1,
        "dnf": 1,
        "wishlist": 1,
        "copies": 2,
        "tags": 1,
        "errors": 0,
        "existing": 0,
        "new": 5,
        "title_match": 1,
        "reading_kept": 0,
    }
    assert [r["action"] for r in results] == [
        "new",
        "new",
        "new",
        "title_match",
        "new",
        "new",
    ]
    assert results[3]["game_id"] == "persuasion"
    assert results[0] == {
        "line": 1,
        "title": "The Left Hand of Darkness",
        "barcode": LEFT,
        "game_id": results[0]["game_id"],
        "action": "new",
    }
    assert cio.summary_of(summary, 2) == {
        "rows": 6,
        "games_added": 5,
        "games_matched": 1,
        "copies_added": 2,
        "reading_set": 4,
        "reading_kept": 2,
        "wishlist_added": 1,
        "errors": 0,
    }
    left = next(b for b in new["games"].values() if b["barcode"] == LEFT)
    assert left["needs_details"] is False and left["tags"] == ["favorites"]
    copies = [c for c in new["copies"].values() if c["game_id"] == left["id"]]
    assert len(copies) == 1 and copies[0]["shelf_id"] == "s"
    assert copies[0]["format"] == "paperback"
    reading = new["reading"]["p"][left["id"]]
    assert reading["status"] == "read" and reading["read_count"] == 2
    assert reading["private_notes"] == "Great\ngame"
    emma = next(b for b in new["games"].values() if b["title"] == "Emma")
    assert emma["wishlist"]["person_id"] == "p" and emma["wishlist"]["buy"] is False
    assert emma["id"] not in new["reading"]["p"]


def test_import_matches_and_keeps_reading() -> None:
    state = _library()
    state["reading"]["p"] = {"persuasion": {**m.empty_reading(now=NOW)}}
    rows = cio.parse(LIB)
    first, _, _ = cio.apply_import(
        state,
        rows,
        person_id="p",
        shelf_id="missing",
        import_notes=False,
        replace_reading=False,
        now=NOW,
    )
    assert first["reading"]["p"]["persuasion"]["status"] == "want"
    left = next(b for b in first["games"].values() if b["barcode"] == LEFT)
    assert first["reading"]["p"][left["id"]]["private_notes"] == ""
    copy = next(c for c in first["copies"].values() if c["game_id"] == left["id"])
    assert copy["shelf_id"] is None
    _second, summary, _results = cio.apply_import(
        first,
        rows,
        person_id="p",
        shelf_id=None,
        import_notes=True,
        replace_reading=False,
        now=NOW,
    )
    assert summary["new"] == 0 and summary["existing"] == 1
    assert summary["title_match"] == 5
    assert summary["copies"] == 0 and summary["reading_kept"] == 4
    assert summary["read"] + summary["reading"] + summary["want"] == 0
    assert summary["wishlist"] == 0
    third, summary, _ = cio.apply_import(
        first,
        rows,
        person_id="p",
        shelf_id=None,
        import_notes=True,
        replace_reading=True,
        now=NOW,
    )
    assert summary["read"] + summary["want"] + summary["dnf"] == 3
    assert summary["reading"] == 1 and summary["reading_kept"] == 0
    assert third["reading"]["p"][left["id"]]["private_notes"] == "Great\ngame"


def test_import_row_error_and_empty_person() -> None:
    state = _library()
    rows = [cio.empty_row(1)]
    new, summary, results = cio.apply_import(
        state,
        rows,
        person_id="p",
        shelf_id=None,
        import_notes=True,
        replace_reading=False,
        now=NOW,
    )
    assert summary["errors"] == 1 and results[0]["action"] == "error"
    assert results[0]["error"] == "field_required"
    assert results[0]["placeholders"] == {"field": "title"}
    assert "p" not in new["reading"]


def test_import_library_rows_use_ids_and_locations() -> None:
    state = _library()
    game = state["games"].pop("persuasion")
    game["id"] = GAME_HEX
    state["games"][GAME_HEX] = game
    copy = m.build_copy({"game_id": GAME_HEX, "shelf_id": "s"}, now=NOW)
    state["copies"][copy["id"]] = copy
    text = cio.export(state, None)
    new, summary, _ = cio.apply_import(
        m.empty_state()
        | {
            "shelves": state["shelves"],
            "units": state["units"],
            "rooms": state["rooms"],
        },
        cio.parse(text),
        person_id="p",
        shelf_id=None,
        import_notes=True,
        replace_reading=False,
        now=NOW,
    )
    assert summary["new"] == 1 and summary["copies"] == 1
    assert new["games"][GAME_HEX]["title"] == "Persuasion"
    assert new["copies"][copy["id"]]["shelf_id"] == "s"
    _, again, _ = cio.apply_import(
        new,
        cio.parse(text),
        person_id="p",
        shelf_id=None,
        import_notes=True,
        replace_reading=False,
        now=NOW,
    )
    assert again["copies"] == 0 and again["existing"] == 1


def test_import_library_ids_that_are_not_record_ids_are_dropped() -> None:
    header = "game_id,copy_id,title,format\n"
    rows = cio.parse(
        header
        + "../../evil,x,Escape,paperback\n"
        + f"{GAME_HEX},{GAME_HEX.upper()},Upper,paperback\n"
        + f"{GAME_HEX}0,{GAME_HEX},Long,paperback\n"
        + f"{GAME_HEX},{GAME_HEX},Good,paperback\n",
    )
    assert [(r["game_id"], r["copy"]["id"]) for r in rows] == [
        (None, None),
        (GAME_HEX, None),
        (None, GAME_HEX),
        (GAME_HEX, GAME_HEX),
    ]


def test_import_row_with_a_bad_copy_adds_no_game() -> None:
    rows = cio.parse("title,format,condition\nPersuasion,paperback,mint\n")
    new, summary, results = cio.apply_import(
        m.empty_state(),
        rows,
        person_id="p",
        shelf_id=None,
        import_notes=True,
        replace_reading=False,
        now=NOW,
    )
    assert results[0]["action"] == "error"
    assert results[0]["error"] == "invalid_choice"
    assert summary["errors"] == 1 and summary["new"] == 0
    assert new["games"] == {} and new["copies"] == {}


def test_import_sets_the_reading_of_a_game_once() -> None:
    state = _library()
    for _ in range(2):
        copy = m.build_copy({"game_id": "persuasion"}, now=NOW)
        state["copies"][copy["id"]] = copy
    state["reading"]["p"] = {
        "persuasion": m.empty_reading(now=NOW) | {"status": "read"}
    }
    text = cio.export(state, "p")
    for replace, read, kept in ((False, 1, 0), (True, 1, 0)):
        _, summary, _ = cio.apply_import(
            m.empty_state(),
            cio.parse(text),
            person_id="p",
            shelf_id=None,
            import_notes=True,
            replace_reading=replace,
            now=NOW,
        )
        assert summary["rows"] == 2
        assert (summary["read"], summary["reading_kept"]) == (read, kept)


# ── Export ───────────────────────────────────────────────────────────────────


def test_export_header_and_cells() -> None:
    state = _library()
    state["games"]["persuasion"]["barcode"] = LEFT
    copy = m.build_copy({"game_id": "persuasion", "format": "audiobook"}, now=NOW)
    state["copies"][copy["id"]] = copy
    state["reading"]["p"] = {
        "persuasion": {
            **m.empty_reading(now=NOW),
            "status": "read",
            "rating": 4,
            "finished": "2024-01-02",
            "read_count": 1,
        }
    }
    text = cio.export(state, "p")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    assert tuple(reader.fieldnames or ()) == cio.LIBRARY_COLUMNS
    row = next(reader)
    assert row["barcode"] == LEFT and row["genres"] == "Romance"
    assert row["status"] == "read" and row["rating"] == "4"
    assert row["finished"] == "2024-01-02" and row["format"] == "audiobook"
    assert row["copy_id"] == copy["id"]
    no_person = next(csv.DictReader(io.StringIO(cio.export(state, None))))
    assert no_person["status"] == "" and no_person["read_count"] == ""
    assert cio.export_filename("2026-10-05") == "games-2026-10-05.csv"


def test_export_wishlist_of_the_person() -> None:
    state = _library()
    state["games"]["persuasion"]["wishlist"] = m.build_wishlist("p", buy=True, now=NOW)
    row = next(csv.DictReader(io.StringIO(cio.export(state, "p"))))
    assert (row["wishlist"], row["wishlist_buy"], row["format"]) == ("true", "true", "")
    other = next(csv.DictReader(io.StringIO(cio.export(state, "q"))))
    assert (other["wishlist"], other["wishlist_buy"]) == ("false", "false")
    everyone = next(csv.DictReader(io.StringIO(cio.export(state, None))))
    assert everyone["wishlist"] == "true"


def test_export_library_has_a_row_for_each_copy() -> None:
    state = _library()
    for stamp, fmt in (("t1", "hardcover"), ("t2", "ebook")):
        copy = m.build_copy({"game_id": "persuasion", "format": fmt}, now=stamp)
        state["copies"][copy["id"]] = copy
    rows = cio.rows_from_state(state, None)
    assert [r["copy"]["format"] for r in rows] == ["hardcover", "ebook"]
    assert [r["line"] for r in rows] == [1, 2]


# ── Round trips ──────────────────────────────────────────────────────────────

_WORD = st.text(
    alphabet=string.ascii_letters + string.digits + "éüß'\"", min_size=1, max_size=12
)
_TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs", "Cc"), blacklist_characters="\r﻿")
    | st.sampled_from(["\n", ",", '"']),
    max_size=40,
).map(str.strip)
_NAME = st.lists(_WORD, min_size=1, max_size=3).map(" ".join)
_DATE = st.dates(min_value=__import__("datetime").date(1900, 1, 1)).map(
    lambda d: d.isoformat()
)
_BARCODE = st.text(alphabet="0123456789ABC", min_size=8, max_size=13)
_TAG = st.text(alphabet=string.ascii_lowercase + "-", min_size=1, max_size=10).filter(
    lambda t: t not in ("read", "currently-reading", "to-read", "did-not-finish")
)


@st.composite
def _library_row(draw) -> dict:
    row = cio.empty_row(1)
    row["needs_details"] = False
    row["game_id"] = draw(st.uuids()).hex
    row["title"] = draw(_TEXT.filter(bool))
    for field in ("summary", "shared_notes"):
        row[field] = draw(_TEXT)
    row["release_date"] = draw(st.sampled_from(["", "1969", "2017-03-03"]))
    row["genres"] = draw(st.lists(_NAME, max_size=3, unique=True))
    row["tags"] = draw(st.lists(_TAG, max_size=3, unique=True))
    row["barcode"] = draw(st.none() | _BARCODE)
    row["franchise"] = draw(st.none() | _NAME)
    row["igdb_id"] = draw(st.none() | st.integers(min_value=1, max_value=999999))
    if draw(st.booleans()):
        row["copy"] = {
            "id": draw(st.uuids()).hex,
            "format": draw(st.sampled_from(m.FORMATS)),
            "condition": draw(st.sampled_from([None, *m.CONDITIONS])),
            "acquired": draw(st.none() | _DATE),
            "acquired_from": draw(_TEXT),
            "price": draw(st.none() | st.integers(0, 500) | st.just(9.5)),
            "value": draw(st.none() | st.integers(0, 500)),
            "signed": draw(st.booleans()),
            "first_edition": draw(st.booleans()),
            "note": draw(_TEXT),
        }
        row["owned"] = 1
        row["location"] = draw(st.just([]) | st.lists(_NAME, min_size=3, max_size=3))
    status = draw(st.sampled_from([None, *m.STATUSES]))
    row["status"] = status
    if status is not None:
        row["rating"] = draw(st.none() | st.integers(min_value=1, max_value=5))
        row["page"] = draw(st.none() | st.integers(min_value=0, max_value=900))
        row["started"] = draw(st.none() | _DATE)
        row["finished"] = draw(st.none() | _DATE)
        row["read_count"] = draw(st.none() | st.integers(min_value=0, max_value=9))
    row["notes"] = draw(_TEXT)
    row["wishlist"] = draw(st.booleans())
    row["wishlist_buy"] = row["wishlist"] and draw(st.booleans())
    return row


@settings(max_examples=150, deadline=None)
@given(st.lists(_library_row(), min_size=1, max_size=5))
def test_library_round_trip(rows: list[dict]) -> None:
    for index, row in enumerate(rows, start=1):
        row["line"] = index
    again = cio.parse(cio.write(rows))
    assert again == rows


@settings(max_examples=50, deadline=None)
@given(
    st.lists(
        _library_row(),
        min_size=1,
        max_size=5,
        unique_by=(
            lambda r: m.title_key(r["title"]),
            lambda r: r["barcode"] or r["game_id"],
        ),
    )
)
def test_state_export_import_export_is_stable(rows: list[dict]) -> None:
    """Import a library CSV into an empty library, export it, and compare.

    The titles differ, because 2 rows with the same title and author are 1 game.
    """
    for index, row in enumerate(rows, start=1):
        row["line"] = index
        row["location"] = []
    state, _, _ = cio.apply_import(
        m.empty_state(),
        rows,
        person_id="p",
        shelf_id=None,
        import_notes=True,
        replace_reading=True,
        now=NOW,
    )
    first = cio.export(state, "p")
    rebuilt, _, _ = cio.apply_import(
        m.empty_state(),
        cio.parse(first),
        person_id="p",
        shelf_id=None,
        import_notes=True,
        replace_reading=True,
        now=NOW,
    )
    assert cio.export(rebuilt, "p") == first
