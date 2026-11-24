"""The ``Backlog`` to-do list of each person.

The items are the progress rows with play status ``backlog`` for the person. The
summary is the title and the uid is ``game_id:platform``.

* Completing an item sets the play status to ``completed``, with
  ``completed_at`` today.
* Adding an item by name gives a ``backlog`` row to the game with that title, on
  the platform of its copies, or on ``other`` when it has no single platform. If
  no game has that title, a new game with ``needs_details: true`` is added.
* Deleting an item removes the ``backlog`` row.

Home Assistant lets each user call the ``todo`` services on each list. So a
change must come from the user of the person, from an admin user or from Home
Assistant itself (no user). Other users get ``todo_not_allowed``. While the
person does not share their progress, the list is unavailable and has no items.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.todo import (
    TodoItem,
    TodoItemStatus,
    TodoListEntity,
    TodoListEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LibraryConfigEntry, people
from .const import DOMAIN
from .coordinator import LibraryCoordinator
from .entity import PersonEntity, async_track_people
from .models import DEFAULT_PLATFORM, LibraryError, fold, progress_platform
from .projections import backlog
from .services import service_error


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LibraryConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the to-do list of each person."""
    coordinator = entry.runtime_data

    def _build(person: dict[str, Any]) -> list[TodoListEntity]:
        return [BacklogList(coordinator, person)]

    entry.async_on_unload(
        async_track_people(hass, coordinator, _build, async_add_entities)
    )


def _split_uid(uid: str) -> tuple[str, str]:
    """``(game_id, platform)`` from an item uid."""
    game_id, _, platform = uid.partition(":")
    return game_id, platform


class BacklogList(PersonEntity, TodoListEntity):
    """The games in the backlog of a person."""

    _attr_translation_key = "backlog"
    _attr_icon = "mdi:gamepad-variant"
    _attr_supported_features = (
        TodoListEntityFeature.CREATE_TODO_ITEM
        | TodoListEntityFeature.UPDATE_TODO_ITEM
        | TodoListEntityFeature.DELETE_TODO_ITEM
    )

    def __init__(self, coordinator: LibraryCoordinator, person: dict[str, Any]) -> None:
        super().__init__(coordinator, person, "backlog")

    async def _check_caller(self) -> None:
        """Refuse a change from a user who is not the person or an admin.

        The entity service call of Home Assistant sets the context of the call
        on the entity before it calls the item method.
        """
        context = self._context
        actor = await people.actor_for_user(
            self.hass, context.user_id if context else None
        )
        if actor.is_admin or actor.person_id == self.person_id:
            return
        found = people.person(self.hass, self.person_id)
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="todo_not_allowed",
            translation_placeholders={
                "person": str(found["name"] if found else self.person_id)
            },
        )

    @property
    def todo_items(self) -> list[TodoItem]:
        if not self.available:
            return []
        return [
            TodoItem(
                summary=str(game.get("title") or ""),
                uid=f"{game['id']}:{platform}",
                status=TodoItemStatus.NEEDS_ACTION,
            )
            for game, platform in backlog(self.state_doc, self.person_id)
        ]

    async def async_create_todo_item(self, item: TodoItem) -> None:
        """Give the game with this title a ``backlog`` row, or add a new game."""
        await self._check_caller()
        summary = (item.summary or "").strip()
        if not summary:
            return
        store = self.coordinator.store
        wanted = fold(summary)
        match = next(
            (
                game
                for game in store.state["games"].values()
                if wanted and wanted == fold(game.get("title"))
            ),
            None,
        )
        try:
            if match is None:
                match, _ = await store.add_game(
                    {"title": summary, "needs_details": True}
                )
            try:
                platform = progress_platform(store.state, match["id"], None)
            except LibraryError:
                platform = DEFAULT_PLATFORM
            await store.set_progress(
                match["id"],
                self.person_id,
                {"play_status": "backlog", "platform": platform},
            )
        except LibraryError as err:
            raise service_error(err) from err

    async def async_update_todo_item(self, item: TodoItem) -> None:
        """A completed item sets the play status to ``completed``."""
        await self._check_caller()
        if item.uid is None or item.status != TodoItemStatus.COMPLETED:
            return
        try:
            game_id, platform = _split_uid(item.uid)
            await self.coordinator.store.set_progress(
                game_id,
                self.person_id,
                {"play_status": "completed", "platform": platform},
            )
        except LibraryError as err:
            raise service_error(err) from err

    async def async_delete_todo_items(self, uids: list[str]) -> None:
        """Remove the ``backlog`` row of each item."""
        await self._check_caller()
        store = self.coordinator.store
        for uid in uids:
            game_id, platform = _split_uid(uid)
            row = store.progress_row(self.person_id, game_id, platform)
            if row is None or row["play_status"] != "backlog":
                continue
            try:
                await store.set_progress(
                    game_id,
                    self.person_id,
                    {"play_status": "none", "platform": platform},
                )
            except LibraryError as err:
                raise service_error(err) from err
