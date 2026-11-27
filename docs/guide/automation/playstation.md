# PlayStation

The library logs a play session for each game that a PlayStation console plays. The
minutes of the session go on the play time of that game.

## Requirements

- The [PlayStation Network](https://www.home-assistant.io/integrations/playstation_network/)
  integration, set up with your account. It adds a media player for each console, such as
  `media_player.playstation_5`.
- Optional: the [IGDB keys](../start/installation.md#igdb-keys), so that a new game gets
  its details and cover.

## Add a console

1. Go to **Settings → Devices & services → Home Keeper Games** and select **Configure**.
2. Select **Submit** on the first page. The second page is **Consoles**.
3. In **New console**, select the media player of the console. Select the person who
   plays on it and the platform.
4. Select **Submit**.

To remove a console, clear it in **Consoles** on the same page. Each console is for 1
person. If 2 people play on 1 console, the sessions go to the person of the console.

## What the library records

- **A known game.** The library finds the game by its PlayStation title ID, or by its
  title. A game that you renamed with **Change IGDB game** still matches.
- **A new game.** The library adds the game and a digital copy on the platform of the
  console. With the IGDB keys, the game gets its details when IGDB has a game with the
  same title. Else the game shows **This game needs details** in the tab: select
  **Change IGDB game** to correct it.
- **The progress.** A new game or a game in the backlog becomes **Playing**. The last
  played date and the play time change.
- **A short session.** A session of less than 1 minute is not kept.

The PlayStation Network integration reads PSN at an interval, so the start and the end of
a session can be a short time late.

- **No PSN data for a time.** The session continues. If the game stopped in that time,
  the end of the session is the start of that time.
- **Restart of Home Assistant.** The session ends at the stop, and a new session starts
  after the restart.

Use `home_keeper_games.list_sessions` to see the sessions, and `delete_session` to
remove a wrong one ([Services and events](services.md#play-sessions)). The events
`home_keeper_games_session_started` and `home_keeper_games_session_logged` fire when a
session starts and ends.
