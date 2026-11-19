# Home Keeper Games

[![GitHub Downloads][downloads-shield]][releases]
[![GitHub Release][release-shield]][releases]
[![GitHub Release Date][release-date-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![hacs][hacs-shield]][hacs]
![Project Maintenance][maintenance-shield]
[![HACS Validation][hacs-validation-shield]][hacs-validation]
[![HA Version][ha-version-shield]][ha-version]
[![Docs][docs-shield]][docs]

**Home Keeper Games requires [Home Keeper](https://github.com/prestomation/ha-home-keeper).
Install and set up Home Keeper first.**

Home Keeper Games is a Home Assistant integration for the video games of a household. It
records the physical and digital games of each console, where each physical copy is in
the home, the play status of each person, the loans and a wishlist. Admins manage it in
a **Games** tab of the Home Keeper panel. Every user gets a dashboard card, sensors and a
wishlist to-do list.

This project is derived from
[Home Keeper Library](https://github.com/prestomation/ha-home-keeper-library) by Preston
Tamkin. See [Origin and credits](#origin-and-credits).

> [!WARNING]
> **Work in progress.** There is no release yet. The code is still the Home Keeper
> Library code, and the change to games is in progress. Do not install it yet.

## Features

The first release will have these features:

- Find the shelf or the TV cabinet of each physical game.
- Keep the copies of each game: platform (PS5, PS4, Switch, Switch 2 and more),
  physical or digital, edition, region and condition.
- Get the details and the cover of a game from [IGDB](https://www.igdb.com).
- Keep a play status, a rating and a review for each person.
- Record the play time from the PlayStation Network and Nintendo integrations of Home
  Assistant.
- Lend and borrow games, with a Home Keeper task on each due date.
- Send the wishlist games to buy to a to-do list of the person.

## Install

1. Install and set up [Home Keeper](https://github.com/prestomation/ha-home-keeper#installation).
2. In [HACS](https://hacs.xyz/), add this repository as a custom repository of the
   type **Integration**, or
   [open it in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=antoiba86&repository=ha-home-keeper-games&category=integration).
3. Download **Home Keeper Games** and restart Home Assistant.
4. Add the integration in **Settings → Devices & services → Add integration → Home
   Keeper Games**.

## Documentation

- [User Guide](https://antoiba86.github.io/ha-home-keeper-games/docs/intro): every
  feature, with screenshots. The pages are written in [`docs/guide/`](docs/guide).
- [Developer Guide](https://antoiba86.github.io/ha-home-keeper-games/developer/integrating):
  the services, the events and the API reference.
- [Release notes](https://antoiba86.github.io/ha-home-keeper-games/docs/release-notes).

## Development

- Backend: `custom_components/home_keeper_games/`. The pure core imports no Home
  Assistant code. The folder gets the name `home_keeper_games` in the rename step.
- Panel frontend: `custom_components/home_keeper_games/frontend/`, built with
  TypeScript and Rollup.
- Tests: `pytest` in `tests/unit`, `tests/component` and `tests/integration`,
  Playwright in `tests/e2e`, and vitest.

See [AGENTS.md](AGENTS.md) for workflow, [RELEASE.md](RELEASE.md) for releases and
[Developing](docs/DEVELOPING.md) for the test commands and the CI guardrails.

## Origin and credits

This project is derived from
[Home Keeper Library](https://github.com/prestomation/ha-home-keeper-library) by
Preston Tamkin, version 0.4.0, under the MIT license. It is a separate project. The
original author does not maintain, review or endorse it. Report problems with this
project here, not to the original project.

## License

MIT. See [LICENSE](LICENSE). The license keeps the copyright notice of the original
author, as the MIT license requires.

[releases]: https://github.com/antoiba86/ha-home-keeper-games/releases
[release-shield]: https://img.shields.io/github/release/antoiba86/ha-home-keeper-games.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/antoiba86/ha-home-keeper-games.svg?style=for-the-badge
[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge
[hacs]: https://github.com/hacs/integration
[hacs-validation-shield]: https://github.com/antoiba86/ha-home-keeper-games/actions/workflows/hacs.yml/badge.svg
[hacs-validation]: https://github.com/antoiba86/ha-home-keeper-games/actions/workflows/hacs.yml
[downloads-shield]: https://img.shields.io/github/downloads/antoiba86/ha-home-keeper-games/total.svg?style=for-the-badge
[release-date-shield]: https://img.shields.io/github/release-date/antoiba86/ha-home-keeper-games?style=for-the-badge
[commits-shield]: https://img.shields.io/github/last-commit/antoiba86/ha-home-keeper-games?style=for-the-badge
[commits]: https://github.com/antoiba86/ha-home-keeper-games/commits/main
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40antoiba86-blue.svg?style=for-the-badge
[ha-version-shield]: https://img.shields.io/badge/Home%20Assistant-2025.7%2B-blue.svg?style=for-the-badge
[ha-version]: https://www.home-assistant.io/
[docs-shield]: https://img.shields.io/badge/docs-website-03a9f4.svg?style=for-the-badge
[docs]: https://antoiba86.github.io/ha-home-keeper-games/
