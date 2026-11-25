"""The IGDB catalog rules: queries, the platform map and the game fields.

``igdb.py`` sends the queries that this module writes, and gives back the raw
records. This module turns a raw record into the game fields of the library and
into a search candidate. It never trusts the shape of a record: a missing or bad
value becomes an empty field.

The module is pure. It imports no Home Assistant code, so the unit tier and the
mutation gate check it.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from .models import MAX_IGDB_ID, MAX_LIST, MAX_LONG, MAX_SHORT, MAX_TITLE, title_key

#: The IGDB platform id of each platform of the library. ``other`` has none.
IGDB_PLATFORMS: dict[str, int] = {
    "ps5": 167,
    "ps4": 48,
    "ps3": 9,
    "switch2": 508,
    "switch": 130,
    "xbox_series": 169,
    "xbox_one": 49,
    "pc": 6,
}
_PLATFORM_BY_IGDB = {igdb: platform for platform, igdb in IGDB_PLATFORMS.items()}

#: The fields of a game record that the queries ask for.
GAME_FIELDS = (
    "name,summary,first_release_date,genres.name,franchises.name,"
    "collections.name,cover.image_id,platforms"
)
#: The IGDB image size of a cover: 264 x 374 px.
COVER_SIZE = "t_cover_big"
_MAX_QUERY = 200
_IMAGE_ID_RE = re.compile(r"[a-z0-9]{1,64}")
# A character that ends an Apicalypse string or starts an escape.
_UNSAFE_RE = re.compile(r'["\\\x00-\x1f\x7f]')


def clean_query(text: Any) -> str:
    """The search text with no quote, backslash or control character."""
    if not isinstance(text, str):
        return ""
    return " ".join(_UNSAFE_RE.sub(" ", text).split())[:_MAX_QUERY]


def search_body(text: str, platform: str | None, limit: int) -> str:
    """The Apicalypse body of a title search.

    Only main games: an edition or a port of a game has a ``version_parent``.
    """
    where = "version_parent = null"
    if (igdb := IGDB_PLATFORMS.get(platform or "")) is not None:
        where += f" & platforms = ({igdb})"
    return (
        f'search "{clean_query(text)}"; fields {GAME_FIELDS}; '
        f"where {where}; limit {limit};"
    )


def game_body(igdb_id: int) -> str:
    """The Apicalypse body that reads 1 game by its id."""
    return f"fields {GAME_FIELDS}; where id = {int(igdb_id)}; limit 1;"


def _id(raw: dict[str, Any]) -> int | None:
    value = raw.get("id")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if 1 <= value <= MAX_IGDB_ID else None


def _text(value: Any, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _names(value: Any) -> list[str]:
    """The ``name`` of each record in a list, with no empty name or repeat."""
    out: list[str] = []
    for item in value if isinstance(value, list) else []:
        name = _text(item.get("name") if isinstance(item, dict) else None, MAX_SHORT)
        if name and name not in out:
            out.append(name)
    return out[:MAX_LIST]


def release_date(value: Any) -> str:
    """The ``YYYY-MM-DD`` date of a Unix time in seconds, or ``""``."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return ""
    try:
        return datetime.fromtimestamp(value, UTC).date().isoformat()
    except (OverflowError, OSError, ValueError):
        return ""


def image_id(raw: dict[str, Any]) -> str | None:
    """The image id of the cover of a record, or None if it has none."""
    cover = raw.get("cover")
    value = cover.get("image_id") if isinstance(cover, dict) else None
    if isinstance(value, str) and _IMAGE_ID_RE.fullmatch(value):
        return value
    return None


def cover_url(images_url: str, image: str) -> str:
    """The URL of the cover image with the id *image*."""
    return f"{images_url}/{COVER_SIZE}/{image}.jpg"


def platforms(raw: dict[str, Any]) -> list[str]:
    """The library platforms of a record, in the order of the library list."""
    ids = raw.get("platforms")
    found = {
        _PLATFORM_BY_IGDB[i]
        for i in (ids if isinstance(ids, list) else [])
        if isinstance(i, int) and i in _PLATFORM_BY_IGDB
    }
    return [p for p in IGDB_PLATFORMS if p in found]


def game_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """The game fields of the library from an IGDB record.

    The franchise is the first franchise, else the first collection (a series).
    An empty value is left out, so it does not replace a value of the caller.
    """
    fields: dict[str, Any] = {
        "igdb_id": _id(raw),
        "title": _text(raw.get("name"), MAX_TITLE),
    }
    if summary := _text(raw.get("summary"), MAX_LONG):
        fields["summary"] = summary
    if genres := _names(raw.get("genres")):
        fields["genres"] = genres
    if date := release_date(raw.get("first_release_date")):
        fields["release_date"] = date
    franchise = _names(raw.get("franchises")) or _names(raw.get("collections"))
    if franchise:
        fields["franchise"] = franchise[0]
    return fields


def replacement_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """The fields that a stored game gets when an admin gives it another IGDB game.

    A field that the new record does not have becomes empty, because its old value
    came from the other game. The game no longer needs details.
    """
    return {
        "summary": "",
        "genres": [],
        "release_date": "",
        "franchise": None,
        **game_fields(raw),
        "needs_details": False,
    }


def candidate(
    raw: dict[str, Any], images_url: str, in_library: str | None
) -> dict[str, Any]:
    """1 search result in the reply of ``search_catalog``."""
    date = release_date(raw.get("first_release_date"))
    image = image_id(raw)
    return {
        "igdb_id": _id(raw),
        "title": _text(raw.get("name"), MAX_TITLE),
        "release_year": int(date[:4]) if date else None,
        "platforms": platforms(raw),
        "cover_url": cover_url(images_url, image) if image else None,
        "in_library": in_library,
    }


def records(value: Any) -> list[dict[str, Any]]:
    """The game records of an IGDB reply that have a valid id and a name."""
    if not isinstance(value, list):
        return []
    return [
        raw
        for raw in value
        if isinstance(raw, dict) and _id(raw) is not None and _text(raw.get("name"), 1)
    ]


def best_match(
    found: list[dict[str, Any]], title: str, platform: str | None
) -> dict[str, Any] | None:
    """The first record with the same title key, and with the platform if given.

    ``other`` or no platform matches every record. With no exact match there is
    no match, so ``add_game`` adds only the title and marks the game.
    """
    key = title_key(title)
    if not key:
        return None
    for raw in found:
        if title_key(raw.get("name")) != key:
            continue
        if platform in IGDB_PLATFORMS and platform not in platforms(raw):
            continue
        return raw
    return None
