from __future__ import annotations

import json
from pathlib import Path

import pytest

from pah.labs.precomputed_dataset import (
    PrecomputedDatasetError,
    inspect_findings_table,
    materialize_findings_matrix,
)


def test_findings_import_preserves_matrix_and_materializes_neutral_and_hsqa_contracts(tmp_path: Path):
    source = tmp_path / "nist.csv"
    source.write_text("project,CWE-79,CWE-89\nalpha,2,0\nbeta,1,3\n", encoding="utf-8")
    inspection = inspect_findings_table(source)
    assert inspection["valid"] is True
    assert inspection["suggested_id_column"] == "project"
    assert inspection["feature_columns"] == ["CWE-79", "CWE-89"]

    findings_path, findings, feature_path, feature, metadata = materialize_findings_matrix(
        source, output_root=tmp_path / "managed", dataset_name="nist-sard"
    )
    assert findings_path.is_file() and feature_path.is_file()
    assert findings["schema"] == "pah.findings-matrix"
    assert findings["sample_ids"] == ["alpha", "beta"]
    assert findings["feature_ids"] == ["CWE-79", "CWE-89"]
    assert findings["values"] == [[2, 0], [1, 3]]
    assert findings["metadata"]["transformations"] == []
    assert feature["schema"] == "pah.feature-dataset.matrix"
    assert feature["source_type"] == "existing_findings"
    assert feature["values"] == findings["values"]
    assert feature["metadata"]["repository_analysis_bypassed"] is True
    assert feature["metadata"]["pypique_acquisition_bypassed"] is True
    assert metadata["source_type"] == "existing_findings"
    assert json.loads(findings_path.read_text(encoding="utf-8"))["values"] == [[2, 0], [1, 3]]


def test_findings_import_can_use_generated_ids(tmp_path: Path):
    source = tmp_path / "matrix.tsv"
    source.write_text("CWE-1\tCWE-2\n1\t2\n3\t4\n", encoding="utf-8")
    _, findings, _, feature, _ = materialize_findings_matrix(
        source, output_root=tmp_path / "managed", id_column="__generated__"
    )
    assert findings["sample_ids"] == ["sample-1", "sample-2"]
    assert feature["sample_ids"] == ["sample-1", "sample-2"]


def test_findings_import_rejects_non_numeric_feature_instead_of_cleaning_it(tmp_path: Path):
    source = tmp_path / "bad.csv"
    source.write_text("id,CWE-1\na,1\nb,not-a-number\n", encoding="utf-8")
    inspection = inspect_findings_table(source)
    assert inspection["valid"] is False
    assert any("not numeric" in error for error in inspection["errors"])
    with pytest.raises(PrecomputedDatasetError):
        materialize_findings_matrix(source, output_root=tmp_path / "managed")


def test_existing_findings_http_import_is_independent_from_repository_workflow(tmp_path: Path):
    pytest.importorskip("flask")
    from pah import create_app

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "nist.csv"
    source.write_text("project,CWE-79,CWE-89\nalpha,2,0\nbeta,1,3\n", encoding="utf-8")

    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    with app.test_client() as client:
        opened = client.post("/api/workspace/open", json={"path": str(workspace)})
        assert opened.status_code == 200
        imported = client.post("/api/orchestration/findings/import", json={
            "path": str(source), "dataset_name": "nist-sard", "id_column": "project",
        })
        assert imported.status_code == 201
        payload = imported.get_json()
        assert payload["findings_matrix"]["schema_id"] == "pah.findings-matrix"
        assert payload["feature_dataset"]["schema_id"] == "pah.feature-dataset.matrix"
        assert payload["feature_dataset"]["producer_module"] == "pah"
        assert payload["dataset"]["active"]["metadata"]["dataset_name"] == "nist-sard"

        repository = client.get("/api/orchestration/code-analysis").get_json()
        quality = next(step for step in repository["workflow"]["steps"] if step["step_id"] == "quality_modeling")
        assert quality["state"] == "blocked"
        assert "code_analysis" in quality["blocking_reason"]
        assert "dataset_source" not in repository

        findings = client.get("/api/orchestration/findings").get_json()
        assert findings["workflow"]["workflow_id"] == "existing_findings_research"
        assert findings["dataset"]["active"]["metadata"]["repository_analysis_bypassed"] is True
        assert findings["next_action"]["code"] in {"run_hsqa", "blocked"}


def test_existing_findings_history_can_be_pinned_without_changing_repository_input(tmp_path: Path):
    pytest.importorskip("flask")
    from pah import create_app

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first = workspace / "first.csv"
    second = workspace / "second.csv"
    first.write_text("id,CWE-1\na,1\nb,2\n", encoding="utf-8")
    second.write_text("id,CWE-1\na,7\nb,8\n", encoding="utf-8")

    app = create_app(state_dir=tmp_path / "state")
    app.config.update(TESTING=True)
    with app.test_client() as client:
        client.post("/api/workspace/open", json={"path": str(workspace)})
        assert client.post("/api/orchestration/findings/import", json={"path": str(first), "id_column": "id"}).status_code == 201
        assert client.post("/api/orchestration/findings/import", json={"path": str(second), "id_column": "id"}).status_code == 201
        current = client.get("/api/orchestration/findings").get_json()
        history = current["dataset"]["history"]
        assert len(history) >= 2
        older = next(item for item in history if item["metadata"].get("source_sha256") != current["dataset"]["active"]["metadata"].get("source_sha256"))
        selected = client.post(
            "/api/orchestration/findings/steps/representation_analysis/inputs/feature_dataset/select",
            json={"artifact_id": older["artifact_id"]},
        )
        assert selected.status_code == 200
        payload = selected.get_json()
        assert payload["dataset"]["selection_mode"] == "pinned"
        assert payload["dataset"]["active"]["artifact_id"] == older["artifact_id"]
