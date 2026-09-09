"""Runtime registry for cross-module artifacts known to PAH labs."""
from __future__ import annotations

from collections import Counter
from typing import Iterable

from pah.contracts import ArtifactRef, ArtifactRequirement, coerce_artifact_ref


class ArtifactRegistry:
    """Host-owned catalog of artifacts produced during PAH workflows.

    The registry does not parse scientific artifacts. Domain-specific adapters
    register :class:`ArtifactRef` values after creating or discovering outputs;
    lab controllers only query and match those references against generic
    requirements.
    """

    def __init__(self, artifacts: Iterable[ArtifactRef] = ()):
        self._artifacts: dict[str, ArtifactRef] = {}
        for artifact in artifacts:
            self.register(artifact)

    def register(self, artifact: ArtifactRef, *, replace: bool = True) -> ArtifactRef:
        normalized = coerce_artifact_ref(artifact)
        if normalized.artifact_id in self._artifacts and not replace:
            raise ValueError(f"Artifact {normalized.artifact_id!r} is already registered")
        self._artifacts[normalized.artifact_id] = normalized
        return normalized

    def get(self, artifact_id: str) -> ArtifactRef | None:
        return self._artifacts.get(str(artifact_id))

    def remove(self, artifact_id: str) -> ArtifactRef | None:
        return self._artifacts.pop(str(artifact_id), None)

    def clear(self) -> None:
        self._artifacts.clear()

    def all(self) -> tuple[ArtifactRef, ...]:
        return tuple(sorted(self._artifacts.values(), key=lambda item: item.artifact_id))

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
    ) -> tuple[ArtifactRef, ...]:
        artifacts = self.all()
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
            artifacts = tuple(item for item in artifacts if str(parent_artifact_id) in item.parent_artifact_ids)
        if validation_state is not None:
            artifacts = tuple(item for item in artifacts if item.validation_state == str(validation_state))
        return artifacts

    def matching(self, requirement: ArtifactRequirement) -> tuple[ArtifactRef, ...]:
        return tuple(item for item in self.all() if item.matches(requirement))

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
            if (parent := self.get(parent_id)) is not None
        )

    def dependents(self, artifact_id: str) -> tuple[ArtifactRef, ...]:
        return self.find(parent_artifact_id=artifact_id)

    def snapshot(self) -> list[dict]:
        """Backward-compatible list representation used by existing lab clients."""
        return [item.to_dict() for item in self.all()]

    def registry_snapshot(self) -> dict:
        artifacts = self.all()
        kinds = Counter(item.kind for item in artifacts)
        producers = Counter(item.producer_module for item in artifacts)
        validation = Counter(item.validation_state for item in artifacts)
        return {
            "artifacts": [item.to_dict() for item in artifacts],
            "summary": {
                "total": len(artifacts),
                "by_kind": dict(sorted(kinds.items())),
                "by_producer": dict(sorted(producers.items())),
                "by_validation_state": dict(sorted(validation.items())),
            },
        }


# Compatibility name retained for existing PAH integrations and module adapters.
ArtifactInventory = ArtifactRegistry
