---
title: Events reference
summary: The bus events of Home Keeper Games for integrators. When each event fires, with its payload and an example automation.
---

# Events reference

Home Keeper Games fires a Home Assistant bus event for each change to the
library. Automations and other integrations use these events. Each event
observes a change that a service already makes, so an event needs no service of
its own.

A pure function in `events.py` builds each payload. The store fires the event
after it saves the change. So a change from the tab, the card, a service, the
to-do list or a Home Keeper task fires the same event.

`api_surface.py` has the same catalog in `EVENTS` and `PAYLOAD_SPINES`.
`tests/unit/test_api_surface.py` calls the real builders and compares the keys.

## Event catalog

Names follow `home_keeper_games_<noun>_<verb>`.

| Event | Fires when |
|---|---|
| `home_keeper_games_room_added` | A room is added. |
| `home_keeper_games_room_updated` | A room changes. The payload has `changed_fields`. |
| `home_keeper_games_room_removed` | A room is deleted. |
| `home_keeper_games_unit_added` | A unit is added. |
| `home_keeper_games_unit_updated` | A unit changes or moves to another room. |
| `home_keeper_games_unit_removed` | A unit is deleted. |
| `home_keeper_games_shelf_added` | A shelf is added. |
| `home_keeper_games_shelf_updated` | A shelf changes or moves to another unit. |
| `home_keeper_games_shelf_removed` | A shelf is deleted. |
| `home_keeper_games_game_added` | A game is added. |
| `home_keeper_games_game_updated` | The fields, the cover or the wishlist entry of a game change. |
| `home_keeper_games_game_removed` | A game is deleted with its copies, reading rows and loans. |
| `home_keeper_games_copy_added` | A copy is added. |
| `home_keeper_games_copy_moved` | A copy moves to another shelf, or to no shelf. |
| `home_keeper_games_copy_updated` | A field of a copy other than its shelf changes. |
| `home_keeper_games_copy_removed` | A copy is deleted. |
| `home_keeper_games_reading_changed` | The reading status of a person changes. |
| `home_keeper_games_reading_updated` | The rating, page, dates, count or notes of a reading row change, and the status stays. |
| `home_keeper_games_game_finished` | The reading status of a person becomes `read`. |
| `home_keeper_games_loan_started` | A game is lent or borrowed. |
| `home_keeper_games_loan_returned` | A loan is returned. |
| `home_keeper_games_loan_overdue` | An open loan passes its due date. |
| `home_keeper_games_loan_updated` | The party, the dates, the format or the note of a loan change. |
| `home_keeper_games_loan_removed` | A loan is deleted. |
| `home_keeper_games_wishlist_added` | A game goes on the wishlist of a person. |
| `home_keeper_games_wishlist_removed` | A game leaves the wishlist. |
| `home_keeper_games_import_completed` | A CSV import is written. |
| `home_keeper_games_data_imported` | The library section of a Home Keeper import is written. |
| `home_keeper_games_person_settings_updated` | The library settings of a person change. |
| `home_keeper_games_settings_updated` | The options of the library change, such as the currency. |

## Payloads

The game, copy, reading, loan and wishlist events share 1 spine:

```json
{
  "game_id": "5f0c1b2a9d8e4f7a8b6c5d4e3f2a1b0c",
  "title": "The Left Hand of Darkness",
  "person_id": "alice",
  "origin": null
}
```

`person_id` is the id of the Home Assistant person, or `null`. `origin` is the
marker of the caller, or `null` for a user. A change that comes from a Home
Keeper task has the origin `home_keeper_games`.

The other keys of each event are in the generated API reference and in
`api_surface.EVENTS`:

- `game_updated` and the location `*_updated` events add `changed_fields`.
- The copy events add `copy_id` and `shelf_id`. `copy_moved` adds
  `previous_shelf_id`. `copy_updated` adds `changed_fields`, with the names of
  the fields only, not their values (no price or value).
- `reading_changed` adds `status` and `previous_status`. A removed reading row
  has `status: null`.
- `reading_updated` adds `status` and `changed_fields`. It names the changed
  fields and never gives the private notes.
- `game_finished` adds `finished`, `rating` and `read_count`.
- The loan events add `loan_id`, `direction`, `copy_id`, `party`, `started`,
  `due` and `returned`. `direction` is `out` for a lent copy and `in` for a
  borrowed game. `loan_updated` adds `changed_fields`. `loan_removed` has the
  loan as it was before the delete.
- The wishlist events add `buy` and `bought`.
- The room, unit and shelf events have their own ids and `name` in place of
  the game spine.
- `import_completed` has `person_id`, `source` (always `csv`) and the counts of the import.
- `data_imported` has `counts` and `origin`. `counts` has `created`, `updated` and
  `skipped` for each section, such as `games`.
- `person_settings_updated` has `person_id`, `changed_fields` and `origin`, and
  no setting values.
- `settings_updated` has `changed_fields`, `currency` and `origin`. The
  `set_settings` service and the options flow fire it. `changed_fields` names
  `currency`.

## Rules

- `loan_overdue` fires once for each due date. The library checks at setup and
  each hour. A new due date can fire it again.
- A CSV import fires only `import_completed`. It fires no event for each row.
- A Home Keeper import fires only `data_imported`. It fires no event for each record.
- `game_finished` fires with `reading_changed`, in that order.
- The first copy of a game on the wishlist takes the game off the wishlist. The
  scan, `add_copy` and `got_wishlist_game` fire `copy_added` and then
  `wishlist_removed`.
- Deleting a room, a unit or a shelf with `force: true` fires a `*_removed`
  event for each child and a `copy_moved` event for each copy that moves to no
  shelf.
- An update that changes no field fires no event.
- The library fires no event for its own bookkeeping: the Home Keeper task id of a
  loan.

## Events that the library listens for

| Event | What the library does |
|---|---|
| `home_keeper_task_completed` | If the task is the task of an open loan, the loan is returned. |
| `home_keeper_task_deleted` | If the task is the task of a loan, the loan forgets the task and gets no new one. |
| `home_keeper_register_companions` | The library registers as a Home Keeper companion again. |

The library ignores a Home Keeper event with the origin `home_keeper_games`, because
the library made that change itself.

## Example automation

```yaml
automation:
  - alias: Notify when a loan is overdue
    triggers:
      - trigger: event
        event_type: home_keeper_games_loan_overdue
    actions:
      - action: persistent_notification.create
        data:
          title: "Loan overdue"
          message: "{{ trigger.event.data.title }} was due on {{ trigger.event.data.due }}."
```

A second example sends a message when a person finishes a game:

```yaml
automation:
  - alias: Game finished
    triggers:
      - trigger: event
        event_type: home_keeper_games_game_finished
    actions:
      - action: notify.notify
        data:
          message: "Finished {{ trigger.event.data.title }}."
```
