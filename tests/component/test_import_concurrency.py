"""Component test: a change made while an import runs survives the import."""

from __future__ import annotations

import threading

from custom_components.home_keeper_games import csv_io

BOB = "p_bob"


async def test_import_keeps_changes_made_while_it_runs(
    hass, setup_entry, call, monkeypatch
) -> None:
    store = setup_entry.runtime_data.store
    dune = (
        await call(
            "add_game",
            {"title": "Dune", "authors": ["Frank Herbert"]},
        )
    )["game"]
    hyperion = (await call("add_game", {"title": "Hyperion"}))["game"]
    # The import plan waits in the executor until the test lets it go on.
    started, release = threading.Event(), threading.Event()
    real = csv_io.apply_import

    def slow_plan(*args, **kwargs):
        started.set()
        assert release.wait(10)
        return real(*args, **kwargs)

    monkeypatch.setattr(csv_io, "apply_import", slow_plan)
    csv_text = (
        "title,authors,rating,status,tags\n"
        "Dune,Frank Herbert,4,read,classics\n"
        "Emma,Jane Austen,,reading,\n"
    )
    task = hass.async_create_task(
        call(
            "import_csv",
            {"content": csv_text, "person_id": BOB},
        )
    )
    assert await hass.async_add_executor_job(started.wait, 10)
    # Changes while the import runs.
    room = (await call("add_room", {"name": "Attic"}))["room"]
    await call(
        "set_reading",
        {"game_id": hyperion["id"], "person_id": BOB, "status": "reading"},
    )
    await call("update_game", {"game_id": dune["id"], "shared_notes": "Signed."})
    release.set()
    reply = await task
    assert reply["counts"]["errors"] == 0 and reply["counts"]["title_match"] == 1
    state = store.state
    # The concurrent changes survive.
    assert state["rooms"][room["id"]]["name"] == "Attic"
    assert state["reading"][BOB][hyperion["id"]]["status"] == "reading"
    assert state["games"][dune["id"]]["shared_notes"] == "Signed."
    # The import is written too.
    assert state["games"][dune["id"]]["tags"] == ["classics"]
    assert state["reading"][BOB][dune["id"]]["status"] == "read"
    emma = next(b for b in state["games"].values() if b["title"] == "Emma")
    assert state["reading"][BOB][emma["id"]]["status"] == "reading"
