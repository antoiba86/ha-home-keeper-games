---
title: Store and models
summary: The storage document, the records of the library, the pure model functions and the 1 write path that saves and fires events.
implements:
  - custom_components/home_keeper_games/store.py
  - custom_components/home_keeper_games/models.py
related: [architecture, events-api, people-privilege, csv-import-export]
source_hash: a92d187f3c88
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
  library game in the reading history, an ebook, or a wishlist entry.
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
| `reading` | `{person_id: {game_id: row}}` | `models.READING_FIELDS` and `updated_at` |
| `loans` | `{id: loan}` | `direction`, `game_id`, `copy_id`, `party`, dates, `hk_task_id` |
| `people` | `{person_id: settings}` | `models.PERSON_FIELDS` |
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
  ([scan-and-barcode](scan-and-barcode.md#barcode-rules)).
- `models.title_key` folds the whole title for a match with no barcode. The part after
  `:` counts, because it often names another game of 1 franchise.

### The write path

Each method ends in `_commit`: save, add 1 to `revision`, fire the events, call each
listener. A listener that fails is logged and the others still run. The listeners are:

- the coordinator;
- the sender of `const.SIGNAL_STORE_CHANGED`, for the `subscribe` websocket command;
- the wishlist sync and the loan sync.

### Rules

- **Duplicates.** `add_game` returns the stored game with `existing: true` when the
  barcode matches. A second copy is a separate call. `update_game` refuses a barcode that
  another game has with `duplicate_barcode`.
- **Locations.** A room with units, a unit with shelves and a shelf with copies
  fail to delete with a localized error, unless `force: true`. With `force`, each child
  is removed and each copy moves to no shelf.
- **Game delete.** Deleting a game deletes its copies, reading rows and loans, and the
  cover file. Its wishlist to-do item goes to `todo_orphans`.
- **Reading.** `set_reading` with status `none` removes the row. A borrowed game sets the
  status of the person to `reading` if it is `want` or absent.
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
- The enum values: `models.FORMATS`, `models.CONDITIONS`, `models.STATUSES`,
  `models.DIRECTIONS` and `models.COVER_KINDS`.
- Dates as `YYYY-MM-DD` and time stamps as aware ISO 8601.
