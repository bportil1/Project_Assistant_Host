"""Rebuildable SQLite *lookup* for PAH's existing artifact JSON registry.

No artifact bytes are stored or opened. Registry JSON remains authoritative;
SQLite is a disposable, per-host-instance index of descriptors only.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Any
import sqlite3

from .artifacts import ArtifactRegistry


_INDEX_VERSION = 1
_MAX_LIMIT = 100


class ArtifactReferenceIndex:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._synced_revision: int | None = None
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS artifact_refs (
                    artifact_id TEXT PRIMARY KEY,
                    project_id TEXT,
                    workspace_id TEXT,
                    kind TEXT NOT NULL,
                    producer_module TEXT NOT NULL,
                    schema_id TEXT,
                    schema_version TEXT,
                    validation_state TEXT NOT NULL,
                    created_at TEXT,
                    is_alias INTEGER NOT NULL,
                    is_history INTEGER NOT NULL,
                    publication_revision INTEGER,
                    source_fingerprint TEXT,
                    reference_status TEXT,
                    search_text TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS artifact_refs_project
                    ON artifact_refs(project_id, workspace_id, created_at);
                CREATE INDEX IF NOT EXISTS artifact_refs_producer
                    ON artifact_refs(project_id, producer_module, kind);
                CREATE TABLE IF NOT EXISTS artifact_capabilities (
                    artifact_id TEXT NOT NULL,
                    capability TEXT NOT NULL,
                    PRIMARY KEY(artifact_id, capability)
                );
                CREATE INDEX IF NOT EXISTS artifact_capability_lookup
                    ON artifact_capabilities(capability, artifact_id);
                CREATE TABLE IF NOT EXISTS artifact_index_meta (
                    name TEXT PRIMARY KEY, value TEXT NOT NULL
                );
            """)

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def sync(self, registry: ArtifactRegistry) -> None:
        """Atomically refresh when the authoritative registry has changed.

        Every process restart rebuilds from JSON. The index can be removed
        without losing artifacts, producer records, or workflow selections.
        """
        with self._lock:
            if self._synced_revision == registry.revision:
                return
            artifacts = registry.all()
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("DELETE FROM artifact_capabilities")
                db.execute("DELETE FROM artifact_refs")
                for artifact in artifacts:
                    publication = artifact.metadata.get("pah_publication")
                    publication = publication if isinstance(publication, dict) else {}
                    status = artifact.metadata.get("pah_reference_status")
                    status = status if isinstance(status, dict) else {}
                    workspace_id = publication.get("workspace_id")
                    workspace_id = workspace_id if isinstance(workspace_id, str) else None
                    revision = publication.get("revision")
                    revision = revision if type(revision) is int else None
                    fingerprint = publication.get("source_fingerprint")
                    fingerprint = fingerprint if isinstance(fingerprint, str) else None
                    reference_status = status.get("state")
                    reference_status = reference_status if reference_status in {"active", "stale", "missing", "withdrawn"} else "unverified"
                    db.execute("""INSERT INTO artifact_refs (
                        artifact_id, project_id, workspace_id, kind, producer_module,
                        schema_id, schema_version, validation_state, created_at,
                        is_alias, is_history, publication_revision, source_fingerprint,
                        reference_status, search_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (
                        artifact.artifact_id, artifact.project_id, workspace_id,
                        artifact.kind, artifact.producer_module, artifact.schema_id,
                        artifact.schema_version, artifact.validation_state, artifact.created_at,
                        int(bool(artifact.metadata.get("registry_alias"))),
                        int(bool(artifact.metadata.get("history_snapshot"))),
                        revision, fingerprint, reference_status,
                        " ".join((artifact.artifact_id, artifact.kind, artifact.producer_module,
                                  artifact.schema_id or "")).lower(),
                    ))
                    db.executemany(
                        "INSERT INTO artifact_capabilities (artifact_id, capability) VALUES (?, ?)",
                        [(artifact.artifact_id, capability) for capability in set(artifact.capabilities)],
                    )
                db.execute("INSERT OR REPLACE INTO artifact_index_meta (name, value) VALUES ('schema', ?)",
                           (str(_INDEX_VERSION),))
            self._synced_revision = registry.revision

    def query(
        self,
        registry: ArtifactRegistry,
        *,
        host_project_id: str | None,
        workspace_id: str | None,
        producer_module: str | None = None,
        kind: str | None = None,
        schema_id: str | None = None,
        capability: str | None = None,
        search: str | None = None,
        include_history: bool = False,
        include_aliases: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return references only for the selected host project/workspace.

        Legacy descriptors without workspace metadata remain visible *only*
        when their project matches. Explicit published workspace records are
        never shown in a different workspace sharing the same project root.
        """
        if type(limit) is not int or not 1 <= limit <= _MAX_LIMIT:
            raise ValueError(f"limit must be between 1 and {_MAX_LIMIT}")
        if type(offset) is not int or not 0 <= offset <= 100_000:
            raise ValueError("offset must be between 0 and 100000")
        if not host_project_id:
            return {"total": 0, "limit": limit, "offset": offset, "items": []}
        with self._lock:
            self.sync(registry)
            sql = ["project_id = ?", "(workspace_id IS NULL OR workspace_id = ?)"]
            params: list[Any] = [host_project_id, workspace_id]
            for field, value in (("producer_module", producer_module), ("kind", kind), ("schema_id", schema_id)):
                if value is not None:
                    sql.append(f"{field} = ?")
                    params.append(str(value))
            if not include_aliases:
                sql.append("is_alias = 0")
            if not include_history:
                sql.append("is_history = 0")
            if capability is not None:
                sql.append("EXISTS (SELECT 1 FROM artifact_capabilities c WHERE c.artifact_id = artifact_refs.artifact_id AND c.capability = ?)")
                params.append(str(capability))
            if search:
                # LIKE wildcards are escaped; user input never becomes SQL.
                pattern = str(search).lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                sql.append("search_text LIKE ? ESCAPE '\\'")
                params.append("%" + pattern + "%")
            where = " AND ".join(sql)
            with self._connect() as db:
                total = db.execute("SELECT COUNT(*) FROM artifact_refs WHERE " + where, params).fetchone()[0]
                rows = db.execute(
                    "SELECT * FROM artifact_refs WHERE " + where +
                    " ORDER BY COALESCE(created_at, '') DESC, artifact_id ASC LIMIT ? OFFSET ?",
                    [*params, limit, offset],
                ).fetchall()
            # Reference-only response. No file contents, raw filesystem paths,
            # producer DB handles or PAH-authorized download links.
            items = []
            for row in rows:
                record = registry.get(row["artifact_id"])
                if record is None:
                    continue
                items.append({
                    "artifact_id": record.artifact_id,
                    "kind": record.kind,
                    "producer_module": record.producer_module,
                    "schema_id": record.schema_id,
                    "schema_version": record.schema_version,
                    "project_id": record.project_id,
                    "workspace_id": row["workspace_id"],
                    "created_at": record.created_at,
                    "validation_state": record.validation_state,
                    "capabilities": list(record.capabilities),
                    "parent_artifact_ids": list(record.parent_artifact_ids),
                    "is_history": bool(row["is_history"]),
                    "publication_revision": row["publication_revision"],
                    "source_fingerprint": row["source_fingerprint"],
                    "reference_status": row["reference_status"],
                    "fingerprint_verified": False,
                })
            return {"total": total, "limit": limit, "offset": offset, "items": items}
