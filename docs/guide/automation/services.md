# Services and events

Each operation of the Games tab is a `home_keeper_games.*` service. Automations,
scripts and voice assistants can use the services to change the library, and the bus
events to react to a change.

## Services

The services are in **Developer tools → Actions**, with a description of each field.
Most services are admin-only. `set_progress`, `log_session`, `delete_session`,
`set_person_settings` and the read services are open to every user, for their own person
([People and privacy](../start/people-and-privacy.md)).

Example: set the status Completed when an NFC tag on the unit is scanned.

```yaml
automation:
  - alias: Completed a game
    triggers:
      - trigger: tag
        tag_id: console-shelf
    actions:
      - action: home_keeper_games.set_progress
        data:
          game_id: "5f0c1b2a9d8e4f7a8b6c5d4e3f2a1b0c"
          person_id: "alice"
          platform: switch
          play_status: completed
```

### Play sessions

`log_session` adds a play session of a person: the game, the platform, the minutes and
the date. The minutes go on the play time of that game and platform, and a game in the
backlog becomes **Playing**. `delete_session` takes the minutes off again.
`list_sessions` returns the sessions, the newest first. Example: log 45 minutes when a
script stops.

```yaml
actions:
  - action: home_keeper_games.log_session
    data:
      game_id: "5f0c1b2a9d8e4f7a8b6c5d4e3f2a1b0c"
      person_id: "alice"
      platform: ps5
      minutes: 45
```

A read service returns a response. Example: find the shelf of a game.

```yaml
actions:
  - action: home_keeper_games.list_games
    data:
      query: dune
    response_variable: found
  - action: home_keeper_games.get_game
    data:
      game_id: "{{ found.games[0].id }}"
    response_variable: detail
```

## IGDB

With the [IGDB keys](../start/installation.md#igdb-keys), 3 services read game details
from IGDB:

- `search_catalog` returns up to 20 IGDB games for a title, best first. Each user can
  call it.
- `add_game` with `igdb_id` adds that game with its summary, genres, release date,
  franchise and cover. If a game in the library has the same IGDB ID, the service
  returns that game.
- `add_game` with `title` and `lookup: true` adds the IGDB game with the same title. If
  no IGDB game has the same title, it adds the title only and marks the game as
  incomplete. Add `platform` to match only a game on that platform.
- `set_igdb_game` with `game_id` and `igdb_id` gives a game in the library another IGDB
  game. The title, summary, genres, release date, franchise and cover come from IGDB.
  The tags, notes, copies, progress and loans do not change.

Example: add a game from its title.

```yaml
actions:
  - action: home_keeper_games.add_game
    data:
      title: "Hades"
      lookup: true
      platform: pc
    response_variable: result
```

## Events

The library fires an event for each change, such as
`home_keeper_games_game_completed`, `home_keeper_games_loan_started` and
`home_keeper_games_loan_overdue`. Use them with an **Event** trigger.

```yaml
automation:
  - alias: Overdue loan reminder
    triggers:
      - trigger: event
        event_type: home_keeper_games_loan_overdue
    actions:
      - action: notify.notify
        data:
          message: "{{ trigger.event.data.title }} was due on {{ trigger.event.data.due }}."
```

## Entities

| Entity | State |
|---|---|
| **Games** | The games with 1 copy or more |
| **Loans out** | The open loans of lent copies |
| **Loans overdue** | The open loans past their due date |
| *Person* **games completed this year** | The games completed this year on any platform, with the goal |
| *Person* **playing now** | The games with status Playing, with their titles |
| *Person* **backlog** | A to-do list of the games with status Backlog, 1 item for each platform |

Complete an item of a **backlog** list to set the status Completed on that platform. Add an item to add a game
to the list. The per-person entities follow the privacy rules in
[People and privacy](../start/people-and-privacy.md#entities).

## Reference

- [Integrating](https://antoiba86.github.io/ha-home-keeper-games/developer/integrating)
  has the services by group and the contract for other integrations.
- [Events](https://antoiba86.github.io/ha-home-keeper-games/developer/events) has
  each event, its payload and when it fires.
- [API reference](https://antoiba86.github.io/ha-home-keeper-games/developer/api)
  has every service field, event payload and entity attribute.
