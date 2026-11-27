# Installation

Home Keeper Games is a custom integration in the [HACS](https://hacs.xyz/) default list.
It requires Home Assistant 2025.7 or later, and Home Keeper.

## Install Home Keeper first

1. Install Home Keeper with HACS, as its
   [installation steps](https://github.com/prestomation/ha-home-keeper#installation) say.
2. Restart Home Assistant.
3. Add the Home Keeper integration in **Settings → Devices & services → Add
   integration**.

The Games tab needs Home Keeper version 0.30.0 or later.

## Install the library

1. In HACS, search for **Home Keeper Games**, or
   [open it in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=antoiba86&repository=ha-home-keeper-games&category=integration).
2. Download **Home Keeper Games** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration**, and select **Home Keeper
   Games**.
4. Enter the currency of the prices and values of your games, such as `EUR` or `USD`.
   The default is the currency of Home Assistant.
5. Optional: enter a **Twitch client ID** and **Twitch client secret** to get game
   details from IGDB ([IGDB keys](#igdb-keys)).
6. Select **Submit**.

The Home Keeper panel then has a **Library** tab. Open it from the Home Keeper entry in
the sidebar.

To change the currency or the IGDB keys later, open **Settings → Devices & services →
Home Keeper Games** and select **Configure**.

## IGDB keys

IGDB is the game database of Twitch. With its keys, the library finds a game by title
and adds it with its summary, genres, release date, franchise and cover.

1. Sign in at [dev.twitch.tv/console](https://dev.twitch.tv/console). Twitch asks for
   two-factor authentication.
2. Select **Register Your Application**. Enter a name, the OAuth redirect URL
   `http://localhost`, and the category **Application Integration**.
3. Open the application. Copy the **Client ID**, then select **New Secret** and copy the
   secret.
4. Enter both in the setup step or in **Configure**.

The library checks the keys before it saves them. In **Configure**, keep the secret
empty to keep the stored secret, or clear the client ID to remove both keys.

## Setup messages

If Home Keeper is not ready, the setup stops with 1 of these messages:

| Message | What to do |
|---|---|
| Home Keeper Games requires Home Keeper. | Install Home Keeper from HACS, restart Home Assistant, then add Home Keeper Games again. |
| Add the Home Keeper integration first. | Add the Home Keeper integration, then add Home Keeper Games again. |
| Update Home Keeper to version 0.30.0 or later. | Update Home Keeper in HACS, restart Home Assistant, then add Home Keeper Games again. |

## Repair issues

If Home Keeper goes away after the setup, the library keeps its data. The card, the
entities and the services still work. **Settings → Repairs** shows 1 of these issues:

- **Home Keeper is not installed.** Install Home Keeper from HACS and restart Home
  Assistant.
- **Home Keeper is not set up.** Add or enable the Home Keeper integration.
- **Home Keeper is too old.** Update Home Keeper.

While the issue shows, the Games tab and the loan tasks are off. When Home Keeper is
ready again, the issue goes away. The tab and the tasks then come back with no restart.

## Data

The library is 1 JSON document in `.storage/home_keeper_games`. The covers are JPEG
files in `.storage/home_keeper_games_covers/`. Both are in each Home Assistant backup.
