"""Unit tests for the IGDB catalog rules: queries, platforms and game fields."""

from __future__ import annotations

import ex.catalog as c
import ex.models as m
import pytest

IMAGES = "https://images.example/igdb"

ZELDA = {
    "id": 7346,
    "name": "The Legend of Zelda: Breath of the Wild",
    "summary": "  Step into a world of discovery.  ",
    "first_release_date": 1488499200,
    "genres": [
        {"id": 31, "name": "Adventure"},
        {"id": 12, "name": "Role-playing (RPG)"},
    ],
    "franchises": [{"id": 596, "name": "The Legend of Zelda"}],
    "collections": [{"id": 106, "name": "Zelda"}],
    "cover": {"id": 1, "image_id": "co3p2d"},
    "platforms": [130, 41, 6],
}


def test_the_query_text_cannot_break_the_apicalypse_string() -> None:
    assert c.clean_query('Zelda"; fields *; \\ \x00x') == "Zelda ; fields *; x"
    assert c.clean_query("  a   b  ") == "a b"
    assert c.clean_query(None) == ""
    assert len(c.clean_query("x" * 500)) == 200


def test_a_search_body_asks_only_main_games() -> None:
    assert c.search_body("Zelda", None, 10) == (
        f'search "Zelda"; fields {c.GAME_FIELDS}; '
        "where version_parent = null; limit 10;"
    )


def test_a_search_body_filters_the_platform() -> None:
    body = c.search_body("Zelda", "switch", 5)
    assert "where version_parent = null & platforms = (130); limit 5;" in body
    # ``other`` has no IGDB id, so it filters nothing.
    assert "platforms" not in c.search_body("Zelda", "other", 5).split("where")[1]


def test_a_game_body_reads_1_id() -> None:
    assert c.game_body(7346) == f"fields {c.GAME_FIELDS}; where id = 7346; limit 1;"


def test_each_library_platform_but_other_has_an_igdb_id() -> None:
    assert set(c.IGDB_PLATFORMS) == set(m.PLATFORMS) - {"other"}
    assert len(set(c.IGDB_PLATFORMS.values())) == len(c.IGDB_PLATFORMS)


def test_the_game_fields_of_a_full_record() -> None:
    assert c.game_fields(ZELDA) == {
        "igdb_id": 7346,
        "title": "The Legend of Zelda: Breath of the Wild",
        "summary": "Step into a world of discovery.",
        "genres": ["Adventure", "Role-playing (RPG)"],
        "release_date": "2017-03-03",
        "franchise": "The Legend of Zelda",
    }


def test_the_game_fields_leave_out_empty_values() -> None:
    assert c.game_fields({"id": 1, "name": "Tetris", "summary": " ", "genres": []}) == {
        "igdb_id": 1,
        "title": "Tetris",
    }


def test_a_collection_is_the_franchise_when_there_is_no_franchise() -> None:
    raw = {"id": 1, "name": "X", "franchises": [], "collections": [{"name": "Series"}]}
    assert c.game_fields(raw)["franchise"] == "Series"


def test_bad_values_become_empty_fields() -> None:
    raw = {
        "id": 1,
        "name": "X",
        "summary": 5,
        "genres": ["Adventure", {"name": ""}, {"name": "RPG"}, {"name": "RPG"}],
        "first_release_date": "2017",
        "franchises": "Zelda",
    }
    assert c.game_fields(raw) == {"igdb_id": 1, "title": "X", "genres": ["RPG"]}


def test_long_values_are_cut() -> None:
    raw = {"id": 1, "name": "T" * 600, "genres": [{"name": f"g{i}"} for i in range(60)]}
    fields = c.game_fields(raw)
    assert len(fields["title"]) == m.MAX_TITLE
    assert len(fields["genres"]) == m.MAX_LIST


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, "1970-01-01"),
        (1488499200, "2017-03-03"),
        (1488499200.5, "2017-03-03"),
        (True, ""),
        ("1488499200", ""),
        (None, ""),
        (10**20, ""),
    ],
)
def test_release_date(value, expected) -> None:
    assert c.release_date(value) == expected


@pytest.mark.parametrize(
    ("cover", "expected"),
    [
        ({"image_id": "co3p2d"}, "co3p2d"),
        ({"image_id": "../etc"}, None),
        ({"image_id": "CO3P2D"}, None),
        ({"image_id": ""}, None),
        ({"image_id": "a" * 65}, None),
        ({}, None),
        ("co3p2d", None),
        (None, None),
    ],
)
def test_image_id_takes_only_a_safe_id(cover, expected) -> None:
    assert c.image_id({"cover": cover}) == expected


def test_cover_url() -> None:
    assert c.cover_url(IMAGES, "co3p2d") == f"{IMAGES}/t_cover_big/co3p2d.jpg"


def test_platforms_keep_the_library_order_and_drop_unknown_ids() -> None:
    assert c.platforms({"platforms": [6, 130, 41, 130, "48", True]}) == ["switch", "pc"]
    assert c.platforms({"platforms": None}) == []
    assert c.platforms({}) == []


def test_a_candidate() -> None:
    assert c.candidate(ZELDA, IMAGES, "g1") == {
        "igdb_id": 7346,
        "title": "The Legend of Zelda: Breath of the Wild",
        "release_year": 2017,
        "platforms": ["switch", "pc"],
        "cover_url": f"{IMAGES}/t_cover_big/co3p2d.jpg",
        "in_library": "g1",
    }


def test_a_candidate_with_no_date_or_cover() -> None:
    found = c.candidate({"id": 2, "name": "X"}, IMAGES, None)
    assert found["release_year"] is None
    assert found["cover_url"] is None
    assert found["in_library"] is None


@pytest.mark.parametrize(
    "raw",
    [
        {"name": "No id"},
        {"id": 0, "name": "Zero"},
        {"id": True, "name": "Bool"},
        {"id": "5", "name": "Text"},
        {"id": m.MAX_IGDB_ID + 1, "name": "Too big"},
        {"id": 5},
        {"id": 5, "name": "  "},
        "not a dict",
    ],
)
def test_records_drop_a_bad_record(raw) -> None:
    assert c.records([raw]) == []


def test_records_keep_good_records_in_order() -> None:
    good = [{"id": 2, "name": "B"}, {"id": 1, "name": "A"}]
    assert c.records(good) == good
    assert c.records({"id": 1}) == []
    assert c.records(None) == []


def test_best_match_needs_the_same_title_key() -> None:
    found = [{"id": 1, "name": "Zelda II"}, {"id": 2, "name": "ZELDA!"}]
    assert c.best_match(found, "zelda", None) == found[1]
    assert c.best_match(found, "Zelda 3", None) is None
    assert c.best_match(found, "  ", None) is None


def test_best_match_needs_the_platform() -> None:
    pc = {"id": 1, "name": "Hades", "platforms": [6]}
    switch = {"id": 2, "name": "Hades", "platforms": [130]}
    assert c.best_match([pc, switch], "Hades", "switch") == switch
    assert c.best_match([pc, switch], "Hades", "ps5") is None
    assert c.best_match([pc, switch], "Hades", "other") == pc
    assert c.best_match([pc, switch], "Hades", None) == pc
