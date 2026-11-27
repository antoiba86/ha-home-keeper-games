---
title: Ideas and open work
summary: The single backlog of Home Keeper Games work that is not built, for maintainers and agents.
---

# Ideas and open work

This file is the only list of work that is not built: bugs, gaps, refactors and ideas.
Nothing here is committed scope. When an item ships, remove it. The design docs in
`docs/design/` describe what is built.

## Known gaps

- **Home Keeper version check.** The check of the Home Keeper version against
  `const.HOME_KEEPER_MIN_VERSION` is off, so the library works with a Home Keeper beta.
  Bring it back in `home_keeper.async_check` and in its tests when that beta is stable.
- **Query of a tab path.** Home Keeper's host drops a `?query` from a tab path. Ask Home
  Keeper to keep it, then the `;key=value` form of the tab filters can go
  (see `docs/design/frontend-tab-card.md`).
- **Play sessions in the export.** `export_data` and `import_data` do not hold the play
  sessions (`import_export.EXCLUDED_KEYS`). Add a `sessions` section to the export
  format, with a check of the game and the person of each session.
- **PlayStation trophies.** An own PSN client (`psnawp`) with the NPSSO token in an
  options step reads the trophies of each game and the list of played games.
- **Nintendo play time.** A source for the Nintendo Switch Parental Controls or Presence
  integration, with the same consoles list.

## Product ideas

- **QR shelf labels.** Print a QR label for each shelf, built on the QR label work of
  Home Keeper. A scan of the label opens `/home-keeper/games/scan;shelf=<id>`.
- **Series gaps.** List the numbers that are missing from each series that the library
  holds, and put them on the wishlist in 1 step.
- **Reading log for children.** Minutes or pages for each day, a streak, and a goal for a
  person who is a child.
- **Insurance value report.** The total value and price of the copies for each room,
  with a CSV or PDF download for an insurance claim. Admin-only.
- **Phone walkthrough tour.** A second walkthrough capture at phone width: scan a shelf
  with **Enter barcode**, read the summary, set a status in the card.
- **Barcode lookup.** Turn the EAN of a game case into a title with a product lookup
  service, then search the catalog.

### Shelf photo

Take a photo of a shelf, and let the AI task service of Home Assistant read the spines.
Show each title as a scan result row with the same duplicate choices. The photo is never
stored.

### Sync mode for the Home Keeper import

The import of the library section is an upsert. A record that the user deleted from the
document stays in the library. A sync mode option of `import_data` deletes each record
that the document does not have, after a dry run shows the list. It needs the same mode
in Home Keeper ([import-export](docs/design/import-export.md)).

## Testing and CI

### Upgrade test tier

Boot a frozen older Home Assistant and Home Keeper on a seeded config dir, then the
current ones on the same dir, and check that the library, the tab and the loan tasks
load. Add a job in `ha-beta.yml` for it.

- **Browser test of the scan with a camera.** The e2e tier uses **Enter barcode**. A fake
  video stream with a barcode would cover the decoder chunk.

## Docs and quality

### Quality scale ledger

The integration uses the practices of the Platinum quality scale, and `manifest.json`
declares no tier. Add `quality_scale` and a `quality_scale.yaml` ledger with each rule
and its state.
