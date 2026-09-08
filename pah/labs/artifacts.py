"""Runtime inventory for cross-module artifacts known to PAH labs."""
from __future__ import annotations

from typing import Iterable

from pah.contracts import ArtifactRef, ArtifactRequirement


class ArtifactInventory:
    """Small in-memory catalog of artifacts produced during a PAH workflow.

    The inventory does not parse scientific artifacts.  Domain-specific adapters
    register :class:`ArtifactRef` values after they create or discover outputs;
    lab controllers only match those references against generic requirements.
    """

    def __init__(self, artifacts: Iterable[ArtifactRef] = ()):
        self._artifacts: dict[str, ArtifactRef] = {}
        for artifact in artifacts:
            self.register(artifact)

    def register(self, artifact: ArtifactRef, *, replace: bool = True) -> ArtifactRef:
        if not isinstance(artifact, ArtifactRef):
            raise TypeError("artifact must be an ArtifactRef")
        if artifact.artifact_id in self._artifacts and not replace:
            raise ValueError(f"Artifact {artifact.artifact_id!r} is already registered")
        self._artifacts[artifact.artifact_id] = artifact
        return artifact

    def remove(self, artifact_id: str) -> ArtifactRef | None:
        return self._artifacts.pop(str(artifact_id), None)

    def clear(self) -> None:
        self._artifacts.clear()

    def all(self) -> tuple[ArtifactRef, ...]:
        return tuple(sorted(self._artifacts.values(), key=lambda item: item.artifact_id))

    def matching(self, requirement: ArtifactRequirement) -> tuple[ArtifactRef, ...]:
        return tuple(item for item in self.all() if item.matches(requirement))

    def by_kind(self, kind: str) -> tuple[ArtifactRef, ...]:
        return tuple(item for item in self.all() if item.kind == str(kind))

    def snapshot(self) -> list[dict]:
        return [item.to_dict() for item in self.all()]
