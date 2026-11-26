"""Unit tests: the Telegram blueprint matches the services and the models.

The component tier runs the blueprint. These tests read its YAML, so a renamed
service, field, platform or format fails here first, also on a Home Assistant
that is too old for the component test.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import ex.models as m
import yaml

ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT = ROOT / "blueprints/automation/home_keeper_games/telegram_add_game.yaml"
SERVICES = ROOT / "custom_components/home_keeper_games/services.yaml"


class _Input(str):
    """The name of an `!input` tag."""


class _Loader(yaml.SafeLoader):
    pass


_Loader.add_constructor("!input", lambda loader, node: _Input(node.value))


def _blueprint() -> dict[str, Any]:
    return yaml.load(BLUEPRINT.read_text(encoding="utf-8"), Loader=_Loader)


def _walk(node: Any):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


def _options(name: str) -> list[str]:
    selector = _blueprint()["blueprint"]["input"][name]["selector"]["select"]
    return [option["value"] for option in selector["options"]]


def test_each_library_action_and_field_exists() -> None:
    services = yaml.safe_load(SERVICES.read_text(encoding="utf-8"))
    found = []
    for step in _walk(_blueprint()["actions"]):
        action = step.get("action", "")
        if not action.startswith("home_keeper_games."):
            continue
        name = action.split(".", 1)[1]
        assert name in services, name
        fields = set(services[name].get("fields") or {})
        assert set(step.get("data", {})) <= fields, (name, step["data"])
        found.append(name)
    assert sorted(set(found)) == ["add_copy", "add_game", "delete_copy", "delete_game"]


def test_each_input_tag_is_declared() -> None:
    document = _blueprint()
    declared = set(document["blueprint"]["input"])
    used = {
        value
        for node in _walk(document)
        for value in node.values()
        if isinstance(value, _Input)
    }
    assert used == declared


def test_the_selects_match_the_models() -> None:
    assert _options("default_platform") == list(m.PLATFORMS)
    assert _options("copy_format") == list(m.FORMATS)


def test_the_aliases_and_labels_name_only_library_platforms() -> None:
    document = _blueprint()
    assert set(document["variables"]["labels"]) == set(m.PLATFORMS)
    [add] = [
        option["sequence"]
        for node in _walk(document["actions"])
        for option in node.get("choose", [])
    ][:1]
    aliases = add[0]["variables"]["aliases"]
    assert set(aliases.values()) <= set(m.PLATFORMS)
    assert all(key == key.lower() for key in aliases)
