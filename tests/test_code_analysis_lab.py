from __future__ import annotations

from pathlib import Path

import pytest

from pah.contracts import ArtifactRef, ModuleContext, ModuleManifest
from pah.labs import (
    ArtifactInventory,
    CODE_ANALYSIS_LAB,
    CODE_ANALYSIS_WORKFLOW,
    CodeAnalysisLabController,
    ModuleRegistry,
)
from pah.module_catalog import default_module_registry


def _integrated_modules() -> ModuleRegistry:
    return ModuleRegistry((
        ModuleManifest(
            module_id="code_analyzer",
            display_name="Code Analyzer",
            collections=("code_analysis_lab",),
            capabilities=("static_analysis",),
            interfaces=("callable_api", "embedded_ui"),
        ),
        ModuleManifest(
            module_id="pypique",
            display_name="pyPIQUE",
            collections=("code_analysis_lab",),
            capabilities=("quality_modeling",),
            interfaces=("callable_api", "standalone_ui"),
        ),
        ModuleManifest(
            module_id="hsqa_dbn",
            display_name="EBM / DBN Analysis Lab",
            collections=("code_analysis_lab", "ml_lab"),
            capabilities=("representation_learning", "mutual_information_analysis"),
            interfaces=("callable_api", "standalone_ui"),
        ),
    ))


def _steps(snapshot):
    return {step["step_id"]: step for step in snapshot["workflow"]["steps"]}


def test_code_analysis_lab_catalog_contains_real_workflow():
    assert CODE_ANALYSIS_LAB.workflows == (CODE_ANALYSIS_WORKFLOW,)
    assert [step.step_id for step in CODE_ANALYSIS_WORKFLOW.steps] == [
        "repository_analysis",
        "quality_modeling",
        "representation_learning",
        "latent_analysis",
    ]


def test_controller_reports_unregistered_scientific_modules_without_importing_them():
    modules = default_module_registry(discover=False)
    controller = CodeAnalysisLabController(modules, lab=CODE_ANALYSIS_LAB)
    snapshot = controller.snapshot()
    expected = {item["module_id"]: item for item in snapshot["expected_modules"]}
    assert expected["code_analyzer"]["registered"] is True
    assert expected["pypique"]["registered"] is False
    assert expected["hsqa_dbn"]["registered"] is False
    steps = _steps(snapshot)
    assert steps["repository_analysis"]["state"] == "ready"
    assert steps["quality_modeling"]["state"] == "missing_provider"
    assert steps["representation_learning"]["state"] == "missing_provider"
    assert snapshot["recommended_step"] == "quality_modeling"


def test_controller_advances_by_registered_artifacts_not_button_history(tmp_path: Path):
    inventory = ArtifactInventory()
    controller = CodeAnalysisLabController(_integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=inventory)

    initial = _steps(controller.snapshot())
    assert initial["quality_modeling"]["state"] == "blocked"
    assert initial["quality_modeling"]["blocking_reason"] == (
        "Missing required artifact: code_analysis (from code_analyzer, schema pah.code-analysis.current@1)."
    )
    assert initial["representation_learning"]["state"] == "blocked"
    assert initial["latent_analysis"]["state"] == "blocked"

    inventory.register(ArtifactRef(
        artifact_id="code",
        kind="code_analysis",
        producer_module="code_analyzer",
        location=str(tmp_path),
        schema_id="pah.code-analysis.current",
        schema_version="1",
        validation_state="valid",
    ))
    after_code = _steps(controller.snapshot())
    assert after_code["quality_modeling"]["state"] == "ready"

    inventory.register(ArtifactRef(
        artifact_id="benchmark",
        kind="feature_dataset",
        producer_module="pypique",
        location=str(tmp_path / "benchmark.json"),
        schema_id="pah.feature-dataset.matrix",
        schema_version="1",
    ))
    inventory.register(ArtifactRef(
        artifact_id="domain",
        kind="domain_mapping",
        producer_module="pypique",
        location=str(tmp_path / "domain.json"),
        schema_id="pah.domain-mapping.feature-groups",
        schema_version="1",
    ))
    inventory.register(ArtifactRef(
        artifact_id="quality",
        kind="quality_model",
        producer_module="pypique",
        location=str(tmp_path / "operational_model.json"),
    ))
    inventory.register(ArtifactRef(
        artifact_id="evaluation",
        kind="quality_evaluation",
        producer_module="pypique",
        location=str(tmp_path / "evaluation.json"),
    ))

    aligned = _steps(controller.snapshot())
    assert aligned["quality_modeling"]["state"] == "complete"
    assert aligned["representation_learning"]["state"] == "ready"
    assert aligned["representation_learning"]["missing_requirements"] == []

    inventory.register(ArtifactRef(
        artifact_id="representation",
        kind="representation",
        producer_module="hsqa_dbn",
        location=str(tmp_path / "representation_bundle"),
        schema_id="hsqa_dbn.representation_bundle",
        schema_version="1",
        capabilities=("representation_learning",),
    ))
    represented = _steps(controller.snapshot())
    assert represented["representation_learning"]["state"] == "complete"
    assert represented["latent_analysis"]["state"] == "ready"


def test_optional_domain_mapping_does_not_block_representation(tmp_path: Path):
    inventory = ArtifactInventory((ArtifactRef(
        artifact_id="benchmark",
        kind="feature_dataset",
        producer_module="pypique",
        location=str(tmp_path / "benchmark.json"),
        schema_id="pah.feature-dataset.matrix",
        schema_version="1",
    ),))
    controller = CodeAnalysisLabController(_integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=inventory)
    step = _steps(controller.snapshot())["representation_learning"]
    assert step["state"] == "ready"
    domain = next(item for item in step["requirements"] if item["kind"] == "domain_mapping")
    assert domain["optional"] is True
    assert domain["satisfied"] is True


def test_artifact_inventory_matches_generic_contracts():
    inventory = ArtifactInventory()
    artifact = ArtifactRef("a", "feature_dataset", "pypique")
    inventory.register(artifact)
    assert inventory.by_kind("feature_dataset") == (artifact,)
    assert inventory.remove("a") == artifact
    assert inventory.all() == ()


def test_code_analysis_http_endpoint_exposes_workflow_and_expected_modules(tmp_path: Path):
    pytest.importorskip("flask")
    from pah import create_app

    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    with app.test_client() as client:
        response = client.get("/api/orchestration/code-analysis")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        assert payload["lab"]["lab_id"] == "code_analysis_lab"
        assert payload["workflow"]["workflow_id"] == "code_analysis_research"
        expected_ids = {item["module_id"] for item in payload["expected_modules"]}
        assert expected_ids == {"code_analyzer", "pypique", "hsqa_dbn"}


def test_code_analysis_lab_frontend_contract_is_host_owned_and_collapsible():
    root = Path(__file__).resolve().parents[1]
    template = (root / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    css = (root / "pah" / "web" / "static" / "pah-labs.css").read_text(encoding="utf-8")
    js = (root / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")
    assert 'id="labsMenu"' in template
    assert 'id="codeAnalysisLabMode"' in template
    assert 'id="codeAnalysisLabRail"' in template
    assert ".lab-workflow-rail.collapsed" in css
    assert "/api/orchestration/code-analysis" in js
    assert "/api/orchestration/code-analysis/steps/${encodeURIComponent(stepId)}/launch" in js
    assert "openCodeAnalysisLab" in js


def test_code_analysis_lab_exposes_generic_runtime_status_without_host_surface_metadata():
    from pah.runtime import RuntimeRegistry

    class Runtime:
        module_id = "code_analyzer"

        def status(self, *, context=None):
            return {"module_id": self.module_id, "available": True, "running": False, "launchable": True}

        def launch(self, *, context=None, detached=False):
            return {"module_id": self.module_id, "launched": True}

    controller = CodeAnalysisLabController(
        _integrated_modules(),
        lab=CODE_ANALYSIS_LAB,
        runtimes=RuntimeRegistry((Runtime(),)),
    )
    snapshot = controller.snapshot()
    expected = {item["module_id"]: item for item in snapshot["expected_modules"]}
    assert expected["code_analyzer"]["runtime"]["launchable"] is True
    step = _steps(snapshot)["repository_analysis"]
    assert step["resolution"]["provider"]["runtime"]["launchable"] is True


def test_labs_navigation_replaces_analysis_launcher_in_same_position():
    root = Path(__file__).resolve().parents[1]
    template = (root / "pah" / "web" / "templates" / "index.html").read_text(encoding="utf-8")
    js = (root / "pah" / "web" / "static" / "pah.js").read_text(encoding="utf-8")
    workspace_pos = template.index('data-mode="workspace"')
    labs_pos = template.index('id="labsMenuToggle"')
    documents_pos = template.index('data-tool-launcher="documents"')
    assert workspace_pos < labs_pos < documents_pos
    assert 'data-tool-launcher="analysis"' not in template
    assert '>Analysis</button>' not in template
    # The underlying surface remains available through generic runtime launch.
    assert 'id="analysisMode"' in template
    assert '/api/orchestration/modules/${encodeURIComponent(moduleId)}/launch' in js
    assert 'provider.metadata?.host_surface' not in js


def test_artifact_registry_queries_provenance_and_dependencies():
    inventory = ArtifactInventory()
    source = ArtifactRef(
        artifact_id="source",
        kind="feature_dataset",
        producer_module="pypique",
        capabilities=("quality_modeling",),
        validation_state="valid",
    )
    representation = ArtifactRef(
        artifact_id="representation",
        kind="representation",
        producer_module="hsqa_dbn",
        parent_artifact_ids=("source",),
        capabilities=("representation_learning",),
        validation_state="valid",
    )
    inventory.register(source)
    inventory.register(representation)

    assert inventory.get("source") == source
    assert inventory.by_producer("pypique") == (source,)
    assert inventory.by_capability("representation_learning") == (representation,)
    assert inventory.dependencies("representation") == (source,)
    assert inventory.dependents("source") == (representation,)
    assert inventory.registry_snapshot()["summary"]["by_producer"] == {"hsqa_dbn": 1, "pypique": 1}


def test_invalid_artifact_does_not_satisfy_workflow_requirement():
    inventory = ArtifactInventory((ArtifactRef(
        artifact_id="invalid-benchmark",
        kind="feature_dataset",
        producer_module="pypique",
        schema_id="pah.feature-dataset.matrix",
        schema_version="1",
        validation_state="invalid",
        validation_errors=("missing feature names",),
    ),))
    controller = CodeAnalysisLabController(_integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=inventory)
    step = _steps(controller.snapshot())["representation_learning"]
    assert step["state"] == "blocked"
    assert step["missing_requirements"][0]["producer_module"] == "pypique"
    assert step["blocking_reason"] == (
        "Missing required artifact: feature_dataset (from pypique, schema pah.feature-dataset.matrix@1)."
    )


def test_artifact_http_registry_accepts_registered_producer_and_exposes_summary(tmp_path: Path):
    pytest.importorskip("flask")
    from pah import create_app

    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    registry = app.extensions["pah_module_registry"]
    registry.register(ModuleManifest(
        module_id="pypique",
        display_name="pyPIQUE",
        collections=("code_analysis_lab",),
        capabilities=("quality_modeling",),
    ), replace=True)

    with app.test_client() as client:
        created = client.post("/api/orchestration/artifacts", json={
            "artifact_id": "benchmark",
            "kind": "feature_dataset",
            "producer_module": "pypique",
            "capabilities": ["quality_modeling"],
            "validation_state": "valid",
        })
        assert created.status_code == 201

        listing = client.get("/api/orchestration/artifacts").get_json()
        assert listing["summary"]["total"] == 1
        assert listing["summary"]["by_kind"] == {"feature_dataset": 1}

        fetched = client.get("/api/orchestration/artifacts/benchmark").get_json()
        assert fetched["artifact"]["producer_module"] == "pypique"


def test_step_execution_context_routes_required_artifact_to_provider(tmp_path: Path):
    inventory = ArtifactInventory((ArtifactRef(
        artifact_id="code-analyzer-current",
        kind="code_analysis",
        producer_module="code_analyzer",
        location=str(tmp_path),
        schema_id="pah.code-analysis.current",
        schema_version="1",
        validation_state="valid",
    ),))
    controller = CodeAnalysisLabController(_integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=inventory)
    module_id, context = controller.execution_context(
        "quality_modeling",
        ModuleContext(project_root=tmp_path, working_root=tmp_path, runtime={"state_dir": "state"}),
    )
    assert module_id == "pypique"
    assert context.runtime["pah_step"] == "quality_modeling"
    assert context.runtime["input_artifacts"]["code_analysis"]["artifact_id"] == "code-analyzer-current"
    assert context.runtime["state_dir"] == "state"


def test_runtime_registry_optional_artifact_provider_boundary(tmp_path: Path):
    from pah.runtime import RuntimeRegistry

    class Runtime:
        module_id = "pypique"
        def status(self, *, context=None):
            return {"module_id": self.module_id, "available": True, "launchable": True}
        def launch(self, *, context=None, detached=False):
            return {"module_id": self.module_id, "launched": True}
        def artifacts(self, *, context=None):
            return ({
                "artifact_id": "eval",
                "kind": "quality_evaluation",
                "producer_module": "pypique",
                "location": str(tmp_path / "evaluation.json"),
            },)

    registry = RuntimeRegistry((Runtime(),))
    artifacts = registry.artifacts("pypique", ModuleContext(project_root=tmp_path))
    assert artifacts is not None
    assert artifacts[0]["kind"] == "quality_evaluation"
    assert registry.artifacts("missing") is None


def test_representation_execution_context_routes_neutral_pypique_handoff(tmp_path: Path):
    inventory = ArtifactInventory((
        ArtifactRef(
            artifact_id="feature",
            kind="feature_dataset",
            producer_module="pypique",
            location=str(tmp_path / "feature_dataset.json"),
            schema_id="pah.feature-dataset.matrix",
            schema_version="1",
            validation_state="valid",
        ),
        ArtifactRef(
            artifact_id="domain",
            kind="domain_mapping",
            producer_module="pypique",
            location=str(tmp_path / "domain_mapping.json"),
            schema_id="pah.domain-mapping.feature-groups",
            schema_version="1",
            validation_state="valid",
        ),
    ))
    controller = CodeAnalysisLabController(_integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=inventory)
    module_id, context = controller.execution_context(
        "representation_learning",
        ModuleContext(project_root=tmp_path, working_root=tmp_path),
    )
    assert module_id == "hsqa_dbn"
    assert context.runtime["input_artifacts"]["feature_dataset"]["artifact_id"] == "feature"
    assert context.runtime["input_artifacts"]["domain_mapping"]["artifact_id"] == "domain"


def test_invalid_representation_output_does_not_complete_learning_step(tmp_path: Path):
    inventory = ArtifactInventory((
        ArtifactRef(
            artifact_id="feature",
            kind="feature_dataset",
            producer_module="pypique",
            schema_id="pah.feature-dataset.matrix",
            schema_version="1",
            validation_state="valid",
        ),
        ArtifactRef(
            artifact_id="bad-representation",
            kind="representation",
            producer_module="hsqa_dbn",
            schema_id="hsqa_dbn.representation_bundle",
            schema_version="1",
            capabilities=("representation_learning",),
            validation_state="invalid",
            validation_errors=("stale dataset",),
        ),
    ))
    controller = CodeAnalysisLabController(_integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=inventory)
    steps = _steps(controller.snapshot())
    assert steps["representation_learning"]["state"] == "ready"
    assert steps["representation_learning"]["outputs"][0]["available"] is False
    assert steps["latent_analysis"]["state"] == "blocked"


def test_latent_analysis_requires_schema_valid_hsqa_representation(tmp_path: Path):
    inventory = ArtifactInventory((ArtifactRef(
        artifact_id="representation",
        kind="representation",
        producer_module="hsqa_dbn",
        schema_id="hsqa_dbn.representation_bundle",
        schema_version="1",
        capabilities=("representation_learning",),
        validation_state="valid",
    ),))
    controller = CodeAnalysisLabController(_integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=inventory)
    latent = _steps(controller.snapshot())["latent_analysis"]
    assert latent["state"] == "ready"
    requirement = latent["requirements"][0]
    assert requirement["schema_id"] == "hsqa_dbn.representation_bundle"
    assert requirement["schema_version"] == "1"
    assert requirement["capability"] == "representation_learning"


def test_latent_analysis_only_completes_with_schema_valid_hsqa_analysis():
    representation = ArtifactRef(
        artifact_id="representation",
        kind="representation",
        producer_module="hsqa_dbn",
        schema_id="hsqa_dbn.representation_bundle",
        schema_version="1",
        capabilities=("representation_learning",),
        validation_state="valid",
    )
    wrong = ArtifactRef(
        artifact_id="analysis-wrong",
        kind="representation_analysis",
        producer_module="hsqa_dbn",
        schema_id="hsqa_dbn.other_analysis",
        schema_version="1",
        capabilities=("mutual_information_analysis",),
        validation_state="valid",
    )
    inventory = ArtifactInventory((representation, wrong))
    controller = CodeAnalysisLabController(_integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=inventory)
    latent = _steps(controller.snapshot())["latent_analysis"]
    assert latent["state"] == "ready"
    assert latent["outputs"][0]["available"] is False
    assert latent["outputs"][0]["requirement"]["schema_id"] == "hsqa_dbn.representation_analysis"

    inventory.register(ArtifactRef(
        artifact_id="analysis-current",
        kind="representation_analysis",
        producer_module="hsqa_dbn",
        schema_id="hsqa_dbn.representation_analysis",
        schema_version="1",
        capabilities=("experiment_analysis", "mutual_information_analysis"),
        parent_artifact_ids=("representation",),
        validation_state="valid",
    ))
    latent = _steps(controller.snapshot())["latent_analysis"]
    assert latent["state"] == "complete"
    assert latent["outputs"][0]["available"] is True
