"""Optional, project-scoped SQLite history of job *observations*, not job data.

The history can be deleted and rebuilt as observations arrive. No module's
private scientific data or database is accessed by this store.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Any
from .observations import SCHEMA, VERSION


class ObservationHistory:
    def __init__(self, project_root: str | Path):
        root = Path(project_root).expanduser().resolve(strict=True)
        if not root.is_dir():
            raise ValueError("project_root must be an existing directory")
        self.path = root / ".pah" / "job_monitor" / "observations.sqlite3"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.is_symlink():
            raise ValueError("refusing symlinked observation index")
        with self._connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS observations (
                owner TEXT NOT NULL, job_id TEXT NOT NULL,
                observed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                signature TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY (owner,job_id,signature)
            )""")
            db.execute("CREATE INDEX IF NOT EXISTS ix_observation_time ON observations(observed_at)")

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=3)
        connection.execute("PRAGMA busy_timeout=3000")
        return connection

    def record(self, observations: list[dict[str, Any]]) -> int:
        """Store state/telemetry transitions only; never save stdout or results."""
        added = 0
        with self._connect() as db:
            for item in observations:
                if item.get("schema") != SCHEMA or item.get("version") != VERSION:
                    raise ValueError("invalid observation contract")
                owner, job_id = item.get("owner"), item.get("job_id")
                if not all(isinstance(x, str) and x for x in (owner, job_id)):
                    raise ValueError("invalid observation identity")
                safe = {key: item.get(key) for key in (
                    "schema", "version", "owner", "job_id", "run_id", "producer_state",
                    "observed_state", "telemetry_status", "producer_confirmed_terminal",
                    "cancellation_requested", "cancellation_requested_at", "updated_at")}
                signature = json.dumps({k: safe[k] for k in (
                    "producer_state", "observed_state", "telemetry_status",
                    "cancellation_requested", "producer_confirmed_terminal")}, sort_keys=True)
                cur = db.execute("INSERT OR IGNORE INTO observations (owner, job_id, signature, payload) VALUES (?,?,?,?)",
                                 (owner, job_id, signature, json.dumps(safe, sort_keys=True)))
                added += max(cur.rowcount, 0)
        return added

    def recent(self, *, limit: int = 100) -> list[dict[str, Any]]:
        if not 1 <= limit <= 1000:
            raise ValueError("limit out of range")
        with self._connect() as db:
            rows = db.execute("SELECT payload FROM observations ORDER BY observed_at DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(row[0]) for row in rows]
