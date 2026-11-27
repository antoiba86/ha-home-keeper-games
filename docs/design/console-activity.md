---
title: Console activity
summary: How the activity listener turns the media player of a PlayStation console into play sessions, and how it finds or adds the game.
implements:
  - custom_components/home_keeper_games/activity.py
  - custom_components/home_keeper_games/activity_listener.py
related: [store-models, catalog-igdb, events-api]
source_hash: c34d5703d354
---

# Console activity

An admin adds a console in the options of the integration: a media player of the
PlayStation Network integration, the person who plays on it, and its platform. While the
console plays a game, the listener keeps a play session open. When the game changes or
the console stops, the session closes and its minutes go on the play time.

## Goals

- **G1. No lost time.** An open session is in the store. A reload of the entry continues
  it, and a stop of Home Assistant closes it at the stop time.
- **G2. A short outage is not a stop.** An `unavailable` or `unknown` state keeps the
  session. The next known state decides, and a close uses the time of the first unknown
  state.
- **G3. 1 game for 1 title.** A title id that a past session has maps to the same game,
  also after a change of its title.
- **G4. Pure planning.** `activity.py` decides each step and imports no Home Assistant
  code. `activity_listener.py` only reads states and calls the store.

## Non-goals

- A direct connection to PSN. The listener reads the core PlayStation Network
  integration. Trophies and the list of played games are a later step with an own client.
- Nintendo and other sources. The console record has a `source`, so a later source
  adds a value, not a new shape.
- Sessions shorter than 1 minute. They are deleted.

## Design

### Consoles

`entry.options["consoles"]` is a list of `{entity_id, person_id, platform, source}`.
`activity.clean_consoles` keeps the valid ones, 1 for each entity. The options flow has a
second step, `consoles`, after the settings step: it keeps or removes the consoles and
adds 1 (`config_flow.consoles_from_input`). An options update restarts the listener.

### States

The PSN media player is `playing` with `media_title` (the game name) and
`media_content_id` (the PSN title id, such as `PPSA01234_00`) while a game runs, `on` in
the menu, and `off` when the console is off. `activity.now_playing` gives
`{title, title_id}` or None. `activity.next_step` compares it with the open session:

| Open session | Now | Step |
|---|---|---|
| none | a game | `open` |
| a game | none | `close` |
| a game | the same game | `keep` |
| a game | another game | `switch`: close, then open |
| any | `unavailable` or `unknown` | `keep`, and note the time |

The same game is the same title id, else the same `models.title_key` of the title.

### Sessions

`store.start_session` adds an open session (`source: psn`, `external_id` = the title id,
`started_at` = now, `minutes: null`) and fires `session_started`. A new or `backlog`
progress row becomes `playing` (`models.session_start_progress`). `store.end_session`
sets `ended_at` and `minutes` (`models.session_minutes`) and fires `session_logged`, and
the minutes go on the row as for `log_session`. Under 1 minute, it deletes the session
and fires `session_deleted`.

At the start, the listener takes the open session of each console from the store, with
`restored` set. If the console plays that game, the session continues. If it plays
nothing or another game, the end of the old session is not known (a crash), so the
session is deleted. At `homeassistant_stop` each open session closes.

### Games

`activity.match_game` returns the game of the newest session of the source with the
same title id, else the oldest game with the same title. With no match, the listener
calls `add_game` with `lookup: true` and the platform, so IGDB adds the details when it
has a game with that title. When IGDB is not set up, it calls `add_game` with
`needs_details: true`. A new game gets a digital copy on the platform of the console.
"Change IGDB game" in the tab corrects a wrong match.

## Trade-offs

- **The core PSN integration** over **an own PSN client**: no token in this
  integration, and Home Assistant keeps the login. The cost is a poll interval of that
  integration, so a session can start or end up to 1 poll late.
- **Close at stop** over **keep open over a restart**: a restart splits a session in 2,
  and the time of the restart does not count as play.

## One-way doors

- The option key `consoles` and its record keys.
- The session `source` value `psn` and the meaning of `external_id` (the PSN title id).
- The event `session_started`.
