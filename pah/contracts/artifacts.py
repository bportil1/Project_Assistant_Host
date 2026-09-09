"""Serializable cross-module artifact descriptors.

The contracts intentionally describe artifacts without encoding pyPIQUE, HSQA,
or ML_Lab semantics. Domain modules own the schemas; PAH owns routing,
identity, validation state, and provenance between producers and consumers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping


_VALIDATION_STATES = {"unknown", "valid", "invalid"}


def _tuple_of_strings(values: Iterable[Any] | None) -> tuple[str, ...]:
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
    return tuple(str(value) for value in values if str(value))


@dataclass(frozen=True)
class ArtifactRequirement:
    kind: str
    schema_id: str | None = None
    schema_version: str | None = None
    optional: bool = False
    producer_module: str | None = None
    capability: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "optional": self.optional,
            "producer_module": self.producer_module,
            "capability": self.capability,
        }


@dataclass(frozen=True)
class ArtifactRef:
    artifact_id: str
    kind: str
    producer_module: str
    location: str | None = None
    schema_id: str | None = None
    schema_version: str | None = None
    media_type: str | None = None
    producer_version: str | None = None
    project_id: str | None = None
    session_id: str | None = None
    created_at: str | None = None
    capabilities: tuple[str, ...] = ()
    parent_artifact_ids: tuple[str, ...] = ()
    validation_state: str = "unknown"
    validation_errors: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.artifact_id).strip():
            raise ValueError("artifact_id must not be empty")
        if not str(self.kind).strip():
            raise ValueError("kind must not be empty")
        if not str(self.producer_module).strip():
            raise ValueError("producer_module must not be empty")
        if self.validation_state not in _VALIDATION_STATES:
            choices = ", ".join(sorted(_VALIDATION_STATES))
            raise ValueError(f"validation_state must be one of: {choices}")
        object.__setattr__(self, "capabilities", _tuple_of_strings(self.capabilities))
        object.__setattr__(self, "parent_artifact_ids", _tuple_of_strings(self.parent_artifact_ids))
        object.__setattr__(self, "validation_errors", _tuple_of_strings(self.validation_errors))

    def matches(self, requirement: ArtifactRequirement) -> bool:
        if self.kind != requirement.kind:
            return False
        if requirement.schema_id and self.schema_id != requirement.schema_id:
            return False
        if requirement.schema_version and self.schema_version != requirement.schema_version:
            return False
        if requirement.producer_module and self.producer_module != requirement.producer_module:
            return False
        if requirement.capability and requirement.capability not in self.capabilities:
            return False
        return self.validation_state != "invalid"

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "producer_module": self.producer_module,
            "location": self.location,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "media_type": self.media_type,
            "producer_version": self.producer_version,
            "project_id": self.project_id,
            "session_id": self.session_id,
            "created_at": self.created_at,
            "capabilities": list(self.capabilities),
            "parent_artifact_ids": list(self.parent_artifact_ids),
            "validation_state": self.validation_state,
            "validation_errors": list(self.validation_errors),
            "metadata": dict(self.metadata),
            "provenance": dict(self.provenance),
        }


def coerce_artifact_ref(value: ArtifactRef | Mapping[str, Any]) -> ArtifactRef:
    """Normalize an artifact supplied by an in-process adapter or JSON API."""
    if isinstance(value, ArtifactRef):
        return value
    if not isinstance(value, Mapping):
        raise TypeError("artifact must be an ArtifactRef or mapping")

    metadata = value.get("metadata") or {}
    provenance = value.get("provenance") or {}
    if not isinstance(metadata, Mapping):
        raise TypeError("artifact metadata must be a mapping")
    if not isinstance(provenance, Mapping):
        raise TypeError("artifact provenance must be a mapping")

    return ArtifactRef(
        artifact_id=str(value.get("artifact_id") or ""),
        kind=str(value.get("kind") or ""),
        producer_module=str(value.get("producer_module") or ""),
        location=str(value["location"]) if value.get("location") is not None else None,
        schema_id=str(value["schema_id"]) if value.get("schema_id") is not None else None,
        schema_version=str(value["schema_version"]) if value.get("schema_version") is not None else None,
        media_type=str(value["media_type"]) if value.get("media_type") is not None else None,
        producer_version=str(value["producer_version"]) if value.get("producer_version") is not None else None,
        project_id=str(value["project_id"]) if value.get("project_id") is not None else None,
        session_id=str(value["session_id"]) if value.get("session_id") is not None else None,
        created_at=str(value["created_at"]) if value.get("created_at") is not None else None,
        capabilities=_tuple_of_strings(value.get("capabilities")),
        parent_artifact_ids=_tuple_of_strings(value.get("parent_artifact_ids")),
        validation_state=str(value.get("validation_state") or "unknown"),
        validation_errors=_tuple_of_strings(value.get("validation_errors")),
        metadata=dict(metadata),
        provenance=dict(provenance),
    )
