---
title: Scan and barcode
summary: The barcode rules, the camera scanner with its lazy decoder chunk, the scan flow of the tab, and the scan_barcode service with its duplicate choices.
implements:
  - custom_components/home_keeper_games/frontend/src/scanner.ts
  - custom_components/home_keeper_games/frontend/src/zxing-decoder.ts
  - custom_components/home_keeper_games/frontend/src/tab-scan.ts
related: [covers, store-models, frontend-tab-card, loans-home-keeper]
source_hash: caad69b2e062
---

# Scan and barcode

An admin fills a shelf with a phone: open the scan flow for the shelf, point the camera at
the barcode on each case, and read the result of each scan. A barcode that the camera
cannot read is typed by hand. Each scan calls the `scan_barcode` service.

## Goals

- **G1. One barcode for one game.** Every barcode is cleaned to capital letters and
  digits with no spaces or hyphens, so 2 forms of 1 code find the same game.
- **G2. A shelf in 1 pass.** A scan adds the copy to the chosen shelf at once, and the
  next shelf is 1 step away.
- **G3. Duplicates are a choice.** A game that is already in the library asks for Move
  here, Add 2nd copy or Skip.
- **G4. A small bundle.** The barcode decoder loads only on a browser that needs it.

## Non-goals

- Details from a barcode. A scan of a new code saves the code as the title, and the
  user types the title. A lookup service is later work ([IDEAS.md](../../IDEAS.md)).
- A photo of a whole shelf. That is in [IDEAS.md](../../IDEAS.md#shelf-photo).
- Scans from the card. Scanning changes the catalog, so it is in the admin tab.

## Design

### Barcode rules
 `models.barcode` removes spaces and hyphens, changes letters to capitals, and accepts 1 to 50
letters and digits. Any other value raises `invalid_barcode`. The code is a field of the copy, and
`duplicate_barcode` stops a copy of a 2nd game from taking a code that a copy of another game has.
`utils.normalizeBarcode` has the same rule for the tab, so the tab can refuse a bad code before a
call. A field that takes a title or a barcode (`utils.retailBarcode`) reads the text as a barcode
only when it is an EAN-8, UPC-A or EAN-13 with a correct check digit, so a title such as
"1984" stays a title.

### Scanner

`scanner.ts` opens the rear camera with `getUserMedia`. It uses the native
`BarcodeDetector` when the browser supports EAN-13, EAN-8 or UPC-A. Else it imports
`zxing-decoder.ts` with a dynamic import, so Rollup puts `@zxing/library` in a separate
chunk. The decoder imports only the UPC and EAN readers.

- On a page that is not a secure context (`cameraNeedsHttps`), the setup step shows the
  HTTPS message under the camera method and turns off **Start**. **Enter barcode** still
  starts. If the camera step opens from its URL, it shows the same message and offers
  **Enter barcode**.
- If the browser refuses the camera, the tab shows the reason and offers **Enter barcode**.
- The torch button shows when the camera track has a torch.
- The same code is ignored for 3 seconds (`makeCodeGate`), so 1 game is 1 scan.
- The camera runs only on the camera step. Home Keeper redraws its panel when the data
  changes, and that moves the tab out of the page and back in. So the tab stops the
  camera only when it is still out of the page after the redraw, and it starts the
  camera again when it comes back.
- A browser can pause a video that leaves the page. The Home Assistant app for Android,
  with **Autoplay videos** off, then refuses a `play()` that no tap started. So a render
  of the tab keeps the video slot in the page (`dom.replaceKeeping`).
- The picture is stopped when the video is paused, the track ended, or the video time
  does not move for `FROZEN_MS` (frozen). If it stays stopped for `STALL_MS`, a button
  shows on the picture. A tap plays the video, or opens a new camera if the track ended
  or the picture is frozen.
- `;debug=1` on the scan route shows the camera state under the picture: the tab element,
  the video, the track, the last `play()` error and a log of the last camera events.

### Scan flow

The route is `/scan`, with `;shelf=<id>` to preselect the shelf and `;mode=borrowed` for
borrowed games ([frontend-tab-card](frontend-tab-card.md#the-tab)). The steps are setup
(room, shelf, method), camera or manual entry, and the summary. Each result row shows
Added, Already in a place, Moved here, Skipped or No game has this barcode. A row also
shows From wishlist when the reply has `from_wishlist: true`. **Next shelf** goes to the
next shelf in display order. The summary can set the status Read for the caller on each
game that the session added or moved.

### Title sheet

A `not_found` result opens the title sheet (`scan-title` dialog, `nextMiss` in `utils.ts`).
The camera reads no code and **Enter barcode** adds no game until the user saves a title or
selects **Remove this scan**. The sheet has no close button, and Escape and the scrim do
not close it. Save calls `update_game` with the title and each optional field that has a
value, `update_copy` for a new format or platform, and `set_cover` for a photo. Remove calls
`delete_game`. A failed call keeps the sheet open with the error. The game keeps
`needs_details`. A 2nd miss waits until the 1st closes. After the last sheet, the barcode
field gets the focus. If the user leaves the scan, the sheet closes and the game keeps its
barcode as the title.

In borrowed mode each scan calls `borrow_game` with the barcode, the lender and the due date
of the session, and adds no copy ([loans-home-keeper](loans-home-keeper.md)).

### The `scan_barcode` service

1. Check the shelf. A missing `shelf_id` means no shelf.
2. Clean the barcode. An empty value raises `field_required`.
3. If no copy has the barcode, add a game with the barcode as its title and
   `needs_details: true`, and add a copy with the barcode, the `platform` and the
   `format`. The result is `not_found`.
4. If the game has no copy, add a copy: `added`.
5. If the game has copies, `on_duplicate` decides: `ask` returns `duplicate` with the
   copies and their locations, `skip` returns `skipped`, `move` moves a copy that is not
   digital from another shelf and returns `moved`, and `add_copy` adds a copy.

The scan setup has a platform and a format. Each copy that the scan adds gets them.

The reply has `from_wishlist: true` when the new copy took its game off the wishlist
([store-models](store-models.md#rules)). The service then runs the wishlist sync, so the
to-do item goes at once.

## Trade-offs

- **A service call for each scan** over **a batch at the end**: each result shows at once,
  and an automation can use the same service. The cost is 1 round trip for each game.
- **The native detector first** over **zxing always**: the native path is faster and
  costs no download. The cost is 2 code paths to test.
- **A required title** over **a dashed row only**: a row scrolls away as the scan goes
  on, and the user cannot find the game later. The cost is 1 stop for each miss.
- **Ask on a duplicate** over **add a copy by default**: a scan of a shelf that is already
  in the library is the most common duplicate, and it means a move.

## One-way doors

- The `scan_barcode` fields (`barcode`, `shelf_id`, `platform`, `format`, `on_duplicate`), the
  result values `added`, `duplicate`, `moved`, `skipped` and `not_found`, and the reply key
  `from_wishlist`.
- The scan URL and its parameters `shelf`, `mode` and `step`.
- The cleaned barcode as the key of the duplicate check.
