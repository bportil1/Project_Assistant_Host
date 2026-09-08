from __future__ import annotations

from pathlib import Path

import pytest

from pah.contracts import ArtifactRef, ModuleManifest
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
    assert initial["quality_modeling"]["state"] == "ready"
    assert initial["representation_learning"]["state"] == "blocked"
    assert initial["latent_analysis"]["state"] == "blocked"

    inventory.register(ArtifactRef(
        artifact_id="benchmark",
        kind="feature_dataset",
        producer_module="pypique",
        location=str(tmp_path / "benchmark.json"),
        schema_id="pypique.operational-benchmark",
        schema_version="1",
    ))
    inventory.register(ArtifactRef(
        artifact_id="domain",
        kind="domain_mapping",
        producer_module="pypique",
        location=str(tmp_path / "domain.json"),
    ))
    inventory.register(ArtifactRef(
        artifact_id="quality",
        kind="quality_model",
        producer_module="pypique",
        location=str(tmp_path / "operational_model.json"),
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
