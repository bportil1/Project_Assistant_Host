"""Regression coverage for pyPIQUE's two independent PAH workflow contexts."""

from pathlib import Path

from pah.contracts import ArtifactRef, ArtifactRequirement
from pah.labs.artifacts import ArtifactInventory
from pah.labs.runtime_artifact_refresh import reconcile_module_artifacts


MI_KINDS = frozenset({
    "mi_informed_analysis", "mi_informed_model_experiment",
    "mi_informed_quality_model", "mi_informed_validation",
})


def artifact(kind: str, *, project: str = "/workspace") -> ArtifactRef:
    return ArtifactRef(
        artifact_id=f"pypique-{kind}-current",
        kind=kind,
        producer_module="pypique",
        project_id=project,
        location="/tmp/fake-artifact.json",
        schema_id="pah.feature-dataset.matrix" if kind == "feature_dataset" else "pypique.mi_informed_analysis",
        schema_version="1",
        capabilities=("benchmark_reference",) if kind == "feature_dataset" else ("mi_informed_analysis",),
        validation_state="valid",
        metadata={"runtime_managed": True},
    )


def test_mi_refresh_cannot_retract_feature_dataset(tmp_path: Path):
    registry = ArtifactInventory(state_path=tmp_path / "registry.json")
    feature = artifact("feature_dataset")
    mi = artifact("mi_informed_analysis")
    reconcile_module_artifacts(registry, "pypique", (feature, mi), project_id="/workspace")
    reconcile_module_artifacts(registry, "pypique", (mi,), project_id="/workspace", artifact_kinds=MI_KINDS)
    requirement = ArtifactRequirement(
        kind="feature_dataset", producer_module="pypique",
        schema_id="pah.feature-dataset.matrix", schema_version="1",
        capability="benchmark_reference",
    )
    assert registry.matching(requirement, project_id="/workspace")
    assert registry.get(feature.artifact_id) is not None
    assert registry.get(mi.artifact_id) is not None


def test_mi_refresh_retracts_stale_mi_only(tmp_path: Path):
    registry = ArtifactInventory(state_path=tmp_path / "registry.json")
    feature = artifact("feature_dataset")
    mi = artifact("mi_informed_analysis")
    reconcile_module_artifacts(registry, "pypique", (feature, mi), project_id="/workspace")
    reconcile_module_artifacts(registry, "pypique", (), project_id="/workspace", artifact_kinds=MI_KINDS)
    assert registry.get(feature.artifact_id) is not None
    assert registry.get(mi.artifact_id) is None


def test_mi_refresh_does_not_replace_feature_dataset_with_other_context(tmp_path: Path):
    registry = ArtifactInventory(state_path=tmp_path / "registry.json")
    feature = artifact("feature_dataset")
    reconcile_module_artifacts(registry, "pypique", (feature,), project_id="/workspace")
    other = artifact("feature_dataset", project="/another")
    reconcile_module_artifacts(registry, "pypique", (other,), project_id="/workspace", artifact_kinds=MI_KINDS)
    assert registry.get(feature.artifact_id).project_id == "/workspace"
