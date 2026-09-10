"""Runtime registry for cross-module artifacts known to PAH labs."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from typing import Iterable

from pah.contracts import ArtifactRef, ArtifactRequirement, coerce_artifact_ref


_STATE_SCHEMA = "pah.artifact-registry"
_STATE_VERSION = 1
_HISTORY_EXCLUDE_METADATA = {
    "registry_alias",
    "snapshot_artifact_id",
    "history_snapshot",
    "source_alias",
    "superseded",
    "archived_copy",
    "archived_from",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_id(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value)).strip("-._")
    return text or "artifact"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _location_fingerprint(location: str | None) -> dict[str, str | int | None]:
    if not location:
        return {"type": "none", "sha256": None}
    path = Path(location).expanduser()
    try:
        if path.is_file():
            return {"type": "file", "sha256": _sha256_file(path), "size": path.stat().st_size}
        if path.is_dir():
            # Scientific directory artifacts generally expose a stable manifest.
            # Hash that manifest rather than recursively hashing potentially-large
            # model checkpoints on every PAH status refresh.
            manifest = path / "manifest.json"
            if manifest.is_file():
                return {"type": "directory-manifest", "sha256": _sha256_file(manifest)}
            stat = path.stat()
            return {
                "type": "directory-reference",
                "sha256": None,
                "mtime_ns": int(stat.st_mtime_ns),
            }
    except OSError:
        pass
    return {"type": "missing", "sha256": None}


class ArtifactRegistry:
    """Host-owned catalog of current and historical PAH workflow artifacts.

    Provider adapters are free to keep advertising stable ``*-current`` IDs.
    PAH snapshots those aliases into immutable history records, rewrites their
    lineage to immutable parent snapshots, and persists both history and input
    selections.  Modules therefore remain unaware of PAH's history mechanics.
    """

    def __init__(
        self,
        artifacts: Iterable[ArtifactRef] = (),
        *,
        state_path: str | Path | None = None,
        archive_dir: str | Path | None = None,
    ):
        self._artifacts: dict[str, ArtifactRef] = {}
        self._selections: dict[str, str] = {}
        self._state_path = Path(state_path).expanduser().resolve() if state_path else None
        if archive_dir is not None:
            self._archive_dir = Path(archive_dir).expanduser().resolve()
        elif self._state_path is not None:
            self._archive_dir = self._state_path.parent / "artifact-history"
        else:
            self._archive_dir = None
        self._load()
        for artifact in artifacts:
            self.register(artifact, persist=False)
        if artifacts:
            self._persist()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _load(self) -> None:
        if self._state_path is None or not self._state_path.is_file():
            return
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(payload, dict) or payload.get("schema") != _STATE_SCHEMA:
            return
        if int(payload.get("schema_version", 0) or 0) != _STATE_VERSION:
            return
        for raw in payload.get("artifacts", []):
            try:
                artifact = coerce_artifact_ref(raw)
            except (TypeError, ValueError):
                continue
            self._artifacts[artifact.artifact_id] = artifact
        selections = payload.get("selections") or {}
        if isinstance(selections, dict):
            self._selections = {
                str(key): str(value)
                for key, value in selections.items()
                if str(key) and str(value)
            }

    def _persist(self) -> None:
        if self._state_path is None:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema": _STATE_SCHEMA,
            "schema_version": _STATE_VERSION,
            "artifacts": [item.to_dict() for item in self.all()],
            "selections": dict(sorted(self._selections.items())),
        }
        tmp = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self._state_path)

    # ------------------------------------------------------------------
    # Registration / immutable history
    # ------------------------------------------------------------------
    def register(
        self,
        artifact: ArtifactRef,
        *,
        replace: bool = True,
        persist: bool = True,
    ) -> ArtifactRef:
        normalized = coerce_artifact_ref(artifact)
        if normalized.artifact_id in self._artifacts and not replace:
            raise ValueError(f"Artifact {normalized.artifact_id!r} is already registered")
        self._artifacts[normalized.artifact_id] = normalized
        if persist:
            self._persist()
        return normalized

    def _canonical_parent_ids(self, artifact: ArtifactRef) -> tuple[str, ...]:
        return tuple(self.resolve_alias(parent_id) or parent_id for parent_id in artifact.parent_artifact_ids)

    def _snapshot_fingerprint(self, artifact: ArtifactRef) -> str:
        metadata = {
            str(key): value
            for key, value in dict(artifact.metadata).items()
            if str(key) not in _HISTORY_EXCLUDE_METADATA
        }
        payload = {
            "kind": artifact.kind,
            "producer_module": artifact.producer_module,
            "producer_version": artifact.producer_version,
            "schema_id": artifact.schema_id,
            "schema_version": artifact.schema_version,
            "project_id": artifact.project_id,
            "session_id": artifact.session_id,
            "capabilities": list(artifact.capabilities),
            "parent_artifact_ids": list(self._canonical_parent_ids(artifact)),
            "validation_state": artifact.validation_state,
            "validation_errors": list(artifact.validation_errors),
            "metadata": metadata,
            "provenance": dict(artifact.provenance),
            "location": _location_fingerprint(artifact.location),
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _archive_file(self, artifact: ArtifactRef, snapshot_id: str) -> tuple[str | None, dict]:
        metadata = dict(artifact.metadata)
        if self._archive_dir is None or not artifact.location:
            return artifact.location, metadata
        source = Path(artifact.location).expanduser()
        if not source.is_file():
            return artifact.location, metadata
        destination_dir = self._archive_dir / _safe_id(snapshot_id)
        destination = destination_dir / source.name
        try:
            destination_dir.mkdir(parents=True, exist_ok=True)
            if not destination.is_file() or _sha256_file(destination) != _sha256_file(source):
                shutil.copy2(source, destination)
        except OSError:
            return artifact.location, metadata
        metadata["archived_copy"] = True
        metadata["archived_from"] = str(source.resolve())
        return str(destination.resolve()), metadata

    def register_current(self, artifact: ArtifactRef) -> tuple[ArtifactRef, ArtifactRef]:
        """Register a provider's mutable current alias and preserve an immutable snapshot."""
        current = coerce_artifact_ref(artifact)
        alias_id = current.artifact_id
        canonical_parents = self._canonical_parent_ids(current)
        if canonical_parents != current.parent_artifact_ids:
            current = replace(current, parent_artifact_ids=canonical_parents)

        fingerprint = self._snapshot_fingerprint(current)
        base = alias_id[:-8] if alias_id.endswith("-current") else alias_id
        snapshot_id = f"{_safe_id(base)}-{fingerprint[:12]}"
        snapshot_location, snapshot_metadata = self._archive_file(current, snapshot_id)
        selectable = bool(snapshot_metadata.get("history_selectable", current.kind != "code_analysis"))

        # Mark older snapshots from this alias/project as superseded while retaining
        # them for inspection and explicit branching.
        for artifact_id, previous in tuple(self._artifacts.items()):
            meta = dict(previous.metadata)
            if not meta.get("history_snapshot"):
                continue
            if meta.get("source_alias") != alias_id:
                continue
            if previous.project_id != current.project_id:
                continue
            superseded = artifact_id != snapshot_id
            if bool(meta.get("superseded")) != superseded:
                meta["superseded"] = superseded
                self._artifacts[artifact_id] = replace(previous, metadata=meta)

        snapshot_metadata.update({
            "history_snapshot": True,
            "source_alias": alias_id,
            "snapshot_fingerprint": fingerprint,
            "superseded": False,
            "history_selectable": selectable,
        })
        snapshot = replace(
            current,
            artifact_id=snapshot_id,
            location=snapshot_location,
            parent_artifact_ids=canonical_parents,
            created_at=current.created_at or _utc_now(),
            metadata=snapshot_metadata,
        )
        self._artifacts[snapshot_id] = snapshot

        alias_metadata = dict(current.metadata)
        alias_metadata.update({
            "registry_alias": True,
            "snapshot_artifact_id": snapshot_id,
            "snapshot_fingerprint": fingerprint,
        })
        alias = replace(current, metadata=alias_metadata, parent_artifact_ids=canonical_parents)
        self._artifacts[alias_id] = alias
        self._persist()
        return alias, snapshot

    def deactivate_current(self, artifact_id: str) -> ArtifactRef | None:
        """Remove a mutable current alias while retaining its historical snapshot(s)."""
        removed = self._artifacts.pop(str(artifact_id), None)
        if removed is not None:
            alias_id = removed.artifact_id
            for key, previous in tuple(self._artifacts.items()):
                meta = dict(previous.metadata)
                if meta.get("history_snapshot") and meta.get("source_alias") == alias_id:
                    if not meta.get("superseded"):
                        meta["superseded"] = True
                        self._artifacts[key] = replace(previous, metadata=meta)
            self._persist()
        return removed

    def get(self, artifact_id: str) -> ArtifactRef | None:
        return self._artifacts.get(str(artifact_id))

    def resolve_alias(self, artifact_id: str) -> str | None:
        artifact = self.get(artifact_id)
        if artifact is None:
            return None
        snapshot_id = artifact.metadata.get("snapshot_artifact_id") if artifact.metadata.get("registry_alias") else None
        if snapshot_id and self.get(str(snapshot_id)) is not None:
            return str(snapshot_id)
        return artifact.artifact_id

    def remove(self, artifact_id: str) -> ArtifactRef | None:
        removed = self._artifacts.pop(str(artifact_id), None)
        if removed is not None:
            for key, value in tuple(self._selections.items()):
                if value == removed.artifact_id:
                    self._selections.pop(key, None)
            self._persist()
        return removed

    def clear(self) -> None:
        self._artifacts.clear()
        self._selections.clear()
        self._persist()

    def all(self) -> tuple[ArtifactRef, ...]:
        return tuple(sorted(self._artifacts.values(), key=lambda item: item.artifact_id))

    # ------------------------------------------------------------------
    # Queries / lineage
    # ------------------------------------------------------------------
    def find(
        self,
        *,
        kind: str | None = None,
        producer_module: str | None = None,
        capability: str | None = None,
        schema_id: str | None = None,
        schema_version: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
        parent_artifact_id: str | None = None,
        validation_state: str | None = None,
        include_aliases: bool = True,
        include_history: bool = True,
    ) -> tuple[ArtifactRef, ...]:
        artifacts = self.all()
        if not include_aliases:
            artifacts = tuple(item for item in artifacts if not item.metadata.get("registry_alias"))
        if not include_history:
            artifacts = tuple(item for item in artifacts if not item.metadata.get("history_snapshot"))
        if kind is not None:
            artifacts = tuple(item for item in artifacts if item.kind == str(kind))
        if producer_module is not None:
            artifacts = tuple(item for item in artifacts if item.producer_module == str(producer_module))
        if capability is not None:
            artifacts = tuple(item for item in artifacts if str(capability) in item.capabilities)
        if schema_id is not None:
            artifacts = tuple(item for item in artifacts if item.schema_id == str(schema_id))
        if schema_version is not None:
            artifacts = tuple(item for item in artifacts if item.schema_version == str(schema_version))
        if project_id is not None:
            artifacts = tuple(item for item in artifacts if item.project_id == str(project_id))
        if session_id is not None:
            artifacts = tuple(item for item in artifacts if item.session_id == str(session_id))
        if parent_artifact_id is not None:
            canonical_parent = self.resolve_alias(str(parent_artifact_id)) or str(parent_artifact_id)
            artifacts = tuple(
                item for item in artifacts
                if canonical_parent in tuple(self.resolve_alias(parent) or parent for parent in item.parent_artifact_ids)
            )
        if validation_state is not None:
            artifacts = tuple(item for item in artifacts if item.validation_state == str(validation_state))
        return artifacts

    def matching(
        self,
        requirement: ArtifactRequirement,
        *,
        include_history: bool = False,
        project_id: str | None = None,
    ) -> tuple[ArtifactRef, ...]:
        artifacts = tuple(item for item in self.all() if item.matches(requirement))
        if project_id is not None:
            artifacts = tuple(item for item in artifacts if item.project_id in {None, str(project_id)})
        if not include_history:
            artifacts = tuple(item for item in artifacts if not item.metadata.get("history_snapshot"))
        return artifacts

    def history(
        self,
        requirement: ArtifactRequirement,
        *,
        project_id: str | None = None,
    ) -> tuple[ArtifactRef, ...]:
        artifacts = self.matching(requirement, include_history=True, project_id=project_id)
        snapshots = [item for item in artifacts if item.metadata.get("history_snapshot")]
        snapshots.sort(key=lambda item: (item.created_at or "", item.artifact_id), reverse=True)
        return tuple(snapshots)

    def by_kind(self, kind: str) -> tuple[ArtifactRef, ...]:
        return self.find(kind=kind)

    def by_producer(self, producer_module: str) -> tuple[ArtifactRef, ...]:
        return self.find(producer_module=producer_module)

    def by_capability(self, capability: str) -> tuple[ArtifactRef, ...]:
        return self.find(capability=capability)

    def dependencies(self, artifact_id: str) -> tuple[ArtifactRef, ...]:
        artifact = self.get(artifact_id)
        if artifact is None:
            return ()
        return tuple(
            parent
            for parent_id in artifact.parent_artifact_ids
            if (parent := self.get(self.resolve_alias(parent_id) or parent_id)) is not None
        )

    def dependents(self, artifact_id: str) -> tuple[ArtifactRef, ...]:
        canonical = self.resolve_alias(artifact_id) or artifact_id
        return tuple(
            item for item in self.all()
            if canonical in tuple(self.resolve_alias(parent) or parent for parent in item.parent_artifact_ids)
        )

    def ancestor_ids(self, artifact_id: str) -> tuple[str, ...]:
        start = self.resolve_alias(artifact_id) or artifact_id
        seen: set[str] = set()
        pending = [start]
        while pending:
            current_id = pending.pop()
            artifact = self.get(current_id)
            if artifact is None:
                continue
            for parent_id in artifact.parent_artifact_ids:
                canonical = self.resolve_alias(parent_id) or parent_id
                if canonical in seen:
                    continue
                seen.add(canonical)
                pending.append(canonical)
        return tuple(sorted(seen))

    def descends_from(self, artifact_id: str, ancestor_id: str) -> bool:
        child = self.resolve_alias(artifact_id) or artifact_id
        ancestor = self.resolve_alias(ancestor_id) or ancestor_id
        return child == ancestor or ancestor in self.ancestor_ids(child)

    def siblings(self, artifact_id: str) -> tuple[ArtifactRef, ...]:
        artifact = self.get(artifact_id)
        if artifact is None:
            return ()
        parents = set(self.resolve_alias(parent) or parent for parent in artifact.parent_artifact_ids)
        return tuple(
            item for item in self.all()
            if item.artifact_id != artifact.artifact_id
            and item.kind == artifact.kind
            and item.producer_module == artifact.producer_module
            and set(self.resolve_alias(parent) or parent for parent in item.parent_artifact_ids) == parents
            and not item.metadata.get("registry_alias")
        )

    # ------------------------------------------------------------------
    # Per-workflow input selections
    # ------------------------------------------------------------------
    @staticmethod
    def _selection_key(project_id: str | None, workflow_id: str, step_id: str, kind: str) -> str:
        return json.dumps(
            [str(project_id or ""), str(workflow_id), str(step_id), str(kind)],
            separators=(",", ":"),
        )

    def selected_id(
        self,
        *,
        project_id: str | None,
        workflow_id: str,
        step_id: str,
        kind: str,
    ) -> str | None:
        return self._selections.get(self._selection_key(project_id, workflow_id, step_id, kind))

    def select(
        self,
        *,
        project_id: str | None,
        workflow_id: str,
        step_id: str,
        kind: str,
        artifact_id: str | None,
    ) -> str | None:
        key = self._selection_key(project_id, workflow_id, step_id, kind)
        if artifact_id is None:
            self._selections.pop(key, None)
            self._persist()
            return None
        artifact = self.get(str(artifact_id))
        if artifact is None:
            raise KeyError(f"Unknown PAH artifact {artifact_id!r}")
        if artifact.metadata.get("registry_alias"):
            # Current mode is represented by clearing the pin, not pinning a mutable alias.
            self._selections.pop(key, None)
            self._persist()
            return None
        if artifact.metadata.get("history_snapshot") and not artifact.metadata.get("history_selectable", True):
            raise ValueError(f"Artifact {artifact_id!r} is historical-reference-only and cannot be selected as an input")
        self._selections[key] = artifact.artifact_id
        self._persist()
        return artifact.artifact_id

    def snapshot(self) -> list[dict]:
        """Backward-compatible list representation used by existing lab clients."""
        return [item.to_dict() for item in self.all()]

    def registry_snapshot(self) -> dict:
        artifacts = self.all()
        kinds = Counter(item.kind for item in artifacts if not item.metadata.get("registry_alias"))
        producers = Counter(item.producer_module for item in artifacts if not item.metadata.get("registry_alias"))
        validation = Counter(item.validation_state for item in artifacts if not item.metadata.get("registry_alias"))
        history_count = sum(1 for item in artifacts if item.metadata.get("history_snapshot"))
        current_count = sum(1 for item in artifacts if item.metadata.get("registry_alias"))
        return {
            "artifacts": [item.to_dict() for item in artifacts],
            "summary": {
                "total": len(artifacts),
                "current": current_count,
                "history": history_count,
                "by_kind": dict(sorted(kinds.items())),
                "by_producer": dict(sorted(producers.items())),
                "by_validation_state": dict(sorted(validation.items())),
            },
            "selection_count": len(self._selections),
        }


# Compatibility name retained for existing PAH integrations and module adapters.
ArtifactInventory = ArtifactRegistry
