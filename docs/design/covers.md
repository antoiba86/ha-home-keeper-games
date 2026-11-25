---
title: Covers
summary: How the integration uploads, downloads, stores and serves the cover file of a game.
implements:
  - custom_components/home_keeper_games/covers.py
related: [scan-and-barcode, store-models, people-privilege, import-export, catalog-igdb]
source_hash: 3ca41bf2d931
---

# Covers

A cover is a photo that an admin uploads, or the IGDB cover of a game that `add_game` adds
from IGDB. The file is a JPEG next to the storage document, and an authenticated view
serves it.

## Goals

- **G1. Clean files only.** Every stored cover is a JPEG that Pillow wrote, at most
  1200 px, whatever the source.
- **G2. No stale image.** A new cover gets a new URL, so a browser cache never shows the
  old one.
- **G3. An upload wins.** An IGDB cover never replaces a cover that an admin uploaded.

## Non-goals

- A cover gallery with more than 1 cover for each game.
- Private covers. The cover view serves each signed-in user.

## Design

### Cover files

A cover file is `<game_id>-<token>.jpg` in `.storage/home_keeper_games_covers/`. The
directory is not below `.storage/home_keeper_games`, because that path is the store
file. The token changes with each new cover. `cover_url` is
`/api/home_keeper_games/cover/<id>?v=<token>`.

- **Upload.** `CoverUploadView` takes a multipart POST with 1 file from an admin user. It
  reads at most 10 MB, reads the type from the first bytes, and accepts JPEG, PNG and
  WebP. `covers.reencode` writes a new JPEG in an executor job, with a limit on the pixel
  count. The reply is a `file_id` in a pending folder. `set_cover` with `kind: custom`
  moves the file onto the game. A pending file that no game takes is deleted after 24
  hours, at setup.
- **IGDB.** `covers.async_store_igdb_cover` downloads the IGDB cover of a new game
  ([catalog-igdb](catalog-igdb.md)). The client builds the URL from the IGDB image id, so
  a caller cannot make the integration read another host. The bytes get the same type
  check and the same `reencode`, and the game gets `kind: igdb`. A game with
  `kind: custom` keeps its cover, also when an upload comes during the download. A
  failure leaves the game with no cover. `set_cover` does not take `kind: igdb`.
- **Remove.** `set_cover` with `kind: none` removes the cover of a game.
- **Serve.** `CoverView` returns the file of a game to each signed-in user, with a long
  private cache time. An `<img>` element cannot send a token, so the client signs the
  path.
- **Delete.** A new cover or a deleted game releases the old file, and the store deletes
  it in an executor job.
- **Bundle.** A Home Keeper export copies the cover files into its bundle, and an import
  writes each file again with `covers.reencode` ([import-export](import-export.md#files)).

## Trade-offs

- **Re-encode every image** over **store the upload as is**: a stored file is never an
  unknown format, and the size is small. The cost is a little CPU time in an executor.

## One-way doors

- The cover URL path `/api/home_keeper_games/cover/{game_id}` and the upload path
  `/api/home_keeper_games/upload`.
- The covers directory `home_keeper_games_covers`.
- The cover `kind` values `custom`, `igdb` and `none`, and the file name format.
