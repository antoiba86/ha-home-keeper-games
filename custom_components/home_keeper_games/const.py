"""Constants for Home Keeper Games.

Home Keeper Games is a companion of Home Keeper. It stores the games of a
household: the rooms, units and shelves where the copies are, the play
progress of each person, the loans and the wishlist. The admin UI is a tab in the
Home Keeper panel. The usage surfaces are the card, the per-person entities and
the services.

This module is pure. It imports no Home Assistant code, so the unit tier can load
it.
"""

from __future__ import annotations

DOMAIN = "home_keeper_games"
NAME = "Home Keeper Games"
ICON = "mdi:bookshelf"
DOCS_URL = "https://github.com/antoiba86/ha-home-keeper-games"
USER_AGENT = "HomeKeeperGames/{version} (+" + DOCS_URL + ")"

# The Home Keeper integration that this integration requires.
HOME_KEEPER_DOMAIN = "home_keeper"
HOME_KEEPER_EVENT_TASK_COMPLETED = "home_keeper_task_completed"
HOME_KEEPER_EVENT_TASK_DELETED = "home_keeper_task_deleted"
HOME_KEEPER_EVENT_REGISTER_COMPANIONS = "home_keeper_register_companions"
# The first Home Keeper version with the panel tab API (``panel_tabs.py``).
HOME_KEEPER_MIN_VERSION = "0.30.0"
HOME_KEEPER_INSTALL_URL = "https://github.com/prestomation/ha-home-keeper#installation"
# The reasons why Home Keeper cannot take the library tab. Each is a config flow
# abort reason and a repair issue id with the same translation key.
ISSUE_HOME_KEEPER_MISSING = "home_keeper_missing"
ISSUE_HOME_KEEPER_NOT_SET_UP = "home_keeper_not_set_up"
ISSUE_HOME_KEEPER_TOO_OLD = "home_keeper_too_old"
HOME_KEEPER_REASONS = (
    ISSUE_HOME_KEEPER_MISSING,
    ISSUE_HOME_KEEPER_NOT_SET_UP,
    ISSUE_HOME_KEEPER_TOO_OLD,
)

# The entity platforms of the config entry.
PLATFORMS = ["sensor", "todo"]

# PANEL_VERSION is the same string as the manifest version. release.yml checks it,
# and rollup.config.mjs reads it.
PANEL_VERSION = "0.5.0b11"

# The built bundles are in frontend/dist/ and Home Assistant serves them here.
STATIC_URL = "/home_keeper_games_static"
TAB_JS_FILENAME = "games-tab.js"
CARD_JS_FILENAME = "games-card.js"
TAB_ID = "games"
TAB_ELEMENT = "home-keeper-games-tab"
TAB_ORDER = 60
TAB_HOST_API = 1

# The cover HTTP views.
COVER_URL_PREFIX = "/api/home_keeper_games/cover"
COVER_UPLOAD_URL = "/api/home_keeper_games/upload"
COVER_MAX_BYTES = 10 * 1024 * 1024
COVER_MAX_PX = 1200
# The cover files, below `.storage/`. The store file has the name of the domain.
COVERS_DIR = f"{DOMAIN}_covers"
# The dispatcher signal of a store change. Its argument is the store revision.
SIGNAL_STORE_CHANGED = f"{DOMAIN}_store_changed"
# The first bytes that the upload view reads to identify the image type.
SNIFF_BYTES = 16

# The storage document, ``.storage/home_keeper_games``.
STORAGE_KEY = DOMAIN
STORAGE_VERSION = 1
STORAGE_MINOR_VERSION = 1

# The config entry option.
CONF_CURRENCY = "currency"
DEFAULT_CURRENCY = "EUR"

# The IGDB keys: a Twitch client ID and client secret. They are config entry data,
# never options, so no service, event, reply or diagnostics has them.
CONF_IGDB_CLIENT_ID = "igdb_client_id"
CONF_IGDB_CLIENT_SECRET = "igdb_client_secret"
IGDB_API_URL = "https://api.igdb.com/v4"
IGDB_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
IGDB_IMAGES_URL = "https://images.igdb.com/igdb/image/upload"
# Only the test setups set these, to point the client at a fake server.
IGDB_API_URL_ENV = "HOME_KEEPER_GAMES_IGDB_API_URL"
IGDB_TOKEN_URL_ENV = "HOME_KEEPER_GAMES_IGDB_TOKEN_URL"
IGDB_IMAGES_URL_ENV = "HOME_KEEPER_GAMES_IGDB_IMAGES_URL"
IGDB_TIMEOUT_S = 10
# IGDB takes at most 4 requests each second.
IGDB_MIN_INTERVAL_S = 0.25
# A token is renewed when less than this time is left.
IGDB_TOKEN_MARGIN_S = 300
IGDB_SEARCH_DEFAULT = 10
IGDB_SEARCH_MAX = 20

# The Home Keeper capability of a companion that joins the export and import.
HOME_KEEPER_CAPABILITY_IMPORT_EXPORT = "import_export"

# The CSV import limits.
MAX_CSV_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROW_RESULTS = 200

# The overdue loan check interval.
OVERDUE_CHECK_INTERVAL_S = 60 * 60

# The number of titles that the "Playing now" sensor lists.
PLAYING_NOW_MAX_TITLES = 10

# The origin marker that this integration sends to Home Keeper, and that it reads
# back in the events of Home Keeper to stop a loop.
ORIGIN = DOMAIN

# The bus events. Each name is ``home_keeper_games_<noun>_<verb>``. The pure
# builders in events.py make the payloads, and the store fires them.
EVENT_ROOM_ADDED = f"{DOMAIN}_room_added"
EVENT_ROOM_UPDATED = f"{DOMAIN}_room_updated"
EVENT_ROOM_REMOVED = f"{DOMAIN}_room_removed"
EVENT_UNIT_ADDED = f"{DOMAIN}_unit_added"
EVENT_UNIT_UPDATED = f"{DOMAIN}_unit_updated"
EVENT_UNIT_REMOVED = f"{DOMAIN}_unit_removed"
EVENT_SHELF_ADDED = f"{DOMAIN}_shelf_added"
EVENT_SHELF_UPDATED = f"{DOMAIN}_shelf_updated"
EVENT_SHELF_REMOVED = f"{DOMAIN}_shelf_removed"
EVENT_GAME_ADDED = f"{DOMAIN}_game_added"
EVENT_GAME_UPDATED = f"{DOMAIN}_game_updated"
EVENT_GAME_REMOVED = f"{DOMAIN}_game_removed"
EVENT_COPY_ADDED = f"{DOMAIN}_copy_added"
EVENT_COPY_MOVED = f"{DOMAIN}_copy_moved"
EVENT_COPY_UPDATED = f"{DOMAIN}_copy_updated"
EVENT_COPY_REMOVED = f"{DOMAIN}_copy_removed"
EVENT_PROGRESS_CHANGED = f"{DOMAIN}_progress_changed"
EVENT_PROGRESS_UPDATED = f"{DOMAIN}_progress_updated"
EVENT_GAME_COMPLETED = f"{DOMAIN}_game_completed"
EVENT_SESSION_LOGGED = f"{DOMAIN}_session_logged"
EVENT_SESSION_DELETED = f"{DOMAIN}_session_deleted"
EVENT_LOAN_STARTED = f"{DOMAIN}_loan_started"
EVENT_LOAN_RETURNED = f"{DOMAIN}_loan_returned"
EVENT_LOAN_OVERDUE = f"{DOMAIN}_loan_overdue"
EVENT_LOAN_UPDATED = f"{DOMAIN}_loan_updated"
EVENT_LOAN_REMOVED = f"{DOMAIN}_loan_removed"
EVENT_WISHLIST_ADDED = f"{DOMAIN}_wishlist_added"
EVENT_WISHLIST_REMOVED = f"{DOMAIN}_wishlist_removed"
EVENT_IMPORT_COMPLETED = f"{DOMAIN}_import_completed"
EVENT_DATA_IMPORTED = f"{DOMAIN}_data_imported"
EVENT_PERSON_SETTINGS_UPDATED = f"{DOMAIN}_person_settings_updated"
EVENT_SETTINGS_UPDATED = f"{DOMAIN}_settings_updated"

# The languages of every string table: strings.json, translations/ and
# backend_strings/. The same 16 languages as Home Keeper.
LANGUAGES = (
    "ca",
    "cs",
    "da",
    "de",
    "en",
    "es",
    "fi",
    "fr",
    "it",
    "nb",
    "nl",
    "pl",
    "pt-BR",
    "ru",
    "sv",
    "zh-Hans",
)
