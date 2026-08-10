from pathlib import Path
import shutil

import pytest

from pah.integrations import DocumentIntegration, DocumentIntegrationError


def test_document_engine_is_optional_when_module_missing(monkeypatch, tmp_path: Path):
    integration = DocumentIntegration(state_dir=tmp_path / "state")
    integration.bind(tmp_path)

    def fail_import(_name):
        raise ModuleNotFoundError("tech_documents")

    monkeypatch.setattr("pah.integrations.documents.importlib.import_module", fail_import)
    status = integration.status()
    assert status["available"] is False
    with pytest.raises(DocumentIntegrationError, match="not installed"):
        integration.parse_diagram("A -> B\n")


def test_real_document_engine_integration_when_available(tmp_path: Path):
    pytest.importorskip("tech_documents")
    project = tmp_path / "project"
    project.mkdir()
    (project / "notes.md").write_text("# Notes\n", encoding="utf-8")
    (project / "paper.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nHello\n\\end{document}\n",
        encoding="utf-8",
    )
    (project / "architecture.diagram").write_text("A -> B\n", encoding="utf-8")
    (project / ".venv").mkdir()
    (project / ".venv" / "ignored.md").write_text("ignore", encoding="utf-8")

    integration = DocumentIntegration(state_dir=tmp_path / "state")
    integration.bind(project)
    status = integration.status()
    assert status["available"] is True

    files = integration.files()
    paths = {row["path"] for row in files}
    assert {"notes.md", "paper.tex", "architecture.diagram"}.issubset(paths)
    assert ".venv/ignored.md" not in paths

    parsed = integration.parse_diagram("A [service] -> B [database]\n")
    assert "flowchart" in parsed["mermaid"]
    assert "A" in parsed["normalized_source"]


def test_real_document_engine_compile_when_compiler_available(tmp_path: Path):
    pytest.importorskip("tech_documents")
    if not (shutil.which("latexmk") or shutil.which("tectonic")):
        pytest.skip("No LaTeX compiler installed")
    project = tmp_path / "project"
    project.mkdir()
    (project / "paper.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\nPAH 0.3\n\\end{document}\n",
        encoding="utf-8",
    )
    integration = DocumentIntegration(state_dir=tmp_path / "state")
    integration.bind(project)
    result = integration.compile_latex("paper.tex")
    assert result["success"] is True
    assert result["pdf_name"] == "paper.pdf"
    assert integration.build_file(result["build_id"], result["pdf_name"]).exists()
