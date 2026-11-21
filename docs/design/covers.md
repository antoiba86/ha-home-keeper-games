---
title: Covers
summary: How the integration uploads, stores and serves the cover file of a book.
implements:
  - custom_components/home_keeper_games/covers.py
related: [scan-and-barcode, store-models, people-privilege, import-export]
source_hash: b1603f4942c2
---

# Covers

A cover is a photo that an admin uploads. The file is a JPEG next to the storage document,
and an authenticated view serves it.

## Goals

- **G1. Clean files only.** Every stored cover is a JPEG that Pillow wrote, at most
  1200 px, whatever the source.
- **G2. No stale image.** A new cover gets a new URL, so a browser cache never shows the
  old one.

## Non-goals

- A cover from an online catalog. A catalog is later work ([IDEAS](../../IDEAS.md)).
- A cover gallery with more than 1 cover for each book.
- Private covers. The cover view serves each signed-in user.

## Design

### Cover files

A cover file is `<book_id>-<token>.jpg` in `.storage/home_keeper_games_covers/`. The
directory is not below `.storage/home_keeper_games`, because that path is the store
file. The token changes with each new cover. `cover_url` is
`/api/home_keeper_games/cover/<id>?v=<token>`.

- **Upload.** `CoverUploadView` takes a multipart POST with 1 file from an admin user. It
  reads at most 10 MB, reads the type from the first bytes, and accepts JPEG, PNG and
  WebP. `covers.reencode` writes a new JPEG in an executor job, with a limit on the pixel
  count. The reply is a `file_id` in a pending folder. `set_cover` with `kind: custom`
  moves the file onto the book. A pending file that no book takes is deleted after 24
  hours, at setup.
- **Remove.** `set_cover` with `kind: none` removes the cover of a book.
- **Serve.** `CoverView` returns the file of a book to each signed-in user, with a long
  private cache time. An `<img>` element cannot send a token, so the client signs the
  path.
- **Delete.** A new cover or a deleted book releases the old file, and the store deletes
  it in an executor job.
- **Bundle.** A Home Keeper export copies the cover files into its bundle, and an import
  writes each file again with `covers.reencode` ([import-export](import-export.md#files)).

## Trade-offs

- **Re-encode every image** over **store the upload as is**: a stored file is never an
  unknown format, and the size is small. The cost is a little CPU time in an executor.

## One-way doors

- The cover URL path `/api/home_keeper_games/cover/{book_id}` and the upload path
  `/api/home_keeper_games/upload`.
- The covers directory `home_keeper_games_covers`.
- The cover `kind` values `custom` and `none`, and the file name format.
