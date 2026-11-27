"""Build the seed library for the browser tests and the frontend fixture.

Run from the repository root:

    python3 tests/e2e/seed/build_seed.py            # the 2 JSON files
    python3 tests/e2e/seed/build_seed.py --covers   # also draw the cover images

The script writes:

* ``tests/e2e/seed/home_keeper_games.json``: the store document that
  ``ci/e2e-up.sh`` copies to ``.storage/home_keeper_games`` before Home
  Assistant starts.
* ``custom_components/home_keeper_games/frontend/test/fixtures/state.json``:
  the ``get_state`` reply that an admin (Alex) gets for that store. It comes from
  ``projections.project_state``, the same code as the websocket command.
* With ``--covers``: ``tests/e2e/seed/covers/<file>.jpg``, which ``ci/e2e-up.sh``
  copies to ``.storage/home_keeper_games_covers/``. The images need Pillow and
  the DejaVu fonts, so they are made once and committed.

Every record is built by the pure ``models`` builders, so the seed has the shape
that the store writes. The ids are uuid4 values made from a hash of a stable
key, so a new run gives the same ids. The person ids are the ids that Home
Assistant gives to a person named Alex, Sam and Jo (``tests/e2e/global-setup.ts``
makes them).
"""

# The seed tables stay 1 record to a line, so they are easy to read and change.
# ruff: noqa: E501

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import types
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SEED_DIR = Path(__file__).resolve().parent
COMPONENT = ROOT / "custom_components" / "home_keeper_games"
STORE_OUT = SEED_DIR / "home_keeper_games.json"
STATE_OUT = COMPONENT / "frontend" / "test" / "fixtures" / "state.json"
COVERS_OUT = SEED_DIR / "covers"

ALEX, SAM, JO = "alex", "sam", "jo"
PERSONS = [
    {
        "person_id": ALEX,
        "name": "Alex",
        "entity_id": "person.alex",
        "user_id": "u-alex",
    },
    {"person_id": SAM, "name": "Sam", "entity_id": "person.sam", "user_id": "u-sam"},
    {"person_id": JO, "name": "Jo", "entity_id": "person.jo", "user_id": None},
]
NOW = "2026-10-04T18:00:00+00:00"


def _load_pure() -> tuple[types.ModuleType, types.ModuleType]:
    """Load ``models`` and ``projections`` with no Home Assistant (as tests/unit)."""
    pkg = "custom_components.home_keeper_games"
    for name, path in (
        ("custom_components", ROOT / "custom_components"),
        (pkg, COMPONENT),
    ):
        if name not in sys.modules:
            module = types.ModuleType(name)
            module.__path__ = [str(path)]
            sys.modules[name] = module
    loaded = []
    for mod in ("const", "models", "projections"):
        full = f"{pkg}.{mod}"
        if full not in sys.modules:
            spec = importlib.util.spec_from_file_location(full, COMPONENT / f"{mod}.py")
            assert spec and spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules[full] = module
            spec.loader.exec_module(module)
        loaded.append(sys.modules[full])
    return loaded[1], loaded[2]


def seed_id(kind: str, key: str) -> str:
    """A stable uuid4 hex for a seed record."""
    # The salt and the kinds keep the old names (book, bookcase), so the ids of the
    # committed seed files and cover files stay the same.
    digest = hashlib.sha256(f"home-keeper-library-seed:{kind}:{key}".encode()).digest()
    return uuid.UUID(bytes=digest[:16], version=4).hex


# The copy format of each old book format of the seed tables.
FORMAT_OF = {
    "hardcover": "physical",
    "paperback": "physical",
    "ebook": "digital",
    "audiobook": "digital",
    "other": "other",
}
# The platforms that the seed copies use, picked by a hash of the game key.
SEED_PLATFORMS = ("ps5", "switch", "ps4", "switch2", "pc")


def seed_platform(key: str) -> str:
    """A stable platform for a seed game."""
    return SEED_PLATFORMS[
        hashlib.sha256(key.encode()).digest()[0] % len(SEED_PLATFORMS)
    ]


def ean13(first12: str) -> str:
    """An EAN-13 barcode with a correct check digit for the first 12 digits."""
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first12))
    return first12 + str((10 - total % 10) % 10)


# fmt: off
# ── Places ───────────────────────────────────────────────────────────────────

ROOMS = [("living", "Living room", "living_room"), ("office", "Office", "office")]
UNITS = [
    ("case_a", "living", "Unit A", "By the window"),
    ("case_b", "living", "Unit B", "Next to the TV"),
    ("tall", "office", "Tall unit", ""),
]
SHELVES = [
    ("a1", "case_a", "Shelf 1"),
    ("a2", "case_a", "Shelf 2"),
    ("a3", "case_a", "Shelf 3"),
    ("a4", "case_a", "Shelf 4"),
    ("top", "case_b", "Top"),
    ("oversize", "case_b", "Oversize"),
    ("o1", "tall", "Shelf 1"),
    ("o2", "tall", "Shelf 2"),
    ("o3", "tall", "Shelf 3"),
]

# ── Games ────────────────────────────────────────────────────────────────────
# key: (title, developers, barcode first 12 digits, publisher, release year,
#       unused, genres, franchise, tags, cover). The game record takes the year as
#       its release date. The keys and barcodes come from the old book seed, so the
#       ids of the seed records stay the same.
# cover: None or "custom". Each cover is a file in tests/e2e/seed/covers.
NINTENDO = ["Nintendo"]
ADVENTURE = ["Adventure"]
RPG = ["Role-playing (RPG)"]
PLATFORM = ["Platform"]
GAMES: dict[str, tuple[Any, ...]] = {
    "left_hand": ("The Legend of Zelda: Tears of the Kingdom", NINTENDO, "978044147812", "Nintendo",
                  "2023", None, [*ADVENTURE, "Open world"], ("The Legend of Zelda", 20), ["Award winner"], "custom"),
    "earthsea": ("Super Mario Odyssey", NINTENDO, "978054777374", "Nintendo",
                 "2017", None, PLATFORM, ("Super Mario", 1), [], "custom"),
    "dispossessed": ("Metroid Dread", NINTENDO, "978006105488", "Nintendo",
                     "2021", None, [*ADVENTURE, "Shooter"], ("Metroid", 5), ["Award winner"], "custom"),
    "lathe": ("Pikmin 4", NINTENDO, "978141655696", "Nintendo",
              "2023", None, ["Strategy"], None, [], None),
    "atuan": ("Super Mario Bros. Wonder", NINTENDO, "978141650960", "Nintendo",
              "2023", None, PLATFORM, ("Super Mario", 2), [], "custom"),
    "farthest": ("Mario Kart 8 Deluxe", NINTENDO, "978141650963", "Nintendo",
                 "2017", None, ["Racing"], ("Mario Kart", 8), [], None),
    "tehanu": ("Animal Crossing: New Horizons", NINTENDO, "978068931595", "Nintendo",
               "2020", None, ["Simulator"], ("Animal Crossing", 5), ["Award winner"], None),
    "always": ("Splatoon 3", NINTENDO, "978159853705", "Nintendo",
               "2022", None, ["Shooter"], None, [], None),
    "word_world": ("Kirby and the Forgotten Land", NINTENDO, "978076532345", "Nintendo",
                   "2022", None, PLATFORM, ("Kirby", 5), [], None),
    "lavinia": ("Fire Emblem Engage", NINTENDO, "978015603368", "Nintendo",
                "2023", None, ["Strategy"], None, [], None),
    "piranesi": ("Hades", ["Supergiant Games"], "978163557563", "Supergiant Games",
                 "2020", None, [*RPG, "Indie"], None, ["Game club"], "custom"),
    "hail_mary": ("Outer Wilds", ["Mobius Digital"], "978059313520", "Annapurna Interactive",
                  "2019", None, ADVENTURE, None, [], "custom"),
    "fifth_season": ("Elden Ring", ["FromSoftware"], "978031622929", "Bandai Namco",
                     "2022", None, [*RPG, "Adventure"], ("Elden Ring", 1),
                     ["Award winner"], "custom"),
    "dune": ("Hollow Knight", ["Team Cherry"], "978044101359", "Team Cherry",
             "2017", None, [*ADVENTURE, "Platform"], ("Hollow Knight", 1), [], "custom"),
    "name_wind": ("The Witcher 3: Wild Hunt", ["CD Projekt Red"], "978075640474", "CD Projekt",
                  "2015", None, RPG, ("The Witcher", 3), [], None),
    "klara": ("Celeste", ["Maddy Makes Games"], "978059331817", "Maddy Makes Games",
              "2018", None, ADVENTURE, None, [], "custom"),
    "grain_rice": ("Overcooked! 2", ["Ghost Town Games"], "978039308928", "Team17",
                   "2018", None, ["Simulator", "Party"], ("Overcooked", 2), ["Couch co-op"], None),
    "salt_fat": ("PowerWash Simulator", ["FuturLab"], "978147675383", "Square Enix",
                 "2022", None, ["Simulator"], None, ["Couch co-op"], "custom"),
    "food_lab": ("Stardew Valley", ["ConcernedApe"], "978039308108", "ConcernedApe",
                 "2016", None, ["Simulator", "Role-playing (RPG)"], None, ["Couch co-op"], None),
    "atlas": ("A Short Hike", ["adamgryu"], "978014311820", "adamgryu",
              "2019", None, ["Adventure", "Indie"], None, [], None),
    "geb": ("The Witness", ["Thekla"], "978046502656", "Thekla",
            "2016", None, ["Puzzle"], None, [], None),
    "overstory": ("Disco Elysium", ["ZA/UM"], "978039363552", "ZA/UM",
                  "2019", None, RPG, None, ["Award winner"], None),
    "sweetgrass": ("Unpacking", ["Witch Beam"], "978157131356",
                   "Humble Games", "2021", None, ["Puzzle", "Indie"], None, [], None),
    "hobbit": ("Super Mario Galaxy", NINTENDO, "978054792822", "Nintendo",
               "2007", None, PLATFORM, ("Super Mario", 3), ["Family"], "custom"),
    "wild_things": ("Mario Party Superstars", NINTENDO, "978006025492",
                    "Nintendo", "2021", None, ["Party"], None, ["Family"], None),
    "chinese_1": ("Professor Layton and the Curious Village", ["Level-5"], "978162291135",
                  "Nintendo", "2007", None, ["Puzzle"], ("Professor Layton", 1),
                  ["Puzzle night"], None),
    "sicp": ("Baba Is You", ["Hempuli"], "978026251087", "Hempuli",
             "2019", None, ["Puzzle"], None, ["Puzzle night"], None),
    "pragmatic": ("Factorio", ["Wube Software"], "978020161622",
                  "Wube Software", "2020", None, ["Strategy"], None, [], None),
    "thinking": ("Return of the Obra Dinn", ["Lucas Pope"], "978037453355",
                 "3909", "2018", None, ["Puzzle"], None, [], None),
    "sapiens": ("Civilization VI", ["Firaxis Games"], "978006231609", "2K",
                "2016", None, ["Strategy"], ("Civilization", 6), [], None),
    "memory_empire": ("Mass Effect Legendary Edition", ["BioWare"], "978125018643", "Electronic Arts",
                      "2021", None, [*RPG, "Shooter"], ("Mass Effect", 1), ["Award winner"], None),
    "station_eleven": ("The Last of Us Part I", ["Naughty Dog"], "978080417244", "Sony",
                       "2022", None, ADVENTURE, ("The Last of Us", 1), [], None),
    "unreal": ("Xenoblade Chronicles 3", NINTENDO, "978161873079", "Nintendo",
               "2022", None, RPG, ("Xenoblade Chronicles", 3), [], None),
    "untitled": ("Untitled game case", [], "978098012345", "", "", None, [], None, [], None),
    "code_only": ("9780980123468", [], "978098012346", "", "", None, [], None, [], None),
    "steering": ("Kirby's Return to Dream Land Deluxe", NINTENDO, "978054461161", "Nintendo",
                 "2023", None, PLATFORM, ("Kirby", 4), [], None),
    "ministry": ("Baldur's Gate 3", ["Larian Studios"], "978031630013",
                 "Larian Studios", "2023", None, RPG, None, [], "custom"),
    "tomorrow": ("Sea of Stars", ["Sabotage Studio"], "978059332120",
                 "Sabotage Studio", "2023", None, RPG, None, [], None),
    # Games with no copy: a borrowed game and the wishlist.
    "spinning": ("Hi-Fi Rush", ["Tango Gameworks"], "978039958103", "Bethesda",
                 "2023", None, ["Action"], None, [], None),
    "sea_tranquility": ("Spiritfarer", ["Thunder Lotus"], "978059332144",
                        "Thunder Lotus", "2020", None, ["Simulator", "Indie"], None, [], None),
    "other_wind": ("The Legend of Zelda: Echoes of Wisdom", NINTENDO, "978054777376", "Nintendo",
                   "2024", None, ADVENTURE, ("The Legend of Zelda", 21), [], None),
    "obelisk": ("Hollow Knight: Silksong", ["Team Cherry"], "978031622926", "Team Cherry",
                "2025", None, [*ADVENTURE, "Platform"], ("Hollow Knight", 2), [], None),
    "fish_rice": ("Overcooked! All You Can Eat", ["Ghost Town Games"], "978039325438", "Team17",
                  "2020", None, ["Simulator", "Party"], ("Overcooked", 3), [], None),
    "chinese_2": ("Professor Layton and the Diabolical Box", ["Level-5"], "978162291140",
                  "Nintendo", "2007", None, ["Puzzle"], ("Professor Layton", 2),
                  [], None),
}
NEEDS_DETAILS = {"untitled", "code_only"}
SHARED_NOTES = {
    "left_hand": "Game club pick, **Oct 2026**. Sam has the map of Hyrule on the 3rd save.",
    "food_lab": "The *greenhouse* plan is in the case.\n\n- Sticky notes from Jo\n- Do not lend",
    "hobbit": "First game of the family. Keep the case out of the sun.",
}

# (game, shelf or None, format, condition, acquired, acquired_from, price, value,
#  signed, first_edition, note). The copy record takes the book format as physical or
#  digital (FORMAT_OF), a platform from the game key, and the signed mark as a steelbook.
#  The first copy of a game takes the barcode of the game.
COPIES = [
    ("left_hand", "a2", "paperback", "good", "2019-05-04", "Elliott Bay Game Co.", 7.99, 45,
     True, False, "Signed at a launch event in Portland."),
    ("left_hand", "o1", "hardcover", "fine", "2023-12-24", "Gift from Jo", None, None,
     False, False, ""),
    ("earthsea", "a2", "paperback", "fair", "2008-07-01", "", 6.5, None, False, False, ""),
    ("dispossessed", "a2", "paperback", "good", "2015-02-10", "Powell's Games", 9.99, None,
     False, False, ""),
    ("lathe", "a2", "paperback", "good", "2015-02-10", "Powell's Games", 8.99, None,
     False, False, ""),
    ("atuan", "a2", "paperback", "good", "2008-07-01", "", 6.5, None, False, False, ""),
    ("farthest", "a2", "paperback", "good", "2008-07-01", "", 6.5, None, False, False, ""),
    ("tehanu", "a2", "paperback", "good", "2009-01-15", "", 7.5, None, False, False, ""),
    ("always", "a3", "hardcover", "new", "2019-09-01", "Nintendo Store", 45, 45,
     False, False, ""),
    ("word_world", "a3", "paperback", "good", "2016-03-03", "", 8, None, False, False, ""),
    ("lavinia", "a3", "paperback", "good", "2010-05-05", "", 12, None, False, False, ""),
    ("piranesi", "a1", "hardcover", "fine", "2020-09-15", "Elliott Bay Game Co.", 27,
     None, False, True, ""),
    ("hail_mary", "a1", "hardcover", "fine", "2021-05-04", "Amazon", 28.99, None,
     False, False, ""),
    ("fifth_season", "a1", "paperback", "good", "2018-11-02", "", 15.99, None,
     False, False, ""),
    ("dune", "a1", "paperback", "fair", "2004-06-01", "Garage sale", 1,
     None, False, False, "The case is cracked."),
    ("name_wind", "a1", "paperback", "good", "2012-08-08", "", 9.99, None, False, False, ""),
    ("klara", "a1", "hardcover", "fine", "2021-03-02", "Elliott Bay Game Co.", 28, None,
     False, False, ""),
    ("grain_rice", "oversize", "hardcover", "good", "2014-01-20", "", 35, None,
     False, False, ""),
    ("salt_fat", "oversize", "hardcover", "fine", "2018-04-01", "", 35, None, False, False, ""),
    ("food_lab", "oversize", "hardcover", "good", "2016-12-25", "Gift from Sam", 49.95, 30,
     False, False, ""),
    ("atlas", "oversize", "hardcover", "fine", "2011-06-06", "", 25, None, False, False, ""),
    ("geb", "o1", "paperback", "fair", "2001-09-01", "University Game Store", 22, None,
     False, False, ""),
    ("overstory", "top", "paperback", "good", "2019-10-10", "", 18, None, False, False, ""),
    ("sweetgrass", "top", "paperback", "good", "2021-02-14", "", 20, None, False, False, ""),
    ("hobbit", "top", "hardcover", "good", "1985-12-25", "Inherited", None, 120,
     False, True, ""),
    ("wild_things", "top", "hardcover", "fair", "2016-04-01", "", 17.99, None,
     False, False, ""),
    ("chinese_1", "o2", "paperback", "good", "2024-01-08", "Game shop", 59.99, None,
     False, False, ""),
    ("sicp", "o2", "hardcover", "good", "2003-09-01", "University Game Store", 75, 60,
     False, False, ""),
    ("pragmatic", "o2", "paperback", "good", "2005-02-02", "", 39.99, None, False, False, ""),
    ("thinking", "o3", "paperback", "good", "2013-07-07", "", 17, None, False, False, ""),
    ("sapiens", "o3", "paperback", "good", "2017-08-08", "", 18.99, None, False, False, ""),
    ("memory_empire", "a4", "paperback", "fine", "2020-04-04", "", 17.99, None,
     False, False, ""),
    ("station_eleven", "a4", "paperback", "good", "2015-05-05", "", 15.95, None,
     False, False, ""),
    ("unreal", "a4", "hardcover", "fine", "2013-01-01", "", 30, None, False, False, ""),
    ("untitled", "a3", "paperback", None, None, "", None, None, False, False, ""),
    ("code_only", None, "paperback", None, None, "", None, None, False, False, ""),
    ("steering", None, "paperback", "good", "2024-05-05", "", 16, None, False, False, ""),
    ("ministry", "a4", "hardcover", "fine", "2020-10-06", "", 28, None, False, False, ""),
    ("tomorrow", "a4", "hardcover", "fine", "2022-07-05", "", 28, None, False, False, ""),
]

# (game, person, play status, rating, play time in minutes, started, completed,
#  completion count, review, updated_at). Each row is on the platform of the first
#  copy of the game (``other`` with no copy), except the rows in PROGRESS_PLATFORM.
PROGRESS = [
    ("left_hand", ALEX, "completed", 4, None, "2025-02-01", "2025-03-02", 2,
     "Reread before the club.", "2026-09-20T10:00:00+00:00"),
    ("left_hand", SAM, "playing", None, 112, "2026-09-01", None, 0, "",
     "2026-10-03T19:30:00+00:00"),
    ("earthsea", ALEX, "completed", 5, None, None, "2026-02-11", 1, "", "2026-02-11T21:00:00+00:00"),
    ("earthsea", JO, "completed", 4, None, None, "2026-08-30", 1, "", "2026-08-30T19:00:00+00:00"),
    ("dispossessed", ALEX, "completed", 5, None, None, "2026-04-20", 1, "",
     "2026-04-20T22:00:00+00:00"),
    ("lathe", ALEX, "backlog", None, None, None, None, 0, "", "2026-05-01T10:00:00+00:00"),
    ("atuan", JO, "playing", None, 40, "2026-09-28", None, 0, "", "2026-10-02T18:00:00+00:00"),
    ("atuan", ALEX, "backlog", None, None, None, None, 0, "", "2026-08-31T10:00:00+00:00"),
    ("word_world", SAM, "completed", 3, None, None, "2026-06-01", 1, "", "2026-06-01T20:00:00+00:00"),
    ("piranesi", ALEX, "completed", 5, None, "2026-09-20", "2026-10-03", 1, "",
     "2026-10-03T21:45:00+00:00"),
    ("piranesi", SAM, "backlog", None, None, None, None, 0, "", "2026-10-04T08:00:00+00:00"),
    ("hail_mary", ALEX, "playing", None, 210, "2026-09-25", None, 0, "",
     "2026-10-04T07:10:00+00:00"),
    ("hail_mary", SAM, "backlog", None, None, None, None, 0, "", "2026-09-26T10:00:00+00:00"),
    ("fifth_season", ALEX, "completed", 5, None, None, "2026-05-14", 1, "",
     "2026-05-14T22:00:00+00:00"),
    ("dune", ALEX, "completed", 4, None, None, "2024-12-01", 1, "", "2024-12-01T22:00:00+00:00"),
    ("dune", JO, "abandoned", None, 140, None, None, 0, "", "2026-07-12T10:00:00+00:00"),
    ("klara", SAM, "completed", 4, None, None, "2026-09-28", 1, "", "2026-09-28T21:00:00+00:00"),
    ("grain_rice", ALEX, "playing", None, 80, "2026-08-01", None, 0, "",
     "2026-09-12T18:00:00+00:00"),
    ("geb", ALEX, "abandoned", 3, 320, None, None, 0, "Try again one day.",
     "2025-11-11T10:00:00+00:00"),
    ("overstory", SAM, "completed", 5, None, None, "2026-03-03", 1, "", "2026-03-03T21:00:00+00:00"),
    ("hobbit", JO, "completed", 5, None, None, "2026-07-07", 1, "", "2026-07-07T19:00:00+00:00"),
    ("hobbit", ALEX, "completed", None, None, None, "2019-01-01", 1, "", "2019-01-01T10:00:00+00:00"),
    ("wild_things", JO, "completed", None, None, None, "2026-01-02", 12, "",
     "2026-01-02T19:00:00+00:00"),
    ("chinese_1", ALEX, "playing", None, 150, "2026-01-08", None, 0, "",
     "2026-09-30T18:00:00+00:00"),
    ("pragmatic", ALEX, "completed", 4, None, None, "2026-07-20", 1, "", "2026-07-20T22:00:00+00:00"),
    ("sapiens", SAM, "abandoned", None, 120, None, None, 0, "", "2026-04-04T10:00:00+00:00"),
    ("memory_empire", ALEX, "completed", 4, None, None, "2026-08-08", 1, "",
     "2026-08-08T22:00:00+00:00"),
    ("ministry", ALEX, "playing", None, 300, "2026-09-01", None, 0, "",
     "2026-09-29T21:00:00+00:00"),
    ("tomorrow", SAM, "playing", None, 20, "2026-10-01", None, 0, "",
     "2026-10-01T22:00:00+00:00"),
    ("spinning", ALEX, "playing", None, 64, "2026-09-21", None, 0, "",
     "2026-10-01T20:00:00+00:00"),
    ("sea_tranquility", SAM, "backlog", None, None, None, None, 0, "",
     "2026-09-25T10:00:00+00:00"),
    ("left_hand", ALEX, "playing", None, 95, "2026-10-01", None, 0, "",
     "2026-10-04T09:00:00+00:00"),
]

# (game, person, index in PROGRESS of that game and person) to platform, for a
# person with rows on more than 1 platform.
PROGRESS_PLATFORM = {("left_hand", ALEX, 1): "switch"}

# (key, direction, game, copy index of the game or None, party, person, format,
#  started, due, returned, note)
LOANS = [
    ("priya_piranesi", "out", "piranesi", 0, "Priya", None, None, "2026-08-12",
     "2026-09-13", None, ""),
    ("priya_left", "out", "left_hand", 1, "Priya", None, None, "2026-09-12", "2026-10-13",
     None, ""),
    ("club_ministry", "out", "ministry", 0, "Game club", None, None, "2026-10-01", None,
     None, "For the November meeting."),
    ("friend_dispossessed", "out", "dispossessed", 0, "Sam's friend Lee", None, None,
     "2026-05-01", "2026-06-01", "2026-05-28", ""),
    ("spl_spinning", "in", "spinning", None, "Seattle Public Library", ALEX, "paperback",
     "2026-09-20", "2026-10-11", None, ""),
    ("spl_sea", "in", "sea_tranquility", None, "Seattle Public Library", SAM, "ebook",
     "2026-09-25", "2026-10-25", None, ""),
]

# (game, person, buy, added_at)
WISHLIST = [
    ("other_wind", ALEX, True, "2026-09-02T10:00:00+00:00"),
    ("obelisk", ALEX, False, "2026-08-15T10:00:00+00:00"),
    ("fish_rice", SAM, True, "2026-09-18T10:00:00+00:00"),
    ("chinese_2", ALEX, False, "2026-06-01T10:00:00+00:00"),
]

# (key, game, person, platform, source, date, start time or None, minutes). A psn
# session has the start and end time stamps; a manual one has only the date and the
# minutes. The seed writes the sessions as they are, with no change to the progress.
SESSIONS = [
    ("hail_mary_1", "hail_mary", ALEX, "pc", "psn", "2026-10-03", "18:00", 95),
    ("hail_mary_2", "hail_mary", ALEX, "pc", "psn", "2026-10-01", "21:10", 70),
    ("hail_mary_3", "hail_mary", ALEX, "pc", "manual", "2026-09-27", None, 45),
    ("ministry_1", "ministry", ALEX, "pc", "psn", "2026-09-29", "20:30", 120),
    ("left_hand_1", "left_hand", ALEX, "switch", "manual", "2026-10-04", None, 95),
]

PEOPLE = {
    ALEX: {"share_progress": True, "wishlist_todo": "todo.alex_games", "yearly_goal": 24},
    SAM: {"share_progress": True, "wishlist_todo": None, "yearly_goal": 12},
    JO: {"share_progress": True, "wishlist_todo": None, "yearly_goal": None},
}

# fmt: on


def cover_file(key: str) -> str:
    """The stored cover file name of a game: ``<game_id>-<token>.jpg``."""
    token = hashlib.sha256(f"cover:{key}".encode()).hexdigest()[:8]
    return f"{seed_id('book', key)}-{token}.jpg"


def build_store(models: types.ModuleType) -> dict[str, Any]:
    """The store document."""
    state = models.empty_state()
    for order, (key, name, area) in enumerate(ROOMS, 1):
        room = models.build_room({"name": name, "area_id": area}, order=order)
        room["id"] = seed_id("room", key)
        state["rooms"][room["id"]] = room
    for order, (key, room, name, note) in enumerate(UNITS, 1):
        case = models.build_unit(
            {"room_id": seed_id("room", room), "name": name, "note": note}, order=order
        )
        case["id"] = seed_id("bookcase", key)
        state["units"][case["id"]] = case
    orders: dict[str, int] = {}
    for key, case, name in SHELVES:
        orders[case] = orders.get(case, 0) + 1
        shelf = models.build_shelf(
            {"unit_id": seed_id("bookcase", case), "name": name}, order=orders[case]
        )
        shelf["id"] = seed_id("shelf", key)
        state["shelves"][shelf["id"]] = shelf
    codes: dict[str, str] = {}
    for n, (key, row) in enumerate(GAMES.items()):
        (
            title,
            authors,
            code,
            _publisher,
            published,
            _pages,
            subjects,
            series,
            tags,
            cov,
        ) = row
        created = f"2026-0{1 + n // 12}-{1 + n % 12 * 2:02d}T10:00:00+00:00"
        data: dict[str, Any] = {
            "title": title,
            "release_date": published,
            "genres": subjects,
            "franchise": series[0] if series else None,
            "summary": f"A {subjects[0].lower()} title by {authors[0]}."
            if subjects and authors
            else "",
            "tags": tags,
            "shared_notes": SHARED_NOTES.get(key, ""),
        }
        game = models.build_game(data, now=created)
        game["id"] = seed_id("book", key)
        game["updated_at"] = created
        game["needs_details"] = key in NEEDS_DETAILS
        if cov:
            game["cover"] = {"kind": "custom", "file": cover_file(key)}
        state["games"][game["id"]] = game
        codes[key] = ean13(code)
    copy_ids: dict[str, list[str]] = {}
    for row in COPIES:
        game, shelf, fmt, cond, acquired, source, price, value, signed, first, note = (
            row
        )
        copy = models.build_copy(
            {
                "game_id": seed_id("book", game),
                "shelf_id": seed_id("shelf", shelf) if shelf else None,
                "format": FORMAT_OF[fmt],
                "platform": seed_platform(game),
                "steelbook": signed,
                "edition": "First print" if first else "",
                "region": "PAL",
                "barcode": None if copy_ids.get(game) else codes[game],
                "condition": cond,
                "acquired": acquired,
                "acquired_from": source,
                "price": price,
                "value": value,
                "note": note,
            },
            now=state["games"][seed_id("book", game)]["created_at"],
        )
        index = len(copy_ids.setdefault(game, []))
        copy["id"] = seed_id("copy", f"{game}:{index}")
        copy_ids[game].append(copy["id"])
        state["copies"][copy["id"]] = copy
    seen: dict[tuple[str, str], int] = {}
    for (
        game,
        person,
        status,
        rating,
        minutes,
        started,
        completed,
        count,
        review,
        at,
    ) in PROGRESS:
        index = seen.get((game, person), 0)
        seen[(game, person)] = index + 1
        first = copy_ids.get(game, [None])[0]
        platform = PROGRESS_PLATFORM.get((game, person, index)) or (
            state["copies"][first]["platform"] if first else "other"
        )
        row = models.empty_progress(now=at)
        row.update(
            {
                "play_status": status,
                "rating": rating,
                "playtime_minutes": minutes,
                "started_at": started,
                "completed_at": completed,
                "completion_count": count,
                "review": review,
            }
        )
        games = state["progress"].setdefault(person, {})
        games.setdefault(seed_id("book", game), {})[platform] = row
    for (
        key,
        direction,
        game,
        index,
        party,
        person,
        fmt,
        started,
        due,
        back,
        note,
    ) in LOANS:
        loan = models.build_loan(
            {
                "direction": direction,
                "game_id": seed_id("book", game),
                "copy_id": copy_ids[game][index] if index is not None else None,
                "party": party,
                "person_id": person,
                "format": FORMAT_OF[fmt] if fmt else None,
                "started": started,
                "due": due,
                "note": note,
            },
            today=started,
        )
        loan["id"] = seed_id("loan", key)
        loan["returned"] = back
        # The loan sync at setup finds no Home Keeper task with this id, so it
        # adds a new task (loan_tasks.plan_reconcile) and stores its id.
        if due and not back:
            loan["hk_task_id"] = seed_id("task", key)
        state["loans"][loan["id"]] = loan
    for game, person, buy, at in WISHLIST:
        state["games"][seed_id("book", game)]["wishlist"] = models.build_wishlist(
            person, buy=buy, now=at
        )
    for key, game, person, platform, source, day, start, minutes in SESSIONS:
        game_id = seed_id("book", game)
        started = f"{day}T{start}:00+00:00" if start else None
        ended = None
        if started:
            begin = datetime.fromisoformat(started)
            ended = (begin + timedelta(minutes=minutes)).isoformat()
        state["sessions"][seed_id("session", key)] = {
            "id": seed_id("session", key),
            "person_id": person,
            "game_id": game_id,
            "platform": platform,
            "source": source,
            "external_id": "PPSA00001_00" if source == "psn" else None,
            "started_at": started,
            "ended_at": ended,
            "date": day,
            "minutes": minutes,
            "created_at": ended or f"{day}T22:00:00+00:00",
        }
    state["people"] = {pid: dict(settings) for pid, settings in PEOPLE.items()}
    return state


def project(projections: types.ModuleType, state: dict[str, Any]) -> dict[str, Any]:
    """The ``get_state`` reply of Alex, an admin."""
    return projections.project_state(
        state,
        persons=PERSONS,
        viewer=ALEX,
        is_admin=True,
        viewer_name="Alex",
        currency="EUR",
        tab=True,
        revision=1,
    )


def draw_covers(state: dict[str, Any]) -> None:
    """Draw a simple cover image for each game with a cover file."""
    from PIL import Image, ImageDraw, ImageFont

    # DejaVu on Linux, else the macOS fonts.
    dejavu = Path("/usr/share/fonts/truetype/dejavu")
    mac = Path("/System/Library/Fonts/Supplemental")
    serif, sans = (
        (dejavu / "DejaVuSerif-Bold.ttf", dejavu / "DejaVuSans.ttf")
        if dejavu.exists()
        else (mac / "Georgia Bold.ttf", mac / "Arial.ttf")
    )
    key_of = {seed_id("book", key): key for key in GAMES}
    palette = [
        ("#16324f", "#f4d35e"),
        ("#7a1f2b", "#f6e7d8"),
        ("#204e4a", "#e9d985"),
        ("#3d2c52", "#f2c6de"),
        ("#8c3b0b", "#fff1d6"),
        ("#0f4c5c", "#ffe8a3"),
        ("#2f2f2f", "#e4572e"),
        ("#5b7553", "#f5f1e3"),
        ("#123c69", "#edc7b7"),
        ("#6a0572", "#f9e2ae"),
        ("#264653", "#e9c46a"),
        ("#9b2226", "#fefae0"),
    ]
    COVERS_OUT.mkdir(parents=True, exist_ok=True)
    for old in COVERS_OUT.glob("*.jpg"):
        old.unlink()
    for n, game in enumerate(sorted(state["games"].values(), key=lambda b: b["id"])):
        key = key_of[game["id"]]
        file = game["cover"]["file"]
        if not file:
            continue
        bg, ink = palette[n % len(palette)]
        img = Image.new("RGB", (400, 600), bg)
        draw = ImageDraw.Draw(img)
        draw.rectangle((0, 0, 18, 600), fill=ink)
        draw.rectangle((40, 330, 360, 334), fill=ink)
        title_font = ImageFont.truetype(str(serif), 40)
        words, lines, line = game["title"].split(), [], ""
        for word in words:
            test = f"{line} {word}".strip()
            if draw.textlength(test, font=title_font) > 310 and line:
                lines.append(line)
                line = word
            else:
                line = test
        lines.append(line)
        y = 300 - 50 * len(lines)
        for text in lines:
            draw.text((40, y), text, font=title_font, fill=ink)
            y += 50
        author_font = ImageFont.truetype(str(sans), 22)
        draw.text(
            (40, 360), ", ".join(GAMES[key][1]).upper(), font=author_font, fill=ink
        )
        img.save(COVERS_OUT / file, "JPEG", quality=82)


def main() -> None:
    models, projections = _load_pure()
    state = build_store(models)
    document = {
        "version": 1,
        "minor_version": 1,
        "key": "home_keeper_games",
        "data": state,
    }
    STORE_OUT.write_text(json.dumps(document, indent=1, ensure_ascii=False) + "\n")
    STATE_OUT.write_text(
        json.dumps(project(projections, state), indent=1, ensure_ascii=False) + "\n"
    )
    if "--covers" in sys.argv:
        draw_covers(state)
    print(
        f"{len(state['games'])} games, {len(state['copies'])} copies, "
        f"{len(state['loans'])} loans"
    )


if __name__ == "__main__":
    main()
