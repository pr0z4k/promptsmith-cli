"""Security and robustness tests for the local history store."""

import os
import sqlite3
from pathlib import Path

import pytest

from promptsmith.core.history import (
    SQLITE_BUSY_TIMEOUT_MS,
    HistoryEntry,
    HistoryStore,
)


def test_history_uses_wal_and_busy_timeout(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    assert store.available

    with store._connect() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == SQLITE_BUSY_TIMEOUT_MS


def test_corrupt_database_is_quarantined_and_recreated(tmp_path):
    db_path = tmp_path / "history.db"
    db_path.write_bytes(b"this is not sqlite")

    store = HistoryStore(db_path)

    assert store.available
    assert store.count() == 0
    quarantined = list(tmp_path.glob("history.db.corrupt-*"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes() == b"this is not sqlite"

    with sqlite3.connect(db_path) as conn:
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"


@pytest.mark.skipif(os.name == "nt", reason="symlink creation is not reliably available")
def test_symlinked_database_is_rejected(tmp_path):
    target = tmp_path / "target.db"
    target.write_bytes(b"")
    link = tmp_path / "history.db"
    link.symlink_to(target)

    store = HistoryStore(link)

    assert not store.available
    assert target.read_bytes() == b""


@pytest.mark.skipif(os.name == "nt", reason="symlink creation is not reliably available")
def test_export_refuses_symlink_target(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    store.add(HistoryEntry(prompt="private prompt", refined="private result"))

    target = tmp_path / "elsewhere.json"
    target.write_text("do not replace", encoding="utf-8")
    link = tmp_path / "history.json"
    link.symlink_to(target)

    with pytest.raises(OSError, match="symlink"):
        store.export_json(link)

    assert target.read_text(encoding="utf-8") == "do not replace"


def test_failed_export_does_not_replace_existing_file(tmp_path, monkeypatch):
    store = HistoryStore(tmp_path / "history.db")
    store.add(HistoryEntry(prompt="private prompt", refined="private result"))
    destination = tmp_path / "history.json"
    destination.write_text("previous export", encoding="utf-8")

    def fail_replace(source: Path, target: Path) -> None:
        raise OSError("simulated promotion failure")

    monkeypatch.setattr("promptsmith.core.history.os.replace", fail_replace)

    with pytest.raises(OSError, match="promotion failure"):
        store.export_json(destination)

    assert destination.read_text(encoding="utf-8") == "previous export"
    assert not list(tmp_path.glob(".history.json.*.tmp"))


def test_negative_pagination_is_rejected(tmp_path):
    store = HistoryStore(tmp_path / "history.db")

    with pytest.raises(ValueError, match="limit"):
        store.list(limit=-1)
    with pytest.raises(ValueError, match="offset"):
        store.list(offset=-1)
