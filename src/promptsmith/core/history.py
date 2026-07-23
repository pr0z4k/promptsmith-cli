"""Local prompt history, backed by SQLite.

Every successful refine is recorded here: the original prompt, a compact
snapshot of the analyzer's findings, and the refined output. The store is
a single SQLite file under the user data directory, so it survives
reinstalls and portable installations.

History is best-effort. A locked, unwritable, or corrupt database must not
break prompt refinement. Routine failures are logged and degrade to empty
results, while explicit exports still raise so the user sees the failure.
"""

import csv
import json
import logging
import os
import sqlite3
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, List, Optional, TextIO

from promptsmith.utils.path_utils import get_user_data_dir

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DB_FILENAME = "history.db"
SQLITE_TIMEOUT_SECONDS = 5.0
SQLITE_BUSY_TIMEOUT_MS = 5000


@dataclass
class HistoryEntry:
    """One recorded refinement and its analyzer snapshot."""

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
        """Build a defensive JSON-serializable analysis snapshot."""
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
            logger.debug("Partial analysis snapshot (%s)", exc)
        return snap


class HistoryStore:
    """SQLite-backed CRUD for local prompt history."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            db_path = get_user_data_dir() / DB_FILENAME
        self.db_path = Path(db_path)
        self._available = False
        try:
            self._validate_database_path()
            self._init_db_with_recovery()
            self._available = True
        except Exception as exc:
            logger.error("History disabled - could not open %s: %s", self.db_path, exc)

    @property
    def available(self) -> bool:
        """False when the database could not be safely opened or created."""
        return self._available

    def _validate_database_path(self) -> None:
        """Reject symlinks for the database and its parent directory.

        Prompt history contains full prompts and refined output. Following a
        planted symlink could write that private data to an unintended file.
        """
        if self.db_path.is_symlink():
            raise OSError(f"Refusing to use symlinked history database: {self.db_path}")
        parent = self.db_path.parent
        if parent.exists() and parent.is_symlink():
            raise OSError(f"Refusing to use symlinked history directory: {parent}")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=SQLITE_TIMEOUT_SECONDS,
            isolation_level="DEFERRED",
        )
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {SQLITE_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @staticmethod
    def _is_corruption_error(exc: sqlite3.DatabaseError) -> bool:
        message = str(exc).lower()
        return any(
            marker in message
            for marker in (
                "database disk image is malformed",
                "file is not a database",
                "database corrupt",
                "malformed database schema",
            )
        )

    def _init_db_with_recovery(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._initialize_schema()
        except sqlite3.DatabaseError as exc:
            if not self._is_corruption_error(exc):
                raise
            quarantined = self._quarantine_corrupt_database()
            logger.error(
                "History database was corrupt and has been quarantined as %s; "
                "a new empty database will be created",
                quarantined,
            )
            self._initialize_schema()

    def _quarantine_corrupt_database(self) -> Path:
        """Move a corrupt database aside without deleting user data."""
        if self.db_path.is_symlink():
            raise OSError(f"Refusing to move symlinked history database: {self.db_path}")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = self.db_path.with_name(f"{self.db_path.name}.corrupt-{stamp}")
        counter = 1
        while target.exists():
            target = self.db_path.with_name(
                f"{self.db_path.name}.corrupt-{stamp}-{counter}"
            )
            counter += 1
        os.replace(self.db_path, target)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{self.db_path}{suffix}")
            if sidecar.exists() and not sidecar.is_symlink():
                try:
                    sidecar.unlink()
                except OSError:
                    logger.warning("Could not remove stale SQLite sidecar %s", sidecar)
        return target

    def _initialize_schema(self) -> None:
        with self._connect() as conn:
            journal_mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if str(journal_mode).lower() != "wal":
                logger.warning("SQLite WAL mode unavailable; using %s", journal_mode)
            conn.execute("PRAGMA synchronous = NORMAL")
            check = conn.execute("PRAGMA quick_check").fetchone()[0]
            if check != "ok":
                raise sqlite3.DatabaseError(f"database corrupt: quick_check returned {check}")
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

    def add(self, entry: HistoryEntry) -> Optional[int]:
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
                return cur.lastrowid
        except (sqlite3.Error, OSError, TypeError, ValueError) as exc:
            logger.error("Failed to record history entry: %s", exc)
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
        if not self._available:
            return []
        if limit is not None and limit < 0:
            raise ValueError("History limit cannot be negative")
        if offset < 0:
            raise ValueError("History offset cannot be negative")
        try:
            with self._connect() as conn:
                sql = "SELECT * FROM history ORDER BY id DESC"
                params: tuple = ()
                if limit is not None:
                    sql += " LIMIT ? OFFSET ?"
                    params = (limit, offset)
                rows = conn.execute(sql, params).fetchall()
                return [self._row_to_entry(row) for row in rows]
        except (sqlite3.Error, OSError) as exc:
            logger.error("Failed to list history: %s", exc)
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
        except (sqlite3.Error, OSError) as exc:
            logger.error("Failed to get history entry %s: %s", entry_id, exc)
            return None

    def delete(self, entry_id: int) -> bool:
        if not self._available:
            return False
        try:
            with self._connect() as conn:
                cur = conn.execute("DELETE FROM history WHERE id = ?", (entry_id,))
                return cur.rowcount > 0
        except (sqlite3.Error, OSError) as exc:
            logger.error("Failed to delete history entry %s: %s", entry_id, exc)
            return False

    def clear(self) -> int:
        if not self._available:
            return 0
        try:
            with self._connect() as conn:
                cur = conn.execute("DELETE FROM history")
                removed = cur.rowcount
            with self._connect() as conn:
                conn.execute("VACUUM")
            return removed
        except (sqlite3.Error, OSError) as exc:
            logger.error("Failed to clear history: %s", exc)
            return 0

    def count(self) -> int:
        if not self._available:
            return 0
        try:
            with self._connect() as conn:
                return int(conn.execute("SELECT COUNT(*) FROM history").fetchone()[0])
        except (sqlite3.Error, OSError) as exc:
            logger.error("Failed to count history: %s", exc)
            return 0

    @staticmethod
    def _atomic_export(
        out_path: Path,
        writer: Callable[[TextIO], None],
        *,
        newline: Optional[str] = None,
    ) -> None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if out_path.is_symlink():
            raise OSError(f"Refusing to export through symlink: {out_path}")

        temp_path: Optional[Path] = None
        fd: Optional[int] = None
        try:
            fd, raw_path = tempfile.mkstemp(
                prefix=f".{out_path.name}.", suffix=".tmp", dir=out_path.parent
            )
            temp_path = Path(raw_path)
            with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as handle:
                fd = None
                writer(handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, out_path)
            temp_path = None
        finally:
            if fd is not None:
                os.close(fd)
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def export_json(self, out_path: Path) -> int:
        entries = self.list()
        payload = [asdict(entry) for entry in entries]
        self._atomic_export(
            Path(out_path),
            lambda handle: json.dump(payload, handle, ensure_ascii=False, indent=2),
        )
        return len(entries)

    def export_csv(self, out_path: Path) -> int:
        entries = self.list()
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

        def write_csv(handle: TextIO) -> None:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for entry in entries:
                analysis = entry.analysis or {}
                writer.writerow(
                    {
                        "id": entry.id,
                        "created_at": entry.created_at,
                        "profile": entry.profile,
                        "template": entry.template or "",
                        "backend": entry.backend or "",
                        "model": entry.model or "",
                        "score": analysis.get("score", ""),
                        "detected_type": analysis.get("detected_type", ""),
                        "is_ready": analysis.get("is_ready", ""),
                        "prompt": entry.prompt,
                        "refined": entry.refined,
                        "analysis_json": json.dumps(analysis, ensure_ascii=False),
                    }
                )

        self._atomic_export(Path(out_path), write_csv, newline="")
        return len(entries)
