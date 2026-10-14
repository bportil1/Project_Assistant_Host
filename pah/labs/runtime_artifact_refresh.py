"""Scoped host-side artifact reconciliation for multi-step module workflows.

Only the artifact kinds owned by the triggering workflow should be added or
retracted. In particular, refreshing pyPIQUE's MI-informed branch must not
remove the benchmark feature dataset produced by its quality-modeling branch.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from ..contracts import ArtifactRef, coerce_artifact_ref
from .artifacts import ArtifactInventory


def reconcile_module_artifacts(
    inventory: ArtifactInventory,
    module_id: str,
    discovered: Iterable[ArtifactRef | Mapping],
    *,
    project_id: str | None = None,
    artifact_kinds: frozenset[str] | None = None,
    provider_present: bool = True,
) -> None:
    """Publish observed artifacts and retract only current aliases in scope.

    An empty discovery for one workflow cannot invalidate artifacts belonging
    to a different workflow, even when both are produced by the same module.
    Historical snapshots remain available through the inventory.
    """
    active_ids: set[str] = set()
    for raw in discovered:
        try:
            artifact = coerce_artifact_ref(raw)
        except (TypeError, ValueError):
            continue
        if artifact.producer_module != module_id or not provider_present:
            continue
        if artifact_kinds is not None and artifact.kind not in artifact_kinds:
            continue
        active_ids.add(artifact.artifact_id)
        if artifact.metadata.get("runtime_managed"):
            inventory.register_current(artifact)
        else:
            inventory.register(artifact)

    for artifact in tuple(inventory.by_producer(module_id)):
        if not artifact.metadata.get("registry_alias"):
            continue
        if project_id is not None and artifact.project_id not in {None, project_id}:
            continue
        if artifact_kinds is not None and artifact.kind not in artifact_kinds:
            continue
        if artifact.artifact_id not in active_ids:
            inventory.deactivate_current(artifact.artifact_id)
