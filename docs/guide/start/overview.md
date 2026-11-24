# Home Keeper Games

Home Keeper Games is a Home Assistant integration for the books of a household. It
records where each book is, who plays it on which platform, who borrowed it and what to buy next.

**Home Keeper Games requires Home Keeper.** Install and set up
[Home Keeper](https://github.com/prestomation/ha-home-keeper) first. The library adds a
**Library** tab to the Home Keeper panel, and puts the return date of each loan in Home
Keeper as a task.

![The book list of the Library tab in Home Keeper](../../images/games-desktop.png)

## What the library records

| Name | What it is |
|---|---|
| Room | A room of the home. It can link to a Home Assistant area. |
| Bookcase | A piece of furniture in a room. It holds shelves. |
| Shelf | 1 shelf of a bookcase. |
| Book | A title, with its franchise, genres, release date, cover and notes. |
| Copy | 1 book that the household owns, with a platform, a format and the barcode of its case. A physical copy is on a shelf. A book can have 0, 1 or more copies. |
| Play progress | Backlog, Playing, Completed or Abandoned, with a rating and the play time, for 1 person on 1 platform. |
| Loan | A copy that the household lent out, or a book that a person borrowed. |
| Wishlist | The books that a person wants to get. |

A book with no copy is valid. Examples are a borrowed game in the play history of a
person and a game on the wishlist.

## Features

- [Work in progress](work-in-progress.md): what works now, while the change to games goes
  on.
- [Dashboard card](../views/dashboard-card.md): the play progress of a person on a dashboard.
- [People and privacy](people-and-privacy.md): what each user can read and change.
- [Services and events](../automation/services.md): automations and other integrations.

## Admins and users

An admin manages the library in the **Library** tab of the Home Keeper panel. Every user
can set the play progress of their own person on the dashboard card. Every user can use
the entities of the library too.
