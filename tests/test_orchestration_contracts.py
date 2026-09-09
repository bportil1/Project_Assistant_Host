from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from pah.contracts import (
    ArtifactRef,
    ArtifactRequirement,
    ModuleContext,
    ModuleManifest,
    WorkflowManifest,
    WorkflowStep,
    coerce_module_manifest,
)
from pah.labs import LabManifest, LabOrchestrator, LabRegistry, ModuleRegistry, RegistryError
from pah.labs.catalog import default_lab_registry
from pah.module_catalog import default_module_registry


def test_module_contract_supports_ui_and_headless_modules_without_ui_requirement():
    hsqa = ModuleManifest(
        module_id="hsqa_dbn",
        display_name="EBM / DBN Analysis Lab",
        collections=("code_analysis_lab", "ml_lab"),
        capabilities=("representation_learning", "mutual_information_analysis"),
        interfaces=("callable_api", "standalone_ui", "embedded_ui", "detachable_ui"),
    )
    ml = ModuleManifest(
        module_id="ml_lab",
        display_name="ML_Lab",
        collections=("ml_lab",),
        capabilities=("classification", "regression", "clustering", "representation_learning"),
        interfaces=("callable_api", "service_adapter"),
    )
    registry = ModuleRegistry((hsqa, ml))

    assert hsqa.has_interface("standalone_ui")
    assert not ml.has_interface("standalone_ui")
    assert {item.module_id for item in registry.providers("representation_learning")} == {"hsqa_dbn", "ml_lab"}
    assert {item.module_id for item in registry.for_collection("ml_lab")} == {"hsqa_dbn", "ml_lab"}


def test_module_manifest_can_be_coerced_from_foreign_module_dataclass():
    @dataclass
    class ForeignManifest:
        id: str
        name: str
        collections: tuple[str, ...]
        capabilities: tuple[str, ...]
        interfaces: tuple[str, ...]

    manifest = coerce_module_manifest(
        ForeignManifest(
            id="demo",
            name="Demo",
            collections=("code_analysis_lab",),
            capabilities=("analysis",),
            interfaces=("callable_api",),
        )
    )
    assert manifest.module_id == "demo"
    assert manifest.display_name == "Demo"
    assert manifest.supports("analysis")


def test_module_context_keeps_roots_ports_theme_and_runtime_explicit(tmp_path: Path):
    context = ModuleContext(
        project_root=tmp_path,
        working_root=tmp_path / "work",
        results_root=tmp_path / "results",
        ports={"shell": 9100},
        theme={"--pah-accent": "#123456"},
        runtime={"device": "cpu"},
    )
    snapshot = context.to_dict()
    assert snapshot["project_root"] == str(tmp_path.resolve())
    assert snapshot["ports"] == {"shell": 9100}
    assert snapshot["runtime"]["device"] == "cpu"
    with pytest.raises(ValueError, match="between 1 and 65535"):
        ModuleContext(ports={"bad": 70000})


def test_artifact_contract_matches_schema_without_knowing_domain_semantics():
    artifact = ArtifactRef(
        artifact_id="a1",
        kind="feature_dataset",
        producer_module="pypique",
        schema_id="pypique.operational-benchmark",
        schema_version="1",
        location="/tmp/benchmark.json",
        metadata={"observation": "raw_count"},
    )
    assert artifact.matches(ArtifactRequirement("feature_dataset", "pypique.operational-benchmark", "1"))
    assert not artifact.matches(ArtifactRequirement("representation"))


def test_lab_membership_is_collection_based_and_allows_one_module_in_multiple_labs():
    modules = ModuleRegistry((
        ModuleManifest(
            module_id="hsqa_dbn",
            display_name="HSQA_DBN",
            collections=("code_analysis_lab", "ml_lab"),
            capabilities=("representation_learning",),
        ),
    ))
    labs = default_lab_registry()
    code = labs.lab_snapshot("code_analysis_lab", modules)
    ml = labs.lab_snapshot("ml_lab", modules)
    assert [item["module_id"] for item in code["modules"]] == ["hsqa_dbn"]
    assert [item["module_id"] for item in ml["modules"]] == ["hsqa_dbn"]


def test_lab_orchestrator_resolves_capabilities_without_pairwise_imports():
    modules = ModuleRegistry((
        ModuleManifest(
            module_id="pypique",
            display_name="pyPIQUE",
            collections=("code_analysis_lab",),
            capabilities=("quality_modeling",),
        ),
    ))
    workflow = WorkflowManifest(
        workflow_id="quality",
        display_name="Quality workflow",
        steps=(WorkflowStep("quality", "Build quality model", "quality_modeling"),),
    )
    lab = LabManifest("code_analysis_lab", "Code Analysis Lab", workflows=(workflow,))
    resolution = LabOrchestrator(lab, modules).workflow_snapshot(workflow)
    assert resolution["resolution"][0]["state"] == "resolved"
    assert resolution["resolution"][0]["provider"]["module_id"] == "pypique"


def test_lab_orchestrator_reports_ambiguous_provider_instead_of_guessing():
    modules = ModuleRegistry((
        ModuleManifest("a", "A", collections=("lab",), capabilities=("representation",)),
        ModuleManifest("b", "B", collections=("lab",), capabilities=("representation",)),
    ))
    step = WorkflowStep("rep", "Representation", "representation")
    result = LabOrchestrator(LabManifest("lab", "Lab"), modules).resolve_step(step)
    assert result["state"] == "ambiguous"
    assert {item["module_id"] for item in result["providers"]} == {"a", "b"}


def test_duplicate_module_registration_requires_explicit_replace():
    registry = ModuleRegistry((ModuleManifest("demo", "Demo"),))
    with pytest.raises(RegistryError, match="already registered"):
        registry.register(ModuleManifest("demo", "Other"))
    registry.register(ModuleManifest("demo", "Other"), replace=True)
    assert registry.get("demo").display_name == "Other"


def test_default_catalog_uses_existing_ml_lab_collection_contract():
    labs = default_lab_registry()
    assert labs.get("ml_lab").display_name == "ML Lab"
    modules = default_module_registry(discover=False)
    assert modules.get("code_analyzer").belongs_to("code_analysis_lab")


def test_orchestration_http_endpoints_expose_collections_without_requiring_module_ui(tmp_path: Path):
    flask = pytest.importorskip("flask")
    from pah import create_app

    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    with app.test_client() as client:
        modules = client.get("/api/orchestration/modules")
        assert modules.status_code == 200
        module_payload = modules.get_json()
        assert module_payload["ok"] is True
        assert any(item["module_id"] == "code_analyzer" for item in module_payload["modules"])

        labs = client.get("/api/orchestration/labs")
        assert labs.status_code == 200
        lab_payload = labs.get_json()
        names = {item["lab_id"]: item for item in lab_payload["labs"]}
        assert "code_analysis_lab" in names
        assert "ml_lab" in names
        assert any(item["module_id"] == "code_analyzer" for item in names["code_analysis_lab"]["modules"])

        missing = client.get("/api/orchestration/labs/not-a-lab")
        assert missing.status_code == 404


def test_artifact_contract_carries_generic_routing_and_validation_metadata():
    artifact = ArtifactRef(
        artifact_id="representation-7",
        kind="representation",
        producer_module="hsqa_dbn",
        producer_version="0.4.0",
        project_id="project-a",
        session_id="session-2",
        created_at="2026-09-09T09:00:00Z",
        capabilities=("representation_learning",),
        parent_artifact_ids=("quality-4",),
        validation_state="valid",
    )
    payload = artifact.to_dict()
    assert payload["parent_artifact_ids"] == ["quality-4"]
    assert payload["capabilities"] == ["representation_learning"]
    assert artifact.matches(ArtifactRequirement(
        "representation",
        producer_module="hsqa_dbn",
        capability="representation_learning",
    ))


def test_workflow_step_can_declare_schema_validated_output_requirements():
    requirement = ArtifactRequirement(
        kind="representation_analysis",
        schema_id="hsqa_dbn.representation_analysis",
        schema_version="1",
        producer_module="hsqa_dbn",
        capability="mutual_information_analysis",
    )
    step = WorkflowStep(
        "latent",
        "Inspect latent information",
        "mutual_information_analysis",
        produces=("representation_analysis",),
        output_requirements=(requirement,),
    )
    payload = step.to_dict()
    assert payload["produces"] == ["representation_analysis"]
    assert payload["output_requirements"] == [requirement.to_dict()]
