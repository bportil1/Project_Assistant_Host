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
            capabilities=("quality_modeling", "mi_informed_analysis", "mi_informed_modeling"),
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


def test_code_analysis_lab_catalog_contains_repository_workflow():
    assert CODE_ANALYSIS_LAB.workflows == (CODE_ANALYSIS_WORKFLOW,)
    assert [step.step_id for step in CODE_ANALYSIS_WORKFLOW.steps] == [
        "repository_analysis",
        "quality_modeling",
        "representation_analysis",
        "mi_informed_analysis",
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
    assert steps["representation_analysis"]["state"] == "missing_provider"
    assert steps["mi_informed_analysis"]["state"] == "missing_provider"
    assert snapshot["recommended_step"] == "quality_modeling"


def test_controller_advances_by_registered_artifacts_not_button_history(tmp_path: Path):
    inventory = ArtifactInventory()
    controller = CodeAnalysisLabController(_integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=inventory)

    initial = _steps(controller.snapshot())
    assert initial["repository_analysis"]["optional"] is True
    assert initial["quality_modeling"]["state"] == "ready"
    assert initial["quality_modeling"]["requirements"] == []
    assert initial["representation_analysis"]["state"] == "blocked"
    assert initial["mi_informed_analysis"]["state"] == "blocked"

    # Repository analysis is an optional side wing. Registering its output does
    # not gate or otherwise change pyPIQUE readiness.
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
    assert after_code["quality_modeling"]["requirements"] == []

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
    assert aligned["representation_analysis"]["state"] == "ready"
    assert aligned["representation_analysis"]["missing_requirements"] == []

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
    assert represented["representation_analysis"]["state"] == "ready"
    assert represented["representation_analysis"]["outputs"][0]["available"] is True
    assert represented["representation_analysis"]["outputs"][1]["available"] is False
    assert represented["mi_informed_analysis"]["state"] == "blocked"


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
    step = _steps(controller.snapshot())["representation_analysis"]
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
    step = _steps(controller.snapshot())["representation_analysis"]
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


def test_quality_modeling_execution_context_does_not_require_code_analysis(tmp_path: Path):
    controller = CodeAnalysisLabController(_integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=ArtifactInventory())
    module_id, context = controller.execution_context(
        "quality_modeling",
        ModuleContext(project_root=tmp_path, working_root=tmp_path, runtime={"state_dir": "state"}),
    )
    assert module_id == "pypique"
    assert context.runtime["pah_step"] == "quality_modeling"
    assert context.runtime["input_artifacts"] == {}
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
        "representation_analysis",
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
    assert steps["representation_analysis"]["state"] == "ready"
    assert steps["representation_analysis"]["outputs"][0]["available"] is False
    assert steps["mi_informed_analysis"]["state"] == "blocked"


def test_combined_hsqa_stage_requires_both_schema_valid_outputs():
    feature = ArtifactRef(
        artifact_id="feature", kind="feature_dataset", producer_module="pypique",
        schema_id="pah.feature-dataset.matrix", schema_version="1", validation_state="valid",
    )
    representation = ArtifactRef(
        artifact_id="representation", kind="representation", producer_module="hsqa_dbn",
        schema_id="hsqa_dbn.representation_bundle", schema_version="1",
        capabilities=("representation_learning",), validation_state="valid",
    )
    inventory = ArtifactInventory((feature, representation))
    controller = CodeAnalysisLabController(_integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=inventory)
    step = _steps(controller.snapshot())["representation_analysis"]
    assert step["state"] == "ready"
    assert [item["available"] for item in step["outputs"]] == [True, False]

    inventory.register(ArtifactRef(
        artifact_id="analysis-current", kind="representation_analysis", producer_module="hsqa_dbn",
        schema_id="hsqa_dbn.representation_analysis", schema_version="1",
        capabilities=("experiment_analysis", "mutual_information_analysis"),
        parent_artifact_ids=("representation",), validation_state="valid",
    ))
    step = _steps(controller.snapshot())["representation_analysis"]
    assert step["state"] == "complete"
    assert [item["available"] for item in step["outputs"]] == [True, True]


def test_mi_informed_stage_requires_neutral_information_network_and_routes_to_pypique():
    network = ArtifactRef(
        artifact_id="network", kind="information_network", producer_module="pah",
        schema_id="pah.information-network", schema_version="1", validation_state="valid",
    )
    controller = CodeAnalysisLabController(
        _integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=ArtifactInventory((network,))
    )
    step = _steps(controller.snapshot())["mi_informed_analysis"]
    assert step["state"] == "ready"
    module_id, context = controller.execution_context("mi_informed_analysis", ModuleContext())
    assert module_id == "pypique"
    assert context.runtime["input_artifacts"]["information_network"]["artifact_id"] == "network"
    assert "code_analysis" not in context.runtime["input_artifacts"]


def test_mi_informed_stage_only_completes_with_schema_valid_pypique_output():
    network = ArtifactRef(
        artifact_id="network", kind="information_network", producer_module="pah",
        schema_id="pah.information-network", schema_version="1", validation_state="valid",
    )
    wrong = ArtifactRef(
        artifact_id="wrong", kind="mi_informed_analysis", producer_module="pypique",
        schema_id="pypique.other", schema_version="1",
        capabilities=("mi_informed_analysis",), validation_state="valid",
    )
    inventory = ArtifactInventory((network, wrong))
    controller = CodeAnalysisLabController(_integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=inventory)
    assert _steps(controller.snapshot())["mi_informed_analysis"]["state"] == "ready"
    inventory.register(ArtifactRef(
        artifact_id="mi-current", kind="mi_informed_analysis", producer_module="pypique",
        schema_id="pypique.mi_informed_analysis", schema_version="1",
        capabilities=("mi_informed_analysis",), parent_artifact_ids=("network",), validation_state="valid",
    ))
    assert _steps(controller.snapshot())["mi_informed_analysis"]["state"] == "ready"
    inventory.register(ArtifactRef(
        artifact_id="mi-experiment", kind="mi_informed_model_experiment", producer_module="pypique",
        schema_id="pypique.mi_informed_model_experiment", schema_version="1",
        capabilities=("mi_informed_modeling",), parent_artifact_ids=("network",), validation_state="valid",
    ))
    inventory.register(ArtifactRef(
        artifact_id="mi-model", kind="mi_informed_quality_model", producer_module="pypique",
        schema_id="pypique.mi_informed_quality_model", schema_version="1",
        capabilities=("mi_informed_modeling",), parent_artifact_ids=("network",), validation_state="valid",
    ))
    step = _steps(controller.snapshot())["mi_informed_analysis"]
    assert step["state"] == "complete"
    assert [item["available"] for item in step["outputs"]] == [True, True, True]


def test_information_network_preserves_mi_correlation_sign_and_signed_pmi(tmp_path: Path):
    import csv
    import json
    from pah.labs.information_network import build_information_network

    vis = tmp_path / "vis_data"
    vis.mkdir()
    (vis / "dataset_metadata.json").write_text(json.dumps({
        "dataset_name": "fixture",
        "domain": "software_security",
        "semantic_adapter": "cwe",
        "features": [
            {"index": 0, "id": "CWE-1", "label": "CWE-1", "groups": ["Conf"]},
            {"index": 1, "id": "CWE-2", "label": "CWE-2", "groups": ["Int"]},
        ],
    }) + "\n", encoding="utf-8")
    (vis / "nodes.csv").write_text(
        "raw_layer,node_idx,x,y,label\n0,0,0,0,0\n0,1,1,0,0\n1,0,0,1,1\n2,0,0,2,2\n",
        encoding="utf-8",
    )
    (vis / "scope_index.csv").write_text("idx,scope\n0,Conf\n", encoding="utf-8")
    (vis / "edges_pos.csv").write_text(
        "src_layer,src_idx,tgt_layer,tgt_idx,weight\n0,0,1,0,0.7\n",
        encoding="utf-8",
    )
    (vis / "edges_neg.csv").write_text(
        "src_layer,src_idx,tgt_layer,tgt_idx,weight\n0,1,1,0,-0.6\n",
        encoding="utf-8",
    )
    (vis / "contributions_pos.csv").write_text("layer,node,scope,val\n1,0,Conf,0.4\n", encoding="utf-8")
    (vis / "contributions_neg.csv").write_text("layer,node,scope,val\n1,0,Int,-0.2\n", encoding="utf-8")

    dep = tmp_path / "input_dependency"
    dep.mkdir()
    for name, rows in {
        "pearson_visible_visible.csv": [[1.0, -0.8], [-0.8, 1.0]],
        "spearman_visible_visible.csv": [[1.0, -0.7], [-0.7, 1.0]],
        "mi_visible_visible.csv": [[0.0, 0.55], [0.55, 0.0]],
    }.items():
        with (dep / name).open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerows(rows)

    manifest = tmp_path / "representation_analysis.json"
    manifest.write_text(json.dumps({
        "schema": "hsqa_dbn.representation_analysis",
        "schema_version": 1,
        "artifacts": {"visualizer_data": str(vis), "visible_dependency": str(dep)},
    }) + "\n", encoding="utf-8")
    source = ArtifactRef(
        artifact_id="hsqa-analysis", kind="representation_analysis", producer_module="hsqa_dbn",
        location=str(manifest), schema_id="hsqa_dbn.representation_analysis", schema_version="1",
        capabilities=("mutual_information_analysis",), parent_artifact_ids=("representation",),
        validation_state="valid",
    )
    artifact = build_information_network(source, output_path=tmp_path / "information_network.json")
    assert artifact.validation_state == "valid"
    payload = json.loads(Path(artifact.location).read_text(encoding="utf-8"))
    dependency = next(edge for edge in payload["edges"] if edge["relationship"] == "feature_dependency")
    assert dependency["mutual_information"] == 0.55
    assert dependency["pearson"] == -0.8
    assert dependency["correlation_sign"] == "opposing"
    signed = [edge for edge in payload["edges"] if edge["relationship"] == "signed_information"]
    assert {edge["signed_score"] for edge in signed} == {0.7, -0.6}
    assert all(edge["metric"] == "normalized_pmi" for edge in signed)


def test_artifact_registry_preserves_immutable_file_history_and_persists_selection(tmp_path: Path):
    state_path = tmp_path / "state" / "artifact-registry.json"
    source = tmp_path / "feature_dataset.json"
    source.write_text('{"version": 1}\n', encoding="utf-8")
    registry = ArtifactInventory(state_path=state_path)

    alias1, snapshot1 = registry.register_current(ArtifactRef(
        artifact_id="pypique-feature-dataset-current",
        kind="feature_dataset",
        producer_module="pypique",
        location=str(source),
        schema_id="pah.feature-dataset.matrix",
        schema_version="1",
        project_id=str(tmp_path),
        validation_state="valid",
        metadata={"runtime_managed": True},
    ))
    assert alias1.metadata["registry_alias"] is True
    assert snapshot1.metadata["history_snapshot"] is True
    assert Path(snapshot1.location).read_text(encoding="utf-8") == '{"version": 1}\n'

    source.write_text('{"version": 2}\n', encoding="utf-8")
    alias2, snapshot2 = registry.register_current(ArtifactRef(
        artifact_id="pypique-feature-dataset-current",
        kind="feature_dataset",
        producer_module="pypique",
        location=str(source),
        schema_id="pah.feature-dataset.matrix",
        schema_version="1",
        project_id=str(tmp_path),
        validation_state="valid",
        metadata={"runtime_managed": True},
    ))
    assert snapshot2.artifact_id != snapshot1.artifact_id
    assert registry.get(snapshot1.artifact_id).metadata["superseded"] is True
    assert registry.resolve_alias(alias2.artifact_id) == snapshot2.artifact_id
    assert Path(snapshot1.location).read_text(encoding="utf-8") == '{"version": 1}\n'
    assert Path(snapshot2.location).read_text(encoding="utf-8") == '{"version": 2}\n'

    registry.select(
        project_id=str(tmp_path),
        workflow_id=CODE_ANALYSIS_WORKFLOW.workflow_id,
        step_id="representation_analysis",
        kind="feature_dataset",
        artifact_id=snapshot1.artifact_id,
    )
    restored = ArtifactInventory(state_path=state_path)
    assert restored.get(snapshot1.artifact_id) is not None
    assert restored.get(snapshot2.artifact_id) is not None
    assert restored.selected_id(
        project_id=str(tmp_path),
        workflow_id=CODE_ANALYSIS_WORKFLOW.workflow_id,
        step_id="representation_analysis",
        kind="feature_dataset",
    ) == snapshot1.artifact_id


def test_historical_input_selection_routes_branch_and_marks_current_descendants_stale(tmp_path: Path):
    context = ModuleContext(project_root=tmp_path, working_root=tmp_path)
    registry = ArtifactInventory(state_path=tmp_path / "state" / "artifact-registry.json")
    feature_path = tmp_path / "feature.json"
    feature_path.write_text('{"dataset": "A"}\n', encoding="utf-8")
    _, feature_a = registry.register_current(ArtifactRef(
        artifact_id="pypique-feature-dataset-current",
        kind="feature_dataset",
        producer_module="pypique",
        location=str(feature_path),
        schema_id="pah.feature-dataset.matrix",
        schema_version="1",
        project_id=str(tmp_path),
        validation_state="valid",
        metadata={"runtime_managed": True},
    ))
    _, representation_a = registry.register_current(ArtifactRef(
        artifact_id="hsqa-dbn-representation-current",
        kind="representation",
        producer_module="hsqa_dbn",
        schema_id="hsqa_dbn.representation_bundle",
        schema_version="1",
        project_id=str(tmp_path),
        capabilities=("representation_learning",),
        parent_artifact_ids=("pypique-feature-dataset-current",),
        validation_state="valid",
        metadata={"runtime_managed": True},
    ))
    registry.register_current(ArtifactRef(
        artifact_id="hsqa-dbn-representation-analysis-current",
        kind="representation_analysis",
        producer_module="hsqa_dbn",
        schema_id="hsqa_dbn.representation_analysis",
        schema_version="1",
        project_id=str(tmp_path),
        capabilities=("mutual_information_analysis",),
        parent_artifact_ids=("hsqa-dbn-representation-current",),
        validation_state="valid",
        metadata={"runtime_managed": True},
    ))

    controller = CodeAnalysisLabController(_integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=registry)
    assert _steps(controller.snapshot(context=context))["representation_analysis"]["state"] == "complete"

    feature_path.write_text('{"dataset": "B"}\n', encoding="utf-8")
    _, feature_b = registry.register_current(ArtifactRef(
        artifact_id="pypique-feature-dataset-current",
        kind="feature_dataset",
        producer_module="pypique",
        location=str(feature_path),
        schema_id="pah.feature-dataset.matrix",
        schema_version="1",
        project_id=str(tmp_path),
        validation_state="valid",
        metadata={"runtime_managed": True},
    ))
    assert feature_b.artifact_id != feature_a.artifact_id
    stale = _steps(controller.snapshot(context=context))["representation_analysis"]
    assert stale["state"] == "stale"
    assert stale["outputs"][0]["stale_artifacts"]

    selection = controller.select_input(
        "representation_analysis", "feature_dataset", feature_a.artifact_id, context=context
    )
    assert selection["selection_mode"] == "pinned"
    branched = _steps(controller.snapshot(context=context))["representation_analysis"]
    assert branched["state"] == "complete"
    assert branched["branch_mode"] is True
    assert branched["requirements"][0]["selected_artifact_id"] == feature_a.artifact_id

    module_id, launch_context = controller.execution_context("representation_analysis", context)
    assert module_id == "hsqa_dbn"
    selected = launch_context.runtime["input_artifacts"]["feature_dataset"]
    assert selected["artifact_id"] == feature_a.artifact_id
    assert Path(selected["location"]).read_text(encoding="utf-8") == '{"dataset": "A"}\n'

    controller.select_input("representation_analysis", "feature_dataset", None, context=context)
    current = _steps(controller.snapshot(context=context))["representation_analysis"]
    assert current["state"] == "stale"
    assert current["requirements"][0]["selection_mode"] == "current"


def test_mi_informed_execution_context_requests_focused_pypique_view():
    code = ArtifactRef(
        artifact_id="code-focus", kind="code_analysis", producer_module="code_analyzer",
        schema_id="pah.code-analysis.current", schema_version="1", validation_state="valid",
    )
    network = ArtifactRef(
        artifact_id="network-focus", kind="information_network", producer_module="pah",
        schema_id="pah.information-network", schema_version="1", validation_state="valid",
    )
    controller = CodeAnalysisLabController(
        _integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=ArtifactInventory((code, network))
    )
    module_id, context = controller.execution_context("mi_informed_analysis", ModuleContext())
    assert module_id == "pypique"
    assert context.runtime["requested_view"] == "mi-informed"
    assert context.runtime["focused_view"] is True


def test_representation_output_reports_registered_but_invalid_provider_artifact(tmp_path: Path):
    feature = ArtifactRef(
        artifact_id="feature-current",
        kind="feature_dataset",
        producer_module="pypique",
        location=str(tmp_path / "feature.json"),
        schema_id="pah.feature-dataset.matrix",
        schema_version="1",
        validation_state="valid",
    )
    invalid_representation = ArtifactRef(
        artifact_id="hsqa-dbn-representation-current",
        kind="representation",
        producer_module="hsqa_dbn",
        location=str(tmp_path / "representation_bundle"),
        schema_id="hsqa_dbn.representation_bundle",
        schema_version="1",
        capabilities=("representation_learning",),
        parent_artifact_ids=("feature-current",),
        validation_state="invalid",
        validation_errors=("representation bundle was trained from a different feature dataset",),
        metadata={"runtime_managed": True},
    )
    inventory = ArtifactInventory((feature, invalid_representation))
    controller = CodeAnalysisLabController(_integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=inventory)
    step = _steps(controller.snapshot())["representation_analysis"]
    output = next(item for item in step["outputs"] if item["kind"] == "representation")
    assert output["available"] is False
    assert len(output["invalid_artifacts"]) == 1
    assert "different feature dataset" in output["invalid_artifacts"][0]["validation_errors"][0]


def test_representation_execution_context_exposes_feature_dataset_history_to_provider(tmp_path: Path):
    current = ArtifactRef(
        artifact_id="feature-current",
        kind="feature_dataset",
        producer_module="pypique",
        location=str(tmp_path / "current.json"),
        schema_id="pah.feature-dataset.matrix",
        schema_version="1",
        validation_state="valid",
        created_at="2026-09-15T00:00:00+00:00",
    )
    historical = ArtifactRef(
        artifact_id="feature-history-123",
        kind="feature_dataset",
        producer_module="pypique",
        location=str(tmp_path / "history.json"),
        schema_id="pah.feature-dataset.matrix",
        schema_version="1",
        validation_state="valid",
        created_at="2026-09-10T00:00:00+00:00",
        metadata={"history_snapshot": True, "history_selectable": True},
    )
    controller = CodeAnalysisLabController(
        _integrated_modules(),
        lab=CODE_ANALYSIS_LAB,
        artifacts=ArtifactInventory((current, historical)),
    )
    module_id, context = controller.execution_context("representation_analysis", ModuleContext(project_root=tmp_path))
    assert module_id == "hsqa_dbn"
    assert context.runtime["input_artifacts"]["feature_dataset"]["artifact_id"] == "feature-current"
    history = context.runtime["artifact_history"]["feature_dataset"]
    assert [item["artifact_id"] for item in history] == ["feature-history-123"]



def test_old_host_findings_artifact_does_not_become_a_hidden_quality_input(tmp_path: Path):
    imported = ArtifactRef(
        artifact_id="pah-findings-feature-dataset-current",
        kind="feature_dataset",
        producer_module="pah",
        schema_id="pah.feature-dataset.matrix",
        schema_version="1",
        project_id=str(tmp_path),
        validation_state="valid",
    )
    controller = CodeAnalysisLabController(
        _integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=ArtifactInventory((imported,))
    )
    context = ModuleContext(project_root=tmp_path, working_root=tmp_path)
    steps = _steps(controller.snapshot(context=context))
    assert steps["quality_modeling"]["state"] == "ready"
    assert steps["quality_modeling"]["requirements"] == []
    # Downstream HSQA still requires the canonical pyPIQUE-produced feature dataset.
    assert steps["representation_analysis"]["state"] == "blocked"


def test_repository_analysis_is_optional_and_not_routed_into_pypique(tmp_path: Path):
    code = ArtifactRef(
        artifact_id="code-analyzer-current",
        kind="code_analysis",
        producer_module="code_analyzer",
        location=str(tmp_path),
        schema_id="pah.code-analysis.current",
        schema_version="1",
        project_id=str(tmp_path),
        validation_state="valid",
    )
    controller = CodeAnalysisLabController(
        _integrated_modules(), lab=CODE_ANALYSIS_LAB, artifacts=ArtifactInventory((code,))
    )
    context = ModuleContext(project_root=tmp_path, working_root=tmp_path)
    step = _steps(controller.snapshot(context=context))["quality_modeling"]
    assert step["state"] == "ready"
    assert step["requirements"] == []
    _, launch_context = controller.execution_context("quality_modeling", context)
    assert launch_context.runtime["input_artifacts"] == {}
