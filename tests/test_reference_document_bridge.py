import pytest

from pah.integrations import ReferenceDocumentBridgeError, reference_document_snippet


PAPER = {
    "PaperID": "paper-123",
    "Title": "Graph Based Code Analysis",
    "Authors": "A. Smith and B. Jones",
    "Year": "2026",
    "Venue": "ExampleConf",
    "DOI": "10.1000/example",
    "BibKey": "smith2026graph",
}


def test_markdown_reference_citation_uses_existing_bibkey():
    snippet = reference_document_snippet(PAPER, "docs/method.md", kind="citation")
    assert "PAH-REF" in snippet
    assert "[@smith2026graph]" in snippet


def test_latex_reference_citation_uses_existing_bibkey():
    snippet = reference_document_snippet(PAPER, "paper.tex", kind="citation")
    assert r"\cite{smith2026graph}" in snippet


def test_reference_note_does_not_require_bibkey():
    paper = dict(PAPER, BibKey="")
    snippet = reference_document_snippet(paper, "notes.md", kind="note")
    assert "Graph Based Code Analysis" in snippet
    assert "A. Smith" in snippet


def test_citation_refuses_to_invent_missing_bibkey():
    with pytest.raises(ReferenceDocumentBridgeError, match="no BibKey"):
        reference_document_snippet(dict(PAPER, BibKey=""), "notes.md", kind="citation")


def test_reference_rejects_non_document_target():
    with pytest.raises(ReferenceDocumentBridgeError):
        reference_document_snippet(PAPER, "data.json", kind="note")
