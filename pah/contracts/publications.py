"""Versioned, producer-authored artifact *references* for PAH mediation.

This contract does not authorize PAH to open artifact files, query producer
SQLite databases, or assume that a claimed checksum has been verified.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping

from .artifacts import ArtifactRef, coerce_artifact_ref


PUBLICATION_SCHEMA = "pah.published-artifact-reference"
PUBLICATION_VERSION = 1
_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_PROTECTED_METADATA = frozenset({
    "pah_publication", "pah_reference_status", "registry_alias", "history_snapshot", "source_alias",
    "snapshot_artifact_id", "snapshot_fingerprint", "superseded",
    "archived_copy", "archived_from", "history_selectable",
})


@dataclass(frozen=True)
class ArtifactPublication:
    """A scoped, immutable publication of a producer-owned artifact."""

    artifact: ArtifactRef
    instance_id: str
    workspace_id: str
    host_project_id: str
    module_id: str
    module_instance_id: str
    context_token: str
    revision: int
    module_local_project_id: str | None = None
    source_fingerprint: str | None = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ArtifactPublication":
        if not isinstance(payload, Mapping):
            raise TypeError("Publication must be a JSON object")
        if payload.get("schema") != PUBLICATION_SCHEMA or type(payload.get("schema_version")) is not int or payload["schema_version"] != PUBLICATION_VERSION:
            raise ValueError("Unsupported artifact publication schema or version")
        context = payload.get("context")
        if not isinstance(context, Mapping):
            raise ValueError("Publication context is required")
        artifact = coerce_artifact_ref(payload.get("artifact"))
        required = ("instance_id", "workspace_id", "host_project_id", "module_id", "module_instance_id", "context_token")
        fields = {key: str(context.get(key) or "").strip() for key in required}
        if not all(fields.values()):
            raise ValueError("Publication must specify complete host, workspace and module identity")
        revision = payload.get("revision")
        if type(revision) is not int or revision < 1:
            raise ValueError("Publication revision must be a positive integer")
        fingerprint = payload.get("source_fingerprint")
        if fingerprint is not None and (not isinstance(fingerprint, str) or not _SHA256.fullmatch(fingerprint)):
            raise ValueError("source_fingerprint must be sha256: followed by 64 lowercase hex digits")
        if artifact.producer_module != fields["module_id"]:
            raise ValueError("Publication module must match artifact producer")
        if artifact.project_id != fields["host_project_id"]:
            raise ValueError("Artifact project must match publication host project")
        if _PROTECTED_METADATA.intersection(artifact.metadata):
            raise ValueError("Publication metadata contains reserved PAH registry fields")
        local = context.get("module_local_project_id")
        return cls(
            artifact=artifact, revision=revision, source_fingerprint=fingerprint,
            module_local_project_id=str(local) if local is not None else None,
            **fields,
        )

    def validate_scope(self, active: Any) -> None:
        """Use the P5-01 selected context, never the request's claimed project."""
        expected = {
            "instance_id": active.instance_id,
            "workspace_id": active.workspace_id,
            "host_project_id": active.host_project_id,
            "context_token": active.context_token,
        }
        for key, value in expected.items():
            if getattr(self, key) != value or value is None:
                raise ValueError("Artifact publication context is stale or belongs to another workspace/project")
        if self.module_instance_id != f"{active.instance_id}:{self.module_id}":
            raise ValueError("Artifact publication module instance does not match this host")

    def to_registry_artifact(self) -> ArtifactRef:
        from dataclasses import replace
        metadata = dict(self.artifact.metadata)
        metadata["pah_publication"] = {
            "schema_version": PUBLICATION_VERSION,
            "instance_id": self.instance_id,
            "workspace_id": self.workspace_id,
            "host_project_id": self.host_project_id,
            "module_id": self.module_id,
            "module_instance_id": self.module_instance_id,
            "module_local_project_id": self.module_local_project_id,
            "revision": self.revision,
            "source_fingerprint": self.source_fingerprint,
            # A source hash is a producer claim; PAH does not dereference bytes.
            "fingerprint_verified": False,
        }
        return replace(self.artifact, metadata=metadata)
