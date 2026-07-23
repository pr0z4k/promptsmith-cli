"""Local prompt history, backed by SQLite.

Every successful refine is recorded here: the original prompt, a compact
snapshot of the analyzer's findings, and the refined output. The store is
a single SQLite file under the user data directory, so it survives
reinstalls and (in a portable build) travels next to the executable.

SQLite is a deliberate choice over an analytical engine like DuckDB: this
is a transactional insert/list/delete workload, not aggregation over large
datasets, and sqlite3 ships in the Python standard library - no third-party
dependency, in keeping with the project's "local only, zero commercial
dependencies" stance.

The store never raises into the UI for routine failures: history is a
convenience, and a locked or unwritable database must not break the
refine flow. Methods log and degrade (return empty / False) instead.
"""

import csv
import io
import json
import logging
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from promptsmith.utils.path_utils import get_user_data_dir

logger = logging.getLogger(__name__)

#: Schema version, stored in a metadata table so a future migration can
#: detect and upgrade an older file rather than guessing from columns.
SCHEMA_VERSION = 1

DB_FILENAME = "history.db"


@dataclass
class HistoryEntry:
    """One recorded refine. `analysis` is a JSON-serializable dict snapshot
    of the analyzer output at refine time (not the live object), so old
    rows stay readable even if the analyzer's internals change later."""

    prompt: str
    refined: str
    profile: str = "None"
    template: Optional[str] = None
    backend: Optional[str] = None
    model: Optional[str] = None
    analysis: dict = field(default_factory=dict)
    created_at: str = ""
    id: Optional[int] = None

    @staticmethod
    def analysis_from_object(analysis: Any) -> dict:
        """Build the stored analysis snapshot from a PromptAnalysis.

        Kept defensive: anything missing or oddly shaped degrades to a
        partial dict rather than blowing up the refine that triggered it.
        """
        if analysis is None:
            return {}
        snap: dict = {}
        try:
            snap["score"] = getattr(analysis, "score", None)
            snap["detected_type"] = getattr(analysis, "detected_type", None)
            snap["recommended_profile"] = getattr(analysis, "recommended_profile", None)
            snap["is_ready"] = getattr(analysis, "is_ready", None)
            snap["missing"] = list(getattr(analysis, "missing", []) or [])
            recs = getattr(analysis, "recommendations", []) or []
            snap["recommendations"] = [
                getattr(r, "message", getattr(r, "text", str(r))) for r in recs
            ]
            smells = getattr(analysis, "smells", []) or []
            snap["smells"] = [
                {
                    "term": getattr(s, "term", str(s)),
                    "severity": getattr(s, "severity", ""),
                }
                for s in smells
            ]
            challenges = getattr(analysis, "challenges", []) or []
            snap["challenges"] = [
                getattr(c, "question", getattr(c, "text", str(c))) for c in challenges
            ]
        except Exception as exc:  # pragma: no cover - defensive only
            logger.debug(f"Partial analysis snapshot ({exc})")
        return snap


class HistoryStore:
    """SQLite-backed CRUD for prompt history.

    A thin, synchronous wrapper - SQLite calls here are sub-millisecond
    for the row counts a single user generates, so there's no need to push
    them off the UI thread the way an LLM refine is.
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            db_path = get_user_data_dir() / DB_FILENAME
        self.db_path = Path(db_path)
        self._available = False
        try:
            self._init_db()
            self._available = True
        except Exception as exc:
            # A broken history DB must never take down the app - the
            # feature simply goes dark until the underlying issue clears.
            logger.error(f"History disabled - could not open {self.db_path}: {exc}")

    @property
    def available(self) -> bool:
        """False when the DB couldn't be opened/created; callers should
        hide or disable history UI rather than error."""
        return self._available

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    refined TEXT NOT NULL,
                    profile TEXT,
                    template TEXT,
                    backend TEXT,
                    model TEXT,
                    analysis_json TEXT
                )
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            conn.commit()

    def add(self, entry: HistoryEntry) -> Optional[int]:
        """Insert one entry. Returns the new row id, or None on failure
        (logged, never raised - a failed history write must not abort the
        refine that produced it)."""
        if not self._available:
            return None
        created = entry.created_at or datetime.now(timezone.utc).isoformat()
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO history
                        (created_at, prompt, refined, profile, template,
                         backend, model, analysis_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        created,
                        entry.prompt,
                        entry.refined,
                        entry.profile,
                        entry.template,
                        entry.backend,
                        entry.model,
                        json.dumps(entry.analysis, ensure_ascii=False),
                    ),
                )
                conn.commit()
                return cur.lastrowid
        except Exception as exc:
            logger.error(f"Failed to record history entry: {exc}")
            return None

    def _row_to_entry(self, row: sqlite3.Row) -> HistoryEntry:
        try:
            analysis = json.loads(row["analysis_json"]) if row["analysis_json"] else {}
        except (json.JSONDecodeError, TypeError):
            analysis = {}
        return HistoryEntry(
            id=row["id"],
            created_at=row["created_at"],
            prompt=row["prompt"],
            refined=row["refined"],
            profile=row["profile"],
            template=row["template"],
            backend=row["backend"],
            model=row["model"],
            analysis=analysis,
        )

    def list(self, limit: Optional[int] = None, offset: int = 0) -> List[HistoryEntry]:
        """Return entries newest-first. `limit=None` returns all."""
        if not self._available:
            return []
        try:
            with self._connect() as conn:
                sql = "SELECT * FROM history ORDER BY id DESC"
                params: tuple = ()
                if limit is not None:
                    sql += " LIMIT ? OFFSET ?"
                    params = (limit, offset)
                rows = conn.execute(sql, params).fetchall()
                return [self._row_to_entry(r) for r in rows]
        except Exception as exc:
            logger.error(f"Failed to list history: {exc}")
            return []

    def get(self, entry_id: int) -> Optional[HistoryEntry]:
        if not self._available:
            return None
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM history WHERE id = ?", (entry_id,)
                ).fetchone()
                return self._row_to_entry(row) if row else None
        except Exception as exc:
            logger.error(f"Failed to get history entry {entry_id}: {exc}")
            return None

    def delete(self, entry_id: int) -> bool:
        """Delete one entry by id. Returns True if a row was removed."""
        if not self._available:
            return False
        try:
            with self._connect() as conn:
                cur = conn.execute("DELETE FROM history WHERE id = ?", (entry_id,))
                conn.commit()
                return cur.rowcount > 0
        except Exception as exc:
            logger.error(f"Failed to delete history entry {entry_id}: {exc}")
            return False

    def clear(self) -> int:
        """Delete all entries. Returns the number of rows removed."""
        if not self._available:
            return 0
        try:
            with self._connect() as conn:
                cur = conn.execute("DELETE FROM history")
                conn.commit()
                # Reclaim the file space a large history could have taken.
                conn.execute("VACUUM")
                return cur.rowcount
        except Exception as exc:
            logger.error(f"Failed to clear history: {exc}")
            return 0

    def count(self) -> int:
        if not self._available:
            return 0
        try:
            with self._connect() as conn:
                return conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
        except Exception as exc:
            logger.error(f"Failed to count history: {exc}")
            return 0

    def export_json(self, out_path: Path) -> int:
        """Write the entire history to a JSON array file. Returns the count
        of exported entries. Raises on write failure (unlike the routine
        CRUD methods) because an export is an explicit user action whose
        failure they need to see."""
        entries = self.list()
        payload = [asdict(e) for e in entries]
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return len(entries)

    def export_csv(self, out_path: Path) -> int:
        """Write the entire history to a CSV file. Nested analysis is
        flattened to a handful of readable columns plus the raw JSON, so
        the file opens cleanly in a spreadsheet. Returns the entry count."""
        entries = self.list()
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fields = [
            "id",
            "created_at",
            "profile",
            "template",
            "backend",
            "model",
            "score",
            "detected_type",
            "is_ready",
            "prompt",
            "refined",
            "analysis_json",
        ]
        with open(out_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for e in entries:
                a = e.analysis or {}
                writer.writerow(
                    {
                        "id": e.id,
                        "created_at": e.created_at,
                        "profile": e.profile,
                        "template": e.template or "",
                        "backend": e.backend or "",
                        "model": e.model or "",
                        "score": a.get("score", ""),
                        "detected_type": a.get("detected_type", ""),
                        "is_ready": a.get("is_ready", ""),
                        "prompt": e.prompt,
                        "refined": e.refined,
                        "analysis_json": json.dumps(a, ensure_ascii=False),
                    }
                )
        return len(entries)
