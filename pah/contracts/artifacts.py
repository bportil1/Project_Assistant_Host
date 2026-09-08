"""Serializable cross-module artifact descriptors.

The contracts intentionally describe artifacts without encoding pyPIQUE, HSQA,
or ML_Lab semantics. Domain modules own the schemas; PAH owns routing and
provenance between producers and consumers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ArtifactRequirement:
    kind: str
    schema_id: str | None = None
    schema_version: str | None = None
    optional: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "optional": self.optional,
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
    metadata: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)

    def matches(self, requirement: ArtifactRequirement) -> bool:
        if self.kind != requirement.kind:
            return False
        if requirement.schema_id and self.schema_id != requirement.schema_id:
            return False
        if requirement.schema_version and self.schema_version != requirement.schema_version:
            return False
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "producer_module": self.producer_module,
            "location": self.location,
            "schema_id": self.schema_id,
            "schema_version": self.schema_version,
            "media_type": self.media_type,
            "metadata": dict(self.metadata),
            "provenance": dict(self.provenance),
        }
