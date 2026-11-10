"""Host-side publication boundary; producer data stays producer-owned."""
from __future__ import annotations

from typing import Any, Mapping
from dataclasses import replace
from datetime import datetime, timezone

from pah.contracts import ArtifactPublication
from .artifacts import ArtifactRegistry


def publish_reference(
    inventory: ArtifactRegistry,
    payload: Mapping[str, Any],
    *,
    active_context: Any,
    known_modules: set[str] | frozenset[str],
) -> tuple[dict[str, Any], bool]:
    """Publish one immutable versioned descriptor; return (descriptor, created).

    This method deliberately does not read, import or checksum the produced
    file and cannot authorize artifact downloads or module DB access.
    """
    publication = ArtifactPublication.from_dict(payload)
    publication.validate_scope(active_context)
    if publication.module_id not in known_modules:
        raise ValueError("Artifact producer is not a registered PAH module")
    artifact = publication.to_registry_artifact()
    for parent_id in artifact.parent_artifact_ids:
        parent = inventory.get(parent_id)
        if parent is not None and parent.project_id != artifact.project_id:
            raise ValueError("Artifact parent belongs to a different project")
    current = inventory.get(artifact.artifact_id)
    if current is not None:
        current_base = current.to_dict()
        original = artifact.to_dict()
        current_base["metadata"].pop("pah_reference_status", None)
        if current_base == original:
            # Idempotent re-publication must not reactivate an explicitly
            # stale/withdrawn reference or change its observed state.
            return current.to_dict(), False
        raise ValueError("Artifact ID already published with different data; use a new immutable ID")
    artifact = replace(artifact, metadata={
        **artifact.metadata,
        "pah_reference_status": {"state": "active", "reason": "producer published", "observed_at": artifact.created_at},
    })
    inventory.register(artifact, replace=False)
    return artifact.to_dict(), True


def observe_reference_status(
    inventory: ArtifactRegistry,
    artifact_id: str,
    *,
    state: str,
    reason: str,
    active_context: Any,
    module_id: str,
) -> dict[str, Any]:
    """Record producer-observed availability without altering artifact identity.

    This is a producer report, not a host-side checksum or filesystem check.
    An unavailable artifact remains historically discoverable.
    """
    if state not in {"active", "stale", "missing", "withdrawn"}:
        raise ValueError("Invalid producer reference status")
    if not isinstance(reason, str) or len(reason) > 500:
        raise ValueError("Reference status reason must be a short string")
    artifact = inventory.get(artifact_id)
    if artifact is None:
        raise KeyError("Unknown published artifact")
    publication = artifact.metadata.get("pah_publication")
    if not isinstance(publication, dict):
        raise ValueError("Legacy artifacts do not support the publication status API")
    expected = {
        "workspace_id": active_context.workspace_id,
        "host_project_id": active_context.host_project_id,
        "instance_id": active_context.instance_id,
        "module_instance_id": f"{active_context.instance_id}:{module_id}",
        "module_id": module_id,
    }
    if artifact.producer_module != module_id or any(publication.get(k) != v or v is None for k, v in expected.items()):
        raise ValueError("Reference status update does not match the active producer/project")
    metadata = dict(artifact.metadata)
    metadata["pah_reference_status"] = {
        "state": state, "reason": reason,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    updated = replace(artifact, metadata=metadata)
    inventory.register(updated, replace=True)
    return updated.to_dict()
