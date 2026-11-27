---
title: Home Keeper export and import
summary: How the library joins the combined export and import of Home Keeper, what its section holds, how an import matches records, and how the cover files travel in a bundle.
implements:
  - custom_components/home_keeper_games/import_export.py
related: [csv-import-export, home-keeper-dependency, store-models, events-api]
source_hash: 68b9184c8850
---

# Home Keeper export and import

The Home Keeper export holds the library. An admin does 1 export and 1 import for Home
Keeper and for each companion. The library registers the capability `import_export`
with `register_companion` and has 2 admin-only services, `export_data` and `import_data`.
The contract is section 11 of the `INTEGRATING.md` of Home Keeper.

## Goals

- **G1. All library data travels.** The section holds each section of the document. A
  stored key that is not exported is in `import_export.EXCLUDED_KEYS` with a reason.
- **G2. Portable data.** Next to each person, area and to-do entity id, the export has
  its name. An id that only 1 install knows is not exported.
- **G3. Upsert only.** An import matches a record and updates it, or adds it. It never
  deletes a record that is not in the document.
- **G4. Preview before write.** `plan_import` changes no argument, so a dry run and the
  import give 1 report. An `error` blocks the whole import.

## Non-goals

- A sync between 2 installs. An import reads a document once.
- A JSON export of the library alone. The export of Home Keeper holds it.
- Network calls inside the import.

## Design

### Section

`import_export.build_export` makes the `data`: `format` and 1 list for each of `rooms`,
`units`, `shelves`, `games`, `copies`, `loans`, `progress` and `people`. A record is
the stored record, with these changes:

- A room has `area_name`. A loan has `person_name`. The wishlist entry of a game has
  `person_name`.
- `progress` has 1 entry for each person: `person_id`, `person_name` and `games`, 1 row
  for each platform with its `game_id` and `platform`. On import, a platform that is not
  in `models.PLATFORMS` is an error, and a missing one becomes `other`.
- `people` has the settings of each stored person with `person_name` and
  `wishlist_todo_name`.
- `game.cover` is `{kind, file}` with a relative path in a bundle, else `null`.

`EXCLUDED_KEYS` drops `hk_task_id`, the `todo_uid` and `todo_entity` of a
wishlist entry, `todo_orphans` and `sessions`. Format 1 has no play sessions yet; the
play time of each progress row goes out. `services.py` reads the names from the person, area
and entity registries and gives plain maps to the pure module. The reply of `export_data`
is `{format, version, data, skipped}`, and `data` goes through
`projections.project_export`.

### Import

`import_export.plan_import` plans on a snapshot in an executor job, section by section
in the order of `SECTIONS`. Home Keeper sends the whole section `{format, version, data,
skipped}`. `unwrap_document` takes its `data` and keeps the outer `format`. A document
that is only `data` also imports.

1. Refuse a `format` above `import_export.FORMAT`.
2. Match a room by id, then by name. Match a unit or a shelf by id, then by name in
   its parent.
3. Match a game by id, then title, with the index of `csv_io`. A copy with a barcode
   that a copy of another game has gives an `error` and is not imported. A digital copy
   goes on no shelf.
4. Match a copy or a loan by id. Else add it. A loan that exists keeps its task id.
5. Find a person, an area or a to-do entity by id on this install, then by name. 2
   records with 1 name match neither. A person that matches neither gives a `warning`,
   and the import skips the rows of that person.
6. A new record keeps the id of the document if the id is free. A reference to a record
   that is not in the document or in the library is an `error`.

A problem is `{level, path, message}`. `path` starts at the document, such as
`games[3].title`. The reply is `{ok, dry_run, counts, records, problems}`. `counts` has
`created`, `updated` and `skipped` for each section, and `covers` has `imported` and
`skipped`. If the plan has no `error` and `dry_run` is false,
`LibraryStore.commit_data_import` merges the plan, as a CSV import does
([csv-import-export](csv-import-export.md#steps)), and fires only `data_imported`. Then
the loan sync and the wishlist sync run, so the loan tasks and the to-do items come back.

### Files

`files_dir` is set only for a bundle. `import_export.check_files_dir` refuses a path that
is not at or below `<config>/.storage/home_keeper_import_export/`, and a relative path
with `..`. The service checks the real path again, after it resolves symbolic links.

- **Export.** `covers.copy_covers_out` copies each cover file to `covers/<game_id>.jpg`
  in `files_dir`. A cover file that the export does not copy, such as with no bundle, is
  counted in `skipped.covers`.
- **Import.** `covers.read_bundle_cover` reads a file at most 10 MB in `files_dir` and
  checks its first bytes. `covers.reencode` writes a new JPEG before the merge, so the
  cover goes in with the records. A bad file is a `warning`.

## Trade-offs

- **Upsert** over **replace**: an import cannot lose data. The cost is that a record that
  the user deleted from the document stays.
- **Match a copy by id only** over **match by game**: a copy has no natural key. An
  import into an install that has the game adds the copy of the document next to it.
- **Names next to ids** over **ids only**: a person or an area moves to a new install by
  name. 2 people with 1 name match neither.

## One-way doors

- The service names `export_data` and `import_data`, their fields and their replies.
- The keys of the section and `import_export.FORMAT`. A change of the meaning of a key
  needs a new format.
- The capability `import_export` and the event `home_keeper_games_data_imported`.
