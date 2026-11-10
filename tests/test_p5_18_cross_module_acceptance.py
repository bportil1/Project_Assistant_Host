"""P5-18 offline producer-to-host acceptance, without modifying SAT output.

Run with pyPIQUE on the local Python path, for example:
PYTHONPATH=.:../pyPIQUE/src python -m pytest -q tests/test_p5_18_cross_module_acceptance.py
The real hosted Flask/browser workflow is a separate acceptance gate.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import patch

import pytest

from pah.labs.source_evidence import (
    SourceEvidenceError, SourceEvidenceLocator, read_source_evidence,
)

producer = pytest.importorskip("pique_py.source_evidence_locator")


def _finding(content: bytes, *, path: str = "src/example.py", **changes):
    row = {"provider_finding_id": "bandit-17", "tool": "bandit", "file_path": path,
           "line": 2, "end_line": 3, "source_sha256": hashlib.sha256(content).hexdigest()}
    row.update(changes)
    return row


def _source(root: Path):
    source = root / "src" / "example.py"
    source.parent.mkdir(parents=True)
    content = b"first\nsecond\nthird\nfourth\n"
    source.write_bytes(content)
    return source, content


def _preview(root: Path, project_id: str, row: dict):
    projection = producer.finding_evidence_locator(row, project_id=project_id)
    assert projection["schema"] == "pypique.source-evidence-projection@1"
    assert projection["status"] == "ready_for_pah_verification"
    locator = SourceEvidenceLocator.from_mapping(projection["locator"])
    return read_source_evidence(repository_root=root, active_project_id=project_id,
                                locator=locator)


def test_real_producer_projection_to_verified_host_preview(tmp_path):
    source, content = _source(tmp_path)
    original = source.read_bytes()
    result = _preview(tmp_path, "alpha", _finding(content))
    assert result["excerpt"] == "second\nthird"
    assert result["finding_id"] == "bandit-17"
    assert result["relative_path"] == "src/example.py"
    assert result["mode"] == "read_only"
    assert source.read_bytes() == original


def test_project_switch_rejects_previously_selected_finding(tmp_path):
    _, content = _source(tmp_path)
    projection = producer.finding_evidence_locator(_finding(content), project_id="alpha")
    locator = SourceEvidenceLocator.from_mapping(projection["locator"])
    with pytest.raises(SourceEvidenceError, match="different project"):
        read_source_evidence(repository_root=tmp_path, active_project_id="beta", locator=locator)


def test_source_change_after_scan_fails_closed(tmp_path):
    source, content = _source(tmp_path)
    projection = producer.finding_evidence_locator(_finding(content), project_id="alpha")
    source.write_text("first\nchanged\nthird\nfourth\n", encoding="utf-8")
    with pytest.raises(SourceEvidenceError, match="stale"):
        read_source_evidence(repository_root=tmp_path, active_project_id="alpha",
                             locator=SourceEvidenceLocator.from_mapping(projection["locator"]))


def test_historical_missing_digest_unavailable(tmp_path):
    _, content = _source(tmp_path)
    row = _finding(content)
    row.pop("source_sha256")
    projection = producer.finding_evidence_locator(row, project_id="alpha")
    assert projection["status"] == "unavailable"
    assert projection["reason"] == "missing_verified_source_sha256"
    assert projection["locator"] is None


def test_unsafe_source_reference_never_becomes_locator(tmp_path):
    _, content = _source(tmp_path)
    for path in ("../outside.py", "/tmp/absolute.py", "src/../example.py", "src\\example.py"):
        projection = producer.finding_evidence_locator(_finding(content, path=path), project_id="alpha")
        assert projection["status"] == "unavailable"
        assert projection["locator"] is None


def test_symlink_replacement_rejected_by_host(tmp_path):
    root = tmp_path / "root"
    source, content = _source(root)
    projection = producer.finding_evidence_locator(_finding(content), project_id="alpha")
    source.unlink()
    outside = tmp_path / "outside.py"
    outside.write_bytes(content)
    source.symlink_to(outside)
    with pytest.raises(SourceEvidenceError, match="unavailable|escapes"):
        read_source_evidence(repository_root=root, active_project_id="alpha",
                             locator=SourceEvidenceLocator.from_mapping(projection["locator"]))


def test_project_findings_batch_preserves_unavailable_status(tmp_path):
    _, content = _source(tmp_path)
    historical = _finding(content, provider_finding_id="old")
    historical.pop("source_sha256")
    dataset = {"view": "all", "findings": [_finding(content), historical]}
    with patch.object(producer, "load_findings_view", return_value=dataset) as load:
        result = producer.project_findings_evidence(str(tmp_path), project_id="alpha", limit=100)
    load.assert_called_once_with(str(tmp_path), view="all", provider=None)
    assert result["count"] == 2
    assert [row["status"] for row in result["results"]] == ["ready_for_pah_verification", "unavailable"]
    assert result["results"][1]["locator"] is None
