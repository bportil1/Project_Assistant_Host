from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from pah.integrations.overleaf import OverleafImportError, OverleafImportService


def make_zip(files: dict[str, bytes | str]) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            payload = content.encode("utf-8") if isinstance(content, str) else content
            archive.writestr(name, payload)
    buffer.seek(0)
    return buffer


def test_overleaf_zip_import_is_local_preserves_tree_and_detects_document_assets(tmp_path: Path):
    service = OverleafImportService()
    archive = make_zip(
        {
            "main.tex": r"\documentclass{article}\begin{document}Hi\bibliography{refs}\end{document}",
            "chapters/method.tex": r"\section{Method}",
            "refs.bib": "@article{x, title={X}}",
            "figures/result.png": b"PNG",
            "styles/custom.sty": "% style",
        }
    )
    destination = tmp_path / "paper"

    result = service.import_zip(archive, destination, filename="overleaf.zip")

    assert result["acquisition_mode"] == "zip"
    assert result["destination"] == str(destination.resolve())
    assert not (destination / ".git").exists()
    assert (destination / "chapters" / "method.tex").exists()
    project = result["project"]
    assert project["likely_main"] == "main.tex"
    assert project["bib_files"] == ["refs.bib"]
    assert project["figure_files"] == ["figures/result.png"]
    assert project["support_files"] == ["styles/custom.sty"]
    assert project["counts"] == {"tex": 2, "bib": 1, "figures": 1, "support": 1}


def test_overleaf_zip_import_rejects_traversal_and_nonempty_destination(tmp_path: Path):
    service = OverleafImportService()
    bad = make_zip({"../escape.tex": "bad"})
    with pytest.raises(OverleafImportError, match="Unsafe path"):
        service.import_zip(bad, tmp_path / "bad")
    assert not (tmp_path / "escape.tex").exists()
    assert not (tmp_path / "bad").exists()

    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "keep.txt").write_text("keep", encoding="utf-8")
    good = make_zip({"main.tex": r"\documentclass{article}"})
    with pytest.raises(OverleafImportError, match="not empty"):
        service.import_zip(good, destination)
    assert (destination / "keep.txt").read_text(encoding="utf-8") == "keep"


def test_overleaf_likely_main_prefers_document_entry_point(tmp_path: Path):
    service = OverleafImportService()
    root = tmp_path / "project"
    root.mkdir()
    (root / "chapter.tex").write_text(r"\section{Chapter}", encoding="utf-8")
    (root / "thesis.tex").write_text(r"\documentclass{report}\begin{document}x\end{document}", encoding="utf-8")
    summary = service.inspect_project(root)
    assert summary["likely_main"] == "thesis.tex"
