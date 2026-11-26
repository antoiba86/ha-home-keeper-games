# Telegram

With the Telegram blueprint, a command to your Telegram bot, such as
`/juego Hades switch`, adds a game. The game gets its details and cover from IGDB. Its
copy has the platform of your message.

## Requirements

- Home Assistant 2026.3 or later.
- The [Telegram bot](https://www.home-assistant.io/integrations/telegram_bot/)
  integration, set up and able to send messages to your chat.
- The [IGDB keys](../start/installation.md#igdb-keys), for the details and the cover.
  Without them, the blueprint adds the title only.

## Import the blueprint

1. Open
   [Import blueprint](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fantoiba86%2Fha-home-keeper-games%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fhome_keeper_games%2Ftelegram_add_game.yaml)
   and select **Preview** and **Import**.
2. Go to **Settings → Automations & scenes → Blueprints** and select **Home Keeper
   Games - add a game from Telegram**.
3. Fill in the inputs and save the automation.

| Input | Default | What it does |
| --- | --- | --- |
| Command | `/juego` | The command that adds a game. |
| Allowed chats | empty | The chat IDs that can add games. Empty allows each chat of the bot. |
| Default platform | Other | The platform when the message has no platform. |
| Format | Physical | The format of the new copy. |
| Shelf | empty | The shelf ID of a physical copy. A digital copy has no shelf. |
| Home Assistant URL | empty | Your `https://` URL. The Edit button needs it. |

Allow only the chats of people who can manage the library. The bot adds and deletes
games for each allowed chat.

To find a shelf ID, call `home_keeper_games.list_locations` in **Developer tools →
Actions**. The reply has the ID of each shelf.

## Add a game

Send the command, the title and, at the end, the platform:

```text
/juego Hades switch
/juego Astro Bot ps5
/juego The Legend of Zelda Echoes of Wisdom switch 2
/juego Celeste
```

These words at the end are a platform. Upper-case and lower-case letters are the same.

| Words | Platform |
| --- | --- |
| `ps5`, `ps4`, `ps3` | PS5, PS4, PS3 |
| `switch 2`, `switch2`, `ns2` | Switch 2 |
| `switch` | Switch |
| `xbox`, `xbox series`, `xsx` | Xbox Series |
| `xbox one` | Xbox One |
| `pc`, `steam` | PC |
| `other` | Other |

The blueprint uses the IGDB game only if its title is the same as your title, on that
platform. Else it adds your title, and the game shows **This game needs details** in the
tab. If the game is already in the library, the blueprint adds only a new copy.

## Reply

The bot replies with the title and the platform:

```text
Added: Hades (Switch)
```

- **Undo** deletes the new game. For a game that was already in the library, it deletes
  only the new copy.
- **Edit** opens the game in the Games tab. There, select **Change IGDB game** to
  correct a wrong match ([IGDB game](../start/work-in-progress.md#igdb-game)).
