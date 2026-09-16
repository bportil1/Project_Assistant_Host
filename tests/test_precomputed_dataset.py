from __future__ import annotations

import json
from pathlib import Path

import pytest

from pah.labs.precomputed_dataset import (
    PrecomputedDatasetError,
    inspect_precomputed_table,
    materialize_precomputed_feature_dataset,
)


def test_import_preserves_numeric_matrix_order_and_records_no_transformations(tmp_path: Path):
    source = tmp_path / "nist.csv"
    source.write_text(
        "project,CWE-79,CWE-89\nalpha,2,0\nbeta,1,3\n",
        encoding="utf-8",
    )
    inspection = inspect_precomputed_table(source)
    assert inspection["valid"] is True
    assert inspection["suggested_id_column"] == "project"
    assert inspection["feature_columns"] == ["CWE-79", "CWE-89"]

    output, payload, metadata = materialize_precomputed_feature_dataset(
        source, output_root=tmp_path / "managed", dataset_name="nist-sard"
    )
    assert output.is_file()
    assert payload["schema"] == "pah.feature-dataset.matrix"
    assert payload["source_type"] == "precomputed_csv"
    assert payload["sample_ids"] == ["alpha", "beta"]
    assert payload["feature_ids"] == ["CWE-79", "CWE-89"]
    assert payload["values"] == [[2, 0], [1, 3]]
    assert payload["metadata"]["transformations"] == []
    assert payload["metadata"]["analysis_bypassed"] is True
    assert Path(metadata["analysis_target"]).is_dir()
    assert json.loads(output.read_text(encoding="utf-8"))["values"] == [[2, 0], [1, 3]]


def test_import_can_use_generated_ids_for_all_numeric_matrix(tmp_path: Path):
    source = tmp_path / "matrix.tsv"
    source.write_text("CWE-1\tCWE-2\n1\t2\n3\t4\n", encoding="utf-8")
    output, payload, _ = materialize_precomputed_feature_dataset(
        source, output_root=tmp_path / "managed", id_column="__generated__"
    )
    assert output.is_file()
    assert payload["sample_ids"] == ["sample-1", "sample-2"]
    assert payload["feature_ids"] == ["CWE-1", "CWE-2"]


def test_import_rejects_non_numeric_feature_instead_of_cleaning_it(tmp_path: Path):
    source = tmp_path / "bad.csv"
    source.write_text("id,CWE-1\na,1\nb,not-a-number\n", encoding="utf-8")
    inspection = inspect_precomputed_table(source)
    assert inspection["valid"] is False
    assert any("not numeric" in error for error in inspection["errors"])
    with pytest.raises(PrecomputedDatasetError):
        materialize_precomputed_feature_dataset(source, output_root=tmp_path / "managed")
