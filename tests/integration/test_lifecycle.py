"""Docker integration: the library loads next to the real Home Keeper.

The container has the real Home Keeper component (``ci/fetch-home-keeper.sh``)
and a seeded config entry for each integration, so both load at startup.
"""

from __future__ import annotations

from pathlib import Path

import pytest

DOMAIN = "home_keeper_games"
DIST = (
    Path(__file__).resolve().parents[2]
    / "custom_components"
    / DOMAIN
    / "frontend"
    / "dist"
)
HOME_KEEPER = Path(__file__).resolve().parent / ".home_keeper" / "custom_components"
SERVICES = (
    "add_room",
    "add_game",
    "scan_barcode",
    "set_reading",
    "lend_game",
    "borrow_game",
    "import_csv",
    "export_csv",
    "list_games",
    "list_people",
)


def test_both_config_entries_are_loaded(api):
    entries = api.get("/api/config/config_entries/entry").json()
    states = {e["domain"]: e["state"] for e in entries}
    assert states.get("home_keeper") == "loaded", states
    assert states.get(DOMAIN) == "loaded", states


def test_services_registered(api):
    resp = api.get("/api/services")
    assert resp.status_code == 200
    domains = {block["domain"]: block for block in resp.json()}
    assert DOMAIN in domains
    for name in SERVICES:
        assert name in domains[DOMAIN]["services"], name


def test_entities_exist(api):
    ids = {s["entity_id"] for s in api.get("/api/states").json()}
    assert "sensor.home_keeper_games_books" in ids
    assert "sensor.home_keeper_games_loans_overdue" in ids
    assert any(i.startswith("todo.home_keeper_games_") for i in ids), sorted(ids)


def test_get_state_and_the_tab(ws):
    state = ws("home_keeper_games/get_state")
    assert state["success"], state
    result = state["result"]
    assert result["me"]["is_admin"] is True and result["currency"] == "EUR"
    has_tabs = (HOME_KEEPER / "home_keeper" / "panel_tabs.py").exists()
    if not has_tabs:
        pytest.skip("this Home Keeper has no panel_tabs module")
    assert result["home_keeper"] == {"tab": True}
    tabs = ws("home_keeper/get_panel_tabs")
    assert tabs["success"], tabs
    rows = tabs["result"]
    rows = rows["tabs"] if isinstance(rows, dict) else rows
    tab = next(t for t in rows if t["companion"] == DOMAIN)
    assert tab["id"] == "games" and tab["element"] == "home-keeper-games-tab"
    assert tab["module_url"].startswith("/home_keeper_games_static/games-tab.js")
    assert tab["title"] == "Games"


def test_no_repair_issue_with_home_keeper(ws):
    issues = ws("repairs/list_issues")
    assert issues["success"], issues
    ours = [i for i in issues["result"]["issues"] if i["domain"] == DOMAIN]
    if not (HOME_KEEPER / "home_keeper" / "panel_tabs.py").exists():
        assert [i["issue_id"] for i in ours] == ["home_keeper_too_old"]
        return
    assert ours == []


def test_loan_adds_a_home_keeper_task(api):
    game = api.post(
        "/api/services/home_keeper_games/add_game?return_response",
        json={"title": "Integration loan game"},
    ).json()["service_response"]["game"]
    copy = api.post(
        "/api/services/home_keeper_games/add_copy?return_response",
        json={"game_id": game["id"]},
    ).json()["service_response"]["copy"]
    loan = api.post(
        "/api/services/home_keeper_games/lend_game?return_response",
        json={"copy_id": copy["id"], "party": "Zed", "due": "2030-01-01"},
    ).json()["service_response"]["loan"]
    try:
        if not (HOME_KEEPER / "home_keeper" / "panel_tabs.py").exists():
            assert loan["hk_task_id"] is None
            return
        assert loan["hk_task_id"], loan
        tasks = api.post(
            "/api/services/home_keeper/list_tasks?return_response", json={}
        ).json()["service_response"]["tasks"]
        task = next(t for t in tasks if t["id"] == loan["hk_task_id"])
        assert task["name"] == "Get Integration loan game back from Zed"
        assert task["source"] == {"home_keeper_games": {"loan_id": loan["id"]}}
        assert task["managed_by"]["integration"] == DOMAIN
    finally:
        api.post(
            "/api/services/home_keeper_games/delete_game",
            json={"game_id": game["id"]},
        )


@pytest.mark.parametrize("bundle", ["games-tab.js", "games-card.js"])
def test_bundles_served(api, bundle):
    if not (DIST / bundle).exists():
        pytest.skip(f"frontend/dist/{bundle} is not built")
    resp = api.get(f"/home_keeper_games_static/{bundle}")
    assert resp.status_code == 200
    assert len(resp.text) > 100


def test_cover_view_needs_auth(api):
    import requests

    resp = requests.get(
        "http://localhost:8123/api/home_keeper_games/cover/nope", timeout=10
    )
    assert resp.status_code == 401
    assert api.get("/api/home_keeper_games/cover/nope").status_code == 404
