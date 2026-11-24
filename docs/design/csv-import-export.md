---
title: CSV import and export
summary: How the integration reads its own CSV format with a dry run first, how it matches rows to games, and how it writes an export.
implements:
  - custom_components/home_keeper_games/csv_io.py
  - custom_components/home_keeper_games/frontend/src/tab-import.ts
related: [store-models, events-api, import-export]
source_hash: 8a8e04bfbee6
---

# CSV import and export

An admin edits the collection in a spreadsheet, or moves it from 1 Home Assistant to
another, with the CSV format of the integration. The import runs as a dry run first, so
the admin sees the counts before a write.

## Goals

- **G1. Preview before write.** A dry run is the same pure call as the import, with the
  result thrown away. The preview and the import cannot disagree.
- **G2. No second game.** A row matches a stored game by id, then barcode, then title.
- **G3. Keep what is there.** A reading row that the person has now stays, unless the
  admin asks to replace it. A copy id that is already stored is not added again.
- **G4. Round trips.** `parse(write(rows))` gives the rows back.

## Non-goals

- The CSV formats of other apps. The integration reads only its own format.
- Network calls inside the import.
- The whole document. The Home Keeper export holds it ([import-export](import-export.md)).

## Design

### Steps

1. `csv_io.parse` reads the text into import rows. The file needs the `title` column. A
   file of more than 5 MB is refused with `csv_too_large`.
2. `csv_io.apply_import` plans the import on a snapshot of the document in an executor
   job. It returns the planned document, the counts and 1 result for each row.
3. With `dry_run: true` the service returns the counts and the first 200 row results.
   Else `LibraryStore.commit_import` writes the plan and fires `import_completed` with
   the source `csv`.

**An import never replaces the document.** Other changes can come in while the plan
runs. `models.merge_changes` compares the snapshot with the plan, and writes into the
current document only the records and the fields that the plan changed. The merge and
the save have no `await` between them, so no other change comes in the middle.

- A change to another field of the same record stays.
- A record that a user deleted while the plan ran stays deleted.
- A planned copy or reading row of a deleted game is dropped. A planned copy on a
  deleted shelf goes to no shelf.

### Columns

The file has every game field, the copy fields, the location as a path of room, unit
and shelf names, the reading row of the chosen person and the wishlist flags
(`csv_io.LIBRARY_COLUMNS`). A list cell separates its items with `; `. The barcode cell
is cleaned as in [scan-and-barcode](scan-and-barcode.md#barcode-rules). The barcode cell
is a copy field. A row whose barcode is on a copy of another game is an error row.

- A row puts its copy on the shelf of its path when that shelf exists, else on the
  chosen shelf. A row with no copy id adds a copy only to a game with no copy.
- A `game_id` or `copy_id` that is not 32 lower-case hex characters is dropped.
- The import checks the copy of a row first, so a row with a bad copy changes no record.
- A game has 1 row for each copy. The first row of the game sets the reading status.
- A row with `wishlist` true puts a game with no copy on the wishlist of the person.

### Export

`csv_io.export` writes 1 row for each copy, and 1 row for a game with no copy. With a
person, the file has the reading status of that person. With no person, it has all games
and no reading status. `csv_io.export_filename` names the file with the date.

### Tab

`tab-import.ts` is the Import dialog at `/import`: person, shelf for new games, file,
preview table and counts, then **Import**. It reads the file in the browser and sends the
text to `import_csv`. A new person or shelf starts a new preview, and the tab uses only
the reply of the latest preview.

## Trade-offs

- **1 merge of the plan** over **1 store call for each row**: 1 save and 1 event for
  an import of thousands of rows. The cost is the merge, which compares 3 documents.
- **Text in a service field** over **a file upload**: an automation can call the import.
  The limit is 5 MB.
- **Match by title** after the barcode: a row that a user typed often has no barcode. A
  wrong match is possible for 2 games with the same title.

## One-way doors

- The column names of the CSV format.
- The count keys of the import reply (`csv_io.COUNT_KEYS`).
- The `import_completed` source value `csv`.
