---
title: Coordinator and entities
summary: The coordinator that pushes each store change to the entities, the library and per-person sensors, the Backlog list of each person, and the service device.
implements:
  - custom_components/home_keeper_games/coordinator.py
  - custom_components/home_keeper_games/entity.py
  - custom_components/home_keeper_games/sensor.py
  - custom_components/home_keeper_games/todo.py
related: [store-models, people-privilege, events-api]
source_hash: a0cd718e21ac
---

# Coordinator and entities

The entities are the usage surface for automations, dashboards and voice: counts of the
library, the play progress of each person, and a native to-do list of the backlog of each
person.

## Goals

- **G1. Push, never poll.** Each store change reaches the entities at once.
- **G2. Native usage.** A person uses the Backlog list in the Home Assistant to-do panel,
  on a phone and by voice, with no custom UI.
- **G3. Rename-safe.** A per-person entity is anchored to the person id, so a new name
  keeps the entity and its history.
- **G4. 1 device.** All entities of the config entry are on 1 service device.

## Non-goals

- 1 entity for each game. A library of thousands of games would flood the entity
  registry.
- A calendar of due dates. The loan tasks put due dates in Home Keeper.
- Device triggers. The events cover the changes ([events-api](events-api.md)).

## Design

### Coordinator

`LibraryCoordinator` is a `DataUpdateCoordinator` with no interval. The store calls
`async_store_changed` after each change, and the coordinator sends the document with
`async_set_updated_data`. The coordinator also holds the parts of the loaded entry that
the services, the websocket commands and the views use: the store, the 2 syncs, the Home
Keeper link and the currency option. `async_check_settings` fires `settings_updated` for a
new currency
([events-api](events-api.md#events)).
`coordinator.find_coordinator` returns it for a call, or None while no entry is loaded.

### Device and people

`entity.device_info` gives 1 service device for the config entry.
`entity.async_track_people` adds the entities of each Home Assistant person now, and of a
new person on the next store change. A `PersonEntity` has the person id in its
`unique_id`, the person name in the `{person}` placeholder of its translated name, and the
attribute `person_id`. It is unavailable while the person does not exist, and while the
person does not share their progress ([people-privilege](people-privilege.md#entities)).

### Sensors

| Key | State | Attributes |
|---|---|---|
| `games` | Games with 1 copy or more | |
| `loans_out` | Open loans that lend a copy out | |
| `loans_overdue` | Open loans past their due date | |
| `games_completed_this_year` | Games completed this year on any platform | `goal`, `year` |
| `playing_now` | Games with a `playing` row, last change first | `games`: at most 10 titles |

The counts come from the pure functions of `projections.py`. The hourly overdue check
also updates the listeners, so the date-based states change at midnight within 1 hour.

### Backlog list

`BacklogList` is a `todo` entity for each person. Its items are the progress rows with
play status `backlog`, oldest first. The summary is the title and the uid is
`game_id:platform`, so 1 game can have 1 item for each platform.

- Completing an item sets `completed` on that platform, and the store sets
  `completed_at` to today.
- Adding an item gives a `backlog` row to the game with that title, on the platform of its
  copies, or on `other` when the copies have no single platform. If no game matches, the
  list adds a game with `needs_details: true`.
- Deleting an item removes the `backlog` row.
- Each change checks the caller first ([people-privilege](people-privilege.md#entities)).

## Trade-offs

- **Per-person entities for every person** over **an opt-in list**: each person gets the
  list and the sensors with no setup. The cost is a privacy check in each entity, because
  Home Assistant shows each entity to every user.
- **A to-do list for the backlog** over **a list for each status**: the backlog is the
  status that a person works through.
- **Counts as sensors** over **attributes on 1 sensor**: each count has its own history
  and can drive an automation.

## One-way doors

- The unique ids `home_keeper_games_<key>` and `home_keeper_games_<person_id>_<key>`.
- The sensor keys and the attributes `goal`, `year`, `games` and `person_id`.
- The uid of a Backlog item, `game_id:platform`.
