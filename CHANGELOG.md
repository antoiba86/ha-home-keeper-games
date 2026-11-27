# Changelog

Each change that a user can see is in this file. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). `manifest.json` `version`
is the single source of truth (see `RELEASE.md`).

## [0.5.0b13] - 2026-11-27

### Added

- **[Play log](https://antoiba86.github.io/ha-home-keeper-games/docs/guide/work-in-progress#play-log).**
  A Play log page in the Games tab shows the play time of each person for each game and
  platform. Open a game to see its sessions, and log a session by hand.

## [0.5.0b12] - 2026-11-27

### Added

- **[PlayStation play time](https://antoiba86.github.io/ha-home-keeper-games/docs/guide/playstation).**
  Add a console of the PlayStation Network integration in the options, and each game
  that you play on it becomes a play session with its minutes. A game that the library
  does not have is added with a digital copy.

## [0.5.0b11] - 2026-11-27

### Added

- **[Play sessions](https://antoiba86.github.io/ha-home-keeper-games/docs/guide/services#play-sessions).**
  Log a play session of a game with its minutes, from an automation or a script. The
  minutes go on the play time, a game in the backlog becomes Playing, and each session
  stays in the history of the person.

## [0.5.0b10] - 2026-11-27

### Changed

- **Game words in the actions.** The names and descriptions of the actions, the errors
  and the repair issues say games and cabinets in place of books and bookcases, in each
  language. On a new install, the count sensor is `sensor.home_keeper_games_games`.

## [0.5.0b9] - 2026-11-26

### Changed

- **Game words in the tab.** The tab, the card and the Home Keeper companion list say
  games in place of books in each language, and a bookcase is now a cabinet. The names
  and descriptions of the actions still say books.

## [0.5.0b8] - 2026-11-26

### Added

- **[Telegram blueprint](https://antoiba86.github.io/ha-home-keeper-games/docs/guide/telegram).**
  Send `/juego Hades switch` to your Telegram bot to add the game with its IGDB details
  and a copy on that platform. The reply has an Undo button, and an Edit button that
  opens the game in the tab.

## [0.5.0b7] - 2026-11-25

### Added

- **[Change of IGDB game](https://antoiba86.github.io/ha-home-keeper-games/docs/guide/work-in-progress#igdb-game).**
  When an automation adds the wrong game, or IGDB does not find the title, select the
  correct IGDB game from the game page in the tab. Its title, details and cover replace
  the old ones, while the copies, progress, notes and loans stay.

## [0.5.0b6] - 2026-11-25

### Added

- **[Game details from IGDB](https://antoiba86.github.io/ha-home-keeper-games/docs/guide/services#igdb).**
  Enter a Twitch client ID and secret in the options, then find games with
  `search_catalog` and add a game with its summary, genres, release date, franchise and
  cover in 1 call to `add_game`.

## [0.5.0b5] - 2026-11-24

### Changed

- **[Play progress for each platform](https://antoiba86.github.io/ha-home-keeper-games/docs/guide/work-in-progress#play-progress).**
  In place of a reading status, each person has a play status, a rating, the play time,
  dates, a completion count and a private review for each platform of a game. The card,
  the Backlog to-do list and the sensors use it, and `set_reading` is now `set_progress`
  with a `platform` field, so update each automation that uses the reading services,
  events or entities.

## [0.5.0b4] - 2026-11-23

### Changed

- **Copy details.** Each copy has a platform, a physical or digital format, a storefront,
  a region, an edition, a steelbook mark and its own barcode, and a digital copy is on no
  shelf. The signed and first edition marks are gone.

## [0.5.0b3] - 2026-11-23

### Changed

- **Game details.** A game has a summary, genres, a release date and a franchise, and it
  keeps its tags and notes. The authors, subtitle, publisher, page count, language,
  subjects and series of a book are gone, and the to-do items show only the title.

## [0.5.0b2] - 2026-11-21

### Changed

- **Service and event names.** The services, the events and the stored records use "game"
  and "unit" in place of "book" and "bookcase", such as `add_game`, `game_id` and
  `home_keeper_games_game_added`. Update each automation that calls a service or listens
  for an event.

## [0.5.0b1] - 2026-11-21

### Changed

- **[Retail barcode scanning](https://antoiba86.github.io/ha-home-keeper-games/docs/guide/work-in-progress).**
  A scan reads any EAN-13, EAN-8 or UPC-A barcode, and a new barcode asks for the title.
  A book has 1 barcode field in place of its 2 ISBN fields, and `scan_isbn` is now
  `scan_barcode`.

### Removed

- **Open Library.** The library no longer reads details or covers from Open Library, and
  no longer sends books to it. Upload a photo to give a book a cover.
- **Goodreads and StoryGraph files.** The CSV import and export use only the format of
  Home Keeper Games.

## [0.4.0] - 2026-10-25

### Added

- **Open Library title match.**
  When a scanned ISBN has no match, the library looks for the title that you type on Open
  Library and asks if it is your book. If you confirm, the book gets the description,
  subjects and cover from Open Library, and keeps your ISBN.
- **SBN numbers.**
  You can type the 9-digit SBN of an old UK book where the library asks for an ISBN. The
  library finds and stores the book with the matching ISBN.

### Changed

- **Older Home Assistant.** The library now works with Home Assistant 2025.7 and later.
  Before, it needed 2026.9.

## [0.3.0] - 2026-10-12

### Added

- **Send books to Open Library.**
  An admin can connect an Open Library account and send a book that Open Library does not
  have, and the library links the new record. The **Not on Open Library** filter lists
  these books.
- **Title for unmatched scans.**
  If Open Library has no match for a scanned book, the scan stops and asks for its title,
  so you can find the book again later. You can also add the other details and a photo of
  the cover, or remove the scan.
- **Library in Home Keeper export.**
  The Home Keeper export file now holds your whole library: books, shelves, reading
  status, loans and wishlists. Its import brings them back or applies your edits, and a
  bundle export also holds the covers.

### Changed

- **Home Keeper betas.** The library works with a beta of Home Keeper. It does not
  check the Home Keeper version number now.
- **Camera on HTTP pages.** On an `http://` address, the scan says at once that the
  camera needs HTTPS, and it does not start the camera. **Enter ISBN** still works.
- **Integration icon.** Home Keeper Library now has its own icon: the Home Keeper house
  with a stack of books. It shows on the integration pages of Home Assistant.

### Fixed

- **Black camera after scan.** The camera picture stays on after each scan, so you can
  scan the next book at once. If the picture stops, tap it to start the camera again.
- **Camera after Back.** If you leave the scan step while the camera starts, the camera
  stops.
- **Changed ISBN.** When you change the ISBN of a book, its ISBN-10 changes too.
- **Custom covers.** A custom cover stays if the Open Library cover cannot be read. An
  Open Library cover does not replace a cover that you upload during its download.
- **Library CSV import.** A row with a bad copy value adds no book. A book with 2 or
  more copies counts 1 time in the reading totals.
- **ISBN with other digits.** An ISBN cell with a digit such as "²" does not stop the
  import. That row gets no ISBN.
- **Card updates after a reload.** The dashboard card shows changes again after a
  reload of the integration.
- **Wishlist privacy.** A user who is not an admin does not see the to-do list of the
  wishlist of another person.
- **Text after an error.** If a dialog or the notes editor cannot save, it keeps the
  text that you typed. A change that fails shows the stored value again.
- **Import preview.** If you change the import settings quickly, the preview shows the
  result of the last settings.
- **Home Keeper link.** A Home Keeper that refuses a field of the library no longer stops
  the setup of the library.

## [0.2.0] - 2026-10-05

### Added

- **ISBN barcode scan.** Scan the ISBN barcode of each book with a
  phone. The book goes on the selected shelf with its details and cover from Open
  Library. Enter the ISBN by hand for a book with no barcode.
- **Rooms and shelves.** Record the rooms, bookcases and
  shelves of the home. Each copy shows its shelf.
- **Book search and filters.** Find a book by its title, author, ISBN,
  series or notes. Filter the library by room, shelf, reader, subject and reading status.
- **Reading status and notes.** Each person keeps a reading status, a
  rating, the page, the dates and private notes for each book. Each copy keeps its
  format, condition, price and value.
- **Lent and borrowed books.** Record the books that are lent out or
  borrowed. Each due date gets a Home Keeper task, and the completed task returns the book.
- **Per-person wishlist.** Each person has a wishlist. The books to buy go
  to a to-do list of that person.
- **Goodreads and StoryGraph import.** Bring a reading history in
  from a Goodreads or StoryGraph CSV file, with a preview first. Export the library to a
  CSV file that both read.
- **[Dashboard card](https://antoiba86.github.io/ha-home-keeper-games/docs/guide/dashboard-card).** Each user gets a dashboard card with their
  reading and their yearly goal. The card also shows the books to read next and the
  household activity.
- **[Per-person entities](https://antoiba86.github.io/ha-home-keeper-games/docs/guide/services).** Each person gets a To read list and sensors for
  the books read this year and the books in progress.
- **[Services and events](https://antoiba86.github.io/ha-home-keeper-games/docs/guide/services).** Each operation of the Library tab is a service
  for automations. Each change fires an event.
- **[People and privacy](https://antoiba86.github.io/ha-home-keeper-games/docs/guide/people-and-privacy).** Prices, borrower names and private
  notes stay with the admins. Each person can stop sharing their reading status.
