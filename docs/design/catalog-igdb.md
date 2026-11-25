---
title: IGDB catalog
summary: How the integration keeps the IGDB keys, searches IGDB and adds a game with its IGDB details and cover.
implements:
  - custom_components/home_keeper_games/catalog.py
  - custom_components/home_keeper_games/igdb.py
related: [covers, events-api, people-privilege, store-models, architecture]
source_hash: 51b3bdfd233e
---

# IGDB catalog

IGDB is the game database of Twitch. With a Twitch client ID and client secret, the
integration finds games by title and adds a game with its title, summary, genres, release
date, franchise and cover. `catalog.py` is the pure part: the queries and the mapping.
`igdb.py` is the HTTP client.

## Goals

- **G1. The keys stay secret.** The keys come in only through a flow step. No service
  field, event, reply, log line or diagnostics has the secret.
- **G2. A wrong game is worse than no game.** `add_game` with `lookup` uses an IGDB game
  only on an exact title match. Else it adds the title and marks the game.
- **G3. IGDB is optional.** With no keys, every other part of the integration works.
- **G4. A failure is clear.** Each failure is a localized error with its own key.

## Non-goals

- A write to IGDB.
- Details from IGDB for a game that is already in the library. A later step can add it.
- A barcode lookup. IGDB has no barcode search ([IDEAS](../../IDEAS.md)).
- A cache of searches. The rate limit protects the quota.

## Design

### Keys

The setup step and the options step have 2 optional fields, `igdb_client_id` and
`igdb_client_secret` (a password field). `config_flow.async_igdb_data` reads them:

- No client ID and no secret: no keys. A secret with no client ID is
  `igdb_keys_incomplete`.
- A client ID and an empty secret: the stored secret stays if the client ID is the same.
  Else `igdb_keys_incomplete`. The form shows the stored client ID, never the secret.
- A client ID and a secret: the flow gets a token first. A refusal is
  `invalid_igdb_auth`, any other failure is `cannot_connect`.

The keys are in the entry data, not in the options, so `set_settings` and the option
reads never see them. The options flow writes them with `async_update_entry`.
`LibraryCoordinator.igdb_keys` reads them at each call, so a change needs no reload.

### Client

`IgdbClient` uses the shared aiohttp session of Home Assistant:

- **Token.** A POST to the Twitch token URL with the keys in the form body, never in the
  URL. The token stays in memory with its expiry and its keys. The client gets a new
  token 5 minutes before the expiry, when the keys change, and once after a 401.
- **Queries.** A POST of an Apicalypse body to `/v4/games`, with the `Client-ID` and the
  bearer token. An async lock and a gap of 0.25 s keep the 4 requests each second of
  IGDB. Each request has a timeout of 10 s.
- **Errors.** No keys is `igdb_not_configured`. A token request that gets a 400, 401 or
  403, or a query that gets a 403 or a second 401, is `invalid_igdb_auth`. A network
  error, a timeout, a 429, a 5xx or a reply that is not JSON is `igdb_unavailable`. A log
  line names only the type of the error.
- **Covers.** A GET of `<images>/t_cover_big/<image_id>.jpg`, at most 10 MB. A failure
  gives no cover and never an error.
- **Test URLs.** The environment variables `HOME_KEEPER_GAMES_IGDB_API_URL`,
  `HOME_KEEPER_GAMES_IGDB_TOKEN_URL` and `HOME_KEEPER_GAMES_IGDB_IMAGES_URL` replace the
  3 URLs. Only the test setups set them.

### Mapping

`catalog.py` writes the queries and reads the replies. It trusts no field of a reply.

- **Search.** `search "<text>"; where version_parent = null`, so an edition or a port is
  not a result. A platform adds `platforms = (<id>)`. The text loses quotes, backslashes
  and control characters, so it cannot end the string.
- **Platforms.** `IGDB_PLATFORMS` maps each library platform but `other` to 1 IGDB id.
- **Game fields.** `name` is the title, `summary` the summary, `genres.name` the genres,
  `first_release_date` the `YYYY-MM-DD` release date in UTC, and the first franchise,
  else the first collection, the franchise. An empty value is left out.
- **Cover.** Only an image id of lower-case letters and digits makes a URL.
- **Match.** `best_match` takes the first result with the same `models.title_key`, and
  with the platform if the caller gives 1 that is not `other`.

### Services

- **`search_catalog`** (response only, open). `query`, an optional `platform`, and
  `limit` from 1 to 20 (default 10). The reply is `candidates`, best first, each with
  `igdb_id`, `title`, `release_year`, `platforms`, `cover_url` and `in_library` (the id
  of the game with this `igdb_id`, or null).
- **`add_game`** (admin) with `igdb_id`: a game with that id comes back with
  `existing: true`. Else the client reads the game. No game is `igdb_not_found`.
- **`add_game`** with `lookup: true` and `title`: the title is the search text, with the
  optional `platform`. A match adds the IGDB game, with the IGDB title. No match adds the
  title with `needs_details: true`.
- A barcode that a copy has wins over both, as in a plain `add_game`. A field that the
  caller gives wins over the IGDB value. After the add, the cover download runs
  ([covers](covers.md)). The store fires `game_added`, and `game_updated` for the cover.

## Trade-offs

- **Open search** over **admin-only search**: each user has a Home Assistant account, and
  the reply has only IGDB data and game ids. The rate limit keeps a loop of calls from
  the quota.
- **Exact title match** over **the first result**: the Telegram bot adds a game with 1
  call, and a wrong game is hard to see. The cost is more games that need details.
- **Keys in the entry data** over **a service to set them**: a service field goes into
  `call_service` events and the recorder.

## One-way doors

- The entry data keys `igdb_client_id` and `igdb_client_secret`.
- The `search_catalog` fields and reply keys, and the `add_game` fields `igdb_id`,
  `lookup` and `platform`.
- The error keys `igdb_not_configured`, `igdb_unavailable`, `invalid_igdb_auth` and
  `igdb_not_found`.
- The 3 environment variable names.
