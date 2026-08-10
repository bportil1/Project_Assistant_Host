from pathlib import Path

import pytest

from pah.integrations import ReferenceIntegration, ReferenceIntegrationError


def test_reference_manager_is_optional_when_module_missing(monkeypatch, tmp_path: Path):
    integration = ReferenceIntegration(state_dir=tmp_path / "state")

    def fail_import(_name):
        raise ModuleNotFoundError("reference_manager")

    monkeypatch.setattr("pah.integrations.references.importlib.import_module", fail_import)
    status = integration.status()
    assert status["available"] is False
    with pytest.raises(ReferenceIntegrationError, match="not installed"):
        integration.select_library(tmp_path)


def test_real_reference_manager_library_browse_edit_and_restore_selection(tmp_path: Path):
    pytest.importorskip("reference_manager")
    library = tmp_path / "library"
    (library / "Security").mkdir(parents=True)
    (library / "Security" / "paper.pdf").write_bytes(b"%PDF fake")

    integration = ReferenceIntegration(state_dir=tmp_path / "state")
    integration.select_library(library)
    sync = integration.sync(detect_moves=False, extract_titles=False)
    assert integration.status()["available"] is True
    assert integration.status()["configured"] is True
    assert sync["summary"]["papers"] == 1

    data = integration.papers(query="paper")
    assert data["matched"] == 1
    paper = data["papers"][0]
    assert paper["Topic"] == "Security"
    assert paper["pdf_available"] is True

    updated = integration.save_paper(paper["PaperID"], status="Read", notes="Useful for methods")
    assert updated["Status"] == "Read"
    assert updated["Notes"] == "Useful for methods"
    assert integration.pdf_file(paper["PaperID"]).name == "paper.pdf"

    restored = ReferenceIntegration(state_dir=tmp_path / "state")
    assert restored.status()["library_root"] == str(library.resolve())
    assert restored.papers(status="Read")["matched"] == 1


def test_reference_manager_bibtex_import_and_filters(tmp_path: Path):
    pytest.importorskip("reference_manager")
    library = tmp_path / "library"
    library.mkdir()
    integration = ReferenceIntegration(state_dir=tmp_path / "state")
    integration.select_library(library)

    result = integration.import_bibtex(
        "@article{smith2026, title={Graph Based Code Analysis}, author={Smith, A.}, year={2026}, journal={Example Journal}}"
    )
    assert result["entries"] == 1
    papers = integration.papers(query="Graph Based", status="Cited")
    assert papers["matched"] == 1
    assert papers["papers"][0]["BibKey"] == "smith2026"
    assert "BibTeX Inbox" in papers["topics"]
    assert isinstance(integration.duplicates(), list)


def test_use_workspace_can_select_reference_library(tmp_path: Path):
    pytest.importorskip("reference_manager")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    integration = ReferenceIntegration(state_dir=tmp_path / "state")
    integration.bind_workspace(workspace)
    status = integration.use_workspace()
    assert status["library_root"] == str(workspace.resolve())
