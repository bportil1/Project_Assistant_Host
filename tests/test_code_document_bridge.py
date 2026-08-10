import pytest

from pah.integrations import CodeDocumentBridgeError, code_document_snippet


ENTITY = {
    "id": "function:demo.py:7:calculate_score",
    "name": "calculate_score",
    "qualified_name": "demo.calculate_score",
    "path": "src/demo.py",
    "metadata": {
        "line_start": 7,
        "line_end": 10,
        "source_code": "def calculate_score(x):\n    return x * 2",
    },
}


def test_markdown_code_reference_without_source():
    snippet = code_document_snippet(ENTITY, "docs/method.md")
    assert "PAH-CODE-REF" in snippet
    assert "demo.calculate_score" in snippet
    assert "src/demo.py" in snippet
    assert "```python" not in snippet


def test_markdown_code_reference_with_source():
    snippet = code_document_snippet(ENTITY, "docs/method.md", include_source=True)
    assert "```python" in snippet
    assert "def calculate_score" in snippet


def test_latex_code_reference_with_source_is_dependency_free():
    snippet = code_document_snippet(ENTITY, "paper.tex", include_source=True)
    assert "% PAH-CODE-REF" in snippet
    assert r"\begin{verbatim}" in snippet
    assert r"demo.calculate\_score" in snippet


def test_code_reference_rejects_non_document_target():
    with pytest.raises(CodeDocumentBridgeError):
        code_document_snippet(ENTITY, "data.json")
