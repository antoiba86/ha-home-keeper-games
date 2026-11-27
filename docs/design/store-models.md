---
title: Store and models
summary: The storage document, the records of the library, the pure model functions and the 1 write path that saves and fires events.
implements:
  - custom_components/home_keeper_games/store.py
  - custom_components/home_keeper_games/models.py
related: [architecture, events-api, people-privilege, csv-import-export]
source_hash: c8c271197022
---

# Store and models

The library is 1 JSON document in `.storage/home_keeper_games`. `models.py` holds the
pure functions that check input and build records. `LibraryStore` in `store.py` is the
only code that changes the document.

## Goals

- **G1. One write path.** Each change goes through a `LibraryStore` method. It checks the
  input with `models`, changes the document, saves it, fires the events and tells the
  listeners, in that order.
- **G2. A game is the title, a copy is the thing.** A game with 0 copies is valid: a
  game in the play history of a person, a borrowed game, or a wishlist entry.
- **G3. Stable ids.** Every record id is a uuid4 hex string. A person is a Home Assistant
  person by its collection id, never by its entity id.
- **G4. Safe loads.** A missing or damaged section loads as empty. A new section needs no
  migration step.

## Non-goals

- A database. The design size is 5000 games in 1 document.
- History of a record. The events tell an integrator about each change.
- Records that a caller writes directly. Every field goes through a `models` function.

## Design

### The document

| Section | Shape | Note |
|---|---|---|
| `rooms` | `{id: room}` | `name`, `area_id`, `order` |
| `units` | `{id: unit}` | `room_id`, `name`, `note`, `order` |
| `shelves` | `{id: shelf}` | `unit_id`, `name`, `order` |
| `games` | `{id: game}` | `models.GAME_FIELDS`, `cover`, `wishlist`, time stamps |
| `copies` | `{id: copy}` | `game_id` and `models.COPY_FIELDS` |
| `progress` | `{person_id: {game_id: {platform: row}}}` | `models.PROGRESS_FIELDS`, `updated_at` |
| `loans` | `{id: loan}` | `direction`, `game_id`, `copy_id`, `party`, dates, `hk_task_id` |
| `people` | `{person_id: settings}` | `models.PERSON_FIELDS` |
| `sessions` | `{id: session}` | `person_id`, `game_id`, `platform`, `source`, `started_at`, `ended_at`, `date`, `minutes` |
| `todo_orphans` | `[{entity_id, uid}]` | To-do items that the wishlist sync must remove |

`models.normalize_state` runs on every load and in the storage migration hook. It gives
each section its type, so a section that a later version adds needs no migration. The
storage version stays 1.1.

### Model functions

- `models.build_game`, `models.build_copy`, `models.build_loan` and the location builders
  check each field and return a new dict. They never change an argument and never read a
  clock: the store passes `now` and `today`.
- A bad value raises `models.LibraryError` with a key and placeholders. The key is in
  `strings.json` `exceptions`.
- A barcode goes through `models.barcode`
  ([scan-and-barcode](scan-and-barcode.md#barcode-rules)). The barcode is a field of the
  copy, because 2 platforms of 1 game have 2 codes.
- A copy has a `platform` from `models.PLATFORMS` and a `format` from `models.FORMATS`
  (`physical`, `digital`, `other`). A digital copy has no shelf: `build_copy` and
  `update_copy` set `shelf_id` to null, and `move_copy` to a shelf raises
  `digital_copy_no_shelf`.
- `models.title_key` folds the whole title for a match with no barcode. The part after
  `:` counts, because it often names another game of 1 franchise.
- `models.find_game_by_igdb_id` returns the oldest game with an `igdb_id`, so
  `add_game` from IGDB does not add 1 game 2 times ([catalog-igdb](catalog-igdb.md)).
- A cover `kind` is `custom` (an upload), `igdb` (a download) or `none`. `set_cover`
  takes only `models.SET_COVER_KINDS`, `custom` and `none` ([covers](covers.md)).

### The write path

Each method ends in `_commit`: save, add 1 to `revision`, fire the events, call each
listener. A listener that fails is logged and the others still run. The listeners are:

- the coordinator;
- the sender of `const.SIGNAL_STORE_CHANGED`, for the `subscribe` websocket command;
- the wishlist sync and the loan sync.

### Rules

- **Duplicates.** `add_game` with a barcode returns the game of the oldest copy that
  has the code (`models.find_game_by_barcode`), with `existing: true`. A second copy is a
  separate call. `add_copy` and `update_copy` refuse a barcode that a copy of another game
  has with `duplicate_barcode`.
- **Locations.** A room with units, a unit with shelves and a shelf with copies
  fail to delete with a localized error, unless `force: true`. With `force`, each child
  is removed and each copy moves to no shelf.
- **Game delete.** Deleting a game deletes its copies, progress rows, loans and play
  sessions, and the cover file. Its wishlist to-do item goes to `todo_orphans`.
- **Progress.** A person has 1 row for each platform of a game. `set_progress` with
  `play_status: none` removes the row. With no `platform`, the store uses the platform of
  the copies if they have only 1, else it refuses with `platform_required`. `completed`
  sets `completed_at` and adds 1 to `completion_count`; `playing` sets `started_at`.
  A loan does not change the progress.
- **Play sessions.** `log_session` adds a closed session with `source: manual`, and
  `models.session_progress` adds its minutes to the progress row of that person and
  platform. A new or `backlog` row becomes `playing`, and `last_played_at` takes the later
  date. `delete_session` takes the minutes off, down to 0. `get_state` does not hold the
  sessions; `list_sessions` reads them, the newest first.
  `start_session` and `end_session` open and close a session of a console listener
  ([console-activity](console-activity.md)). An open session has `minutes: null`.
- **Loans.** A copy has at most 1 open loan. A lent copy keeps its shelf.
- **Overdue.** `fire_overdue` marks each loan that passed its due date with
  `overdue_fired`, so `loan_overdue` fires once for each due date.
- **Wishlist.** A new copy of a game that has a wishlist entry and no copy clears the
  entry (`models.copy_clears_wishlist`), as `got_wishlist_game` does. The to-do item
  goes to `todo_orphans`, and `copy_added` fires before `wishlist_removed`.
- **Import.** `commit_import` merges the result of a CSV import into the current
  document and fires only `import_completed` ([csv-import-export](csv-import-export.md#steps)).
  `commit_data_import` does the same for a Home Keeper import and fires only
  `data_imported` ([import-export](import-export.md)).
- **Gamekeeping.** `set_loan_task` saves a field that only the loan sync reads, and
  fires no event.
- **Currency.** The currency is an option of the config entry, not a field of the
  document. `async_settings_updated` fires `settings_updated` and tells the listeners,
  so the clients read it again.

## Trade-offs

- **Plain dicts** over **model classes**: the document is the storage format and the
  reply format, with no conversion layer. The cost is that each shape is pinned by tests
  (`tests/unit/test_shapes.py`), not by a type.
- **Save before the events** over **events first**: an automation that reads the library
  on an event sees the change.
- **1 revision number** over **a change log**: a client reads the whole state again after
  each change. That is simple and consistent at the design size.

## One-way doors

- The storage key, the section names and the field names of each record.
- The enum values: `models.FORMATS`, `models.CONDITIONS`, `models.PLATFORMS`,
  `models.PLAY_STATUSES`, `models.DIRECTIONS` and `models.COVER_KINDS`.
- Dates as `YYYY-MM-DD` and time stamps as aware ISO 8601.
