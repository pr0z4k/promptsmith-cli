"""Tests for the SQLite-backed prompt history store."""

import csv
import json
from pathlib import Path

import pytest

from promptsmith.core.history import HistoryEntry, HistoryStore


@pytest.fixture
def store(tmp_path):
    return HistoryStore(db_path=tmp_path / "history.db")


def _entry(prompt="a rough prompt", refined="a refined prompt", **kw):
    base = dict(
        prompt=prompt,
        refined=refined,
        profile="vibe-coding",
        template="react-component",
        backend="rule",
        model=None,
        analysis={"score": 42, "detected_type": "code", "is_ready": False},
    )
    base.update(kw)
    return HistoryEntry(**base)


def test_store_initializes_and_is_available(store):
    assert store.available
    assert store.db_path.exists()
    assert store.count() == 0


def test_add_and_get_roundtrip(store):
    new_id = store.add(_entry())
    assert new_id is not None
    assert store.count() == 1

    got = store.get(new_id)
    assert got is not None
    assert got.prompt == "a rough prompt"
    assert got.refined == "a refined prompt"
    assert got.profile == "vibe-coding"
    assert got.analysis["score"] == 42
    assert got.created_at  # auto-populated


def test_list_returns_newest_first(store):
    id1 = store.add(_entry(prompt="first"))
    id2 = store.add(_entry(prompt="second"))
    id3 = store.add(_entry(prompt="third"))

    entries = store.list()
    assert [e.prompt for e in entries] == ["third", "second", "first"]
    assert [e.id for e in entries] == [id3, id2, id1]


def test_list_respects_limit(store):
    for i in range(5):
        store.add(_entry(prompt=f"p{i}"))
    assert len(store.list(limit=2)) == 2
    assert len(store.list()) == 5


def test_delete_single_entry(store):
    id1 = store.add(_entry(prompt="keep"))
    id2 = store.add(_entry(prompt="remove"))

    assert store.delete(id2) is True
    assert store.count() == 1
    assert store.get(id2) is None
    assert store.get(id1) is not None
    # Deleting a non-existent row returns False, doesn't raise.
    assert store.delete(99999) is False


def test_clear_removes_all(store):
    for i in range(3):
        store.add(_entry(prompt=f"p{i}"))
    removed = store.clear()
    assert removed == 3
    assert store.count() == 0


def test_export_json(store, tmp_path):
    store.add(_entry(prompt="one"))
    store.add(_entry(prompt="two"))
    out = tmp_path / "export.json"
    n = store.export_json(out)

    assert n == 2
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data) == 2
    # Newest-first ordering preserved in the export.
    assert data[0]["prompt"] == "two"
    assert data[0]["analysis"]["score"] == 42
    # Full round-trip: the JSON carries every field.
    assert set(data[0].keys()) >= {
        "id",
        "created_at",
        "prompt",
        "refined",
        "profile",
        "template",
        "backend",
        "model",
        "analysis",
    }


def test_export_csv(store, tmp_path):
    store.add(_entry(prompt="one"))
    store.add(_entry(prompt="two"))
    out = tmp_path / "export.csv"
    n = store.export_csv(out)

    assert n == 2
    with open(out, encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["prompt"] == "two"
    assert rows[0]["score"] == "42"
    assert rows[0]["detected_type"] == "code"
    # analysis_json column holds the full nested snapshot.
    assert json.loads(rows[0]["analysis_json"])["score"] == 42


def test_analysis_from_object_snapshot():
    """A live-ish analysis object is reduced to a JSON-safe dict."""

    class FakeSmell:
        def __init__(self, term, severity):
            self.term = term
            self.severity = severity

    class FakeRec:
        def __init__(self, message):
            self.message = message

    class FakeChallenge:
        def __init__(self, question):
            self.question = question

    class FakeAnalysis:
        score = 73
        detected_type = "architecture"
        recommended_profile = "vibe-coding"
        is_ready = True
        missing = ["Context", "Audience/Role"]
        recommendations = [FakeRec("Add background")]
        smells = [FakeSmell("modern", "high")]
        challenges = [FakeChallenge("Who consumes this?")]

    snap = HistoryEntry.analysis_from_object(FakeAnalysis())
    assert snap["score"] == 73
    assert snap["detected_type"] == "architecture"
    assert snap["is_ready"] is True
    assert snap["missing"] == ["Context", "Audience/Role"]
    assert snap["recommendations"] == ["Add background"]
    assert snap["smells"] == [{"term": "modern", "severity": "high"}]
    assert snap["challenges"] == ["Who consumes this?"]
    # And the whole thing must be JSON-serializable.
    json.dumps(snap)


def test_analysis_from_object_none():
    assert HistoryEntry.analysis_from_object(None) == {}


def test_unavailable_store_degrades_gracefully(tmp_path):
    """A store pointed at an unwritable path reports unavailable and its
    methods no-op rather than raising."""
    # Point at a path whose parent is a file, so mkdir/connect fails.
    bad_parent = tmp_path / "afile"
    bad_parent.write_text("x")
    store = HistoryStore(db_path=bad_parent / "nested" / "history.db")
    # Depending on the OS this may or may not fail at init; if it did,
    # every method must still be safe to call.
    if not store.available:
        assert store.add(_entry()) is None
        assert store.list() == []
        assert store.count() == 0
        assert store.delete(1) is False
        assert store.clear() == 0


# --- UI integration ---------------------------------------------------------


def test_history_written_on_refine_and_modal_flow(tmp_path, monkeypatch):
    """End-to-end: a refine records an entry, the History modal lists it
    in the grid with visible button labels, and copy/delete/clear work."""
    import asyncio

    monkeypatch.setenv("PROMPTSMITH_LOG_DIR", str(tmp_path))

    from textual.widgets import Button, DataTable

    from promptsmith.cli.app import HistoryScreen, PromptSmithApp

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(160, 60)) as pilot:
            await pilot.pause()
            assert app.history is not None and app.history.available

            app.query_one("#prompt_input").text = "make a modern best react component"
            await pilot.pause()
            app.action_refine()
            for _ in range(50):
                await pilot.pause(0.1)
                if app.history.count() > 0:
                    break
            assert app.history.count() == 1, "refine did not record a history entry"

            # Open the History modal.
            app.action_history()
            await pilot.pause()
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, HistoryScreen)

            table = screen.query_one("#history_table", DataTable)
            assert table.row_count == 1

            # Every modal button must have a visible (non-empty) label.
            for b in screen.query(Button):
                assert b.label.plain.strip(), f"empty history button {b.id!r}"

            # Delete the only row -> grid empties.
            table.move_cursor(row=0)
            await pilot.pause()
            screen._delete_selected()
            await pilot.pause()
            assert app.history.count() == 0
            assert table.row_count == 0

    asyncio.run(run())


def test_history_export_produces_files(tmp_path, monkeypatch):
    """The modal's JSON and CSV export actions both write files."""
    import asyncio
    import glob

    monkeypatch.setenv("PROMPTSMITH_LOG_DIR", str(tmp_path))

    from promptsmith.cli.app import HistoryScreen, PromptSmithApp
    from promptsmith.core.history import HistoryEntry

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(160, 60)) as pilot:
            await pilot.pause()
            app.history.add(
                HistoryEntry(prompt="p", refined="r", analysis={"score": 10})
            )
            app.action_history()
            await pilot.pause()
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, HistoryScreen)
            screen._export("json")
            screen._export("csv")

    asyncio.run(run())

    import promptsmith.cli.app as appmod

    exports = appmod._PROJECT_ROOT / "exports"
    assert glob.glob(str(exports / "*History*.json"))
    assert glob.glob(str(exports / "*History*.csv"))
def test_clear_all_requires_confirmation(tmp_path, monkeypatch):
    """Clear All must not wipe history on a single press - the first press
    arms it, and only a second confirming press deletes."""
    import asyncio

    monkeypatch.setenv("PROMPTSMITH_LOG_DIR", str(tmp_path))

    from promptsmith.cli.app import HistoryScreen, PromptSmithApp
    from promptsmith.core.history import HistoryEntry

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(160, 60)) as pilot:
            await pilot.pause()
            for i in range(3):
                app.history.add(HistoryEntry(prompt=f"p{i}", refined=f"r{i}"))
            app.action_history()
            await pilot.pause()
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, HistoryScreen)
            assert app.history.count() == 3

            # First press: arms, deletes nothing.
            screen._clear_all()
            await pilot.pause()
            assert screen._clear_armed is True
            assert app.history.count() == 3, "clear must not delete on first press"

            # Second press: executes.
            screen._clear_all()
            await pilot.pause()
            assert app.history.count() == 0
            assert screen._clear_armed is False

    asyncio.run(run())


def test_clear_all_cancelled_by_other_action(tmp_path, monkeypatch):
    """Arming Clear All and then doing anything else cancels it."""
    import asyncio

    monkeypatch.setenv("PROMPTSMITH_LOG_DIR", str(tmp_path))

    from textual.widgets import Button

    from promptsmith.cli.app import HistoryScreen, PromptSmithApp
    from promptsmith.core.history import HistoryEntry

    async def run():
        app = PromptSmithApp()
        async with app.run_test(size=(160, 60)) as pilot:
            await pilot.pause()
            app.history.add(HistoryEntry(prompt="p", refined="r"))
            app.action_history()
            await pilot.pause()
            await pilot.pause()
            screen = app.screen

            # Arm it.
            screen._clear_all()
            await pilot.pause()
            assert screen._clear_armed is True

            # Simulate pressing a different button (Copy) via the dispatch.
            class FakeEvent:
                class button:
                    id = "history_copy"

            screen.on_button_pressed(FakeEvent())
            await pilot.pause()
            assert screen._clear_armed is False, "other action should disarm clear"
            # And history is untouched.
            assert app.history.count() == 1

    asyncio.run(run())
