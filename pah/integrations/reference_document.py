from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any


class ReferenceDocumentBridgeError(ValueError):
    pass


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _markdown_note(paper: dict[str, Any]) -> str:
    title = _clean(paper.get("Title")) or _clean(paper.get("Filename")) or "Untitled reference"
    authors = _clean(paper.get("Authors"))
    year = _clean(paper.get("Year"))
    venue = _clean(paper.get("Venue"))
    doi = _clean(paper.get("DOI"))
    pieces = []
    if authors:
        pieces.append(authors)
    if year:
        pieces.append(f"({year})")
    prefix = " ".join(pieces)
    line = f"**{title}**"
    if prefix:
        line = f"{prefix}. {line}"
    if venue:
        line += f". {venue}"
    if doi:
        line += f". DOI: {doi}"
    return line.rstrip(".") + "."


def _latex_escape(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def reference_document_snippet(
    paper: dict[str, Any],
    target_path: str,
    *,
    kind: str = "citation",
) -> str:
    """Create a PAH-owned reference snippet for Markdown or LaTeX.

    ``kind='citation'`` uses the library's BibKey and refuses to invent one.
    ``kind='note'`` inserts a human-readable bibliographic note instead.
    """
    suffix = PurePosixPath(str(target_path)).suffix.lower()
    if suffix not in {".md", ".markdown", ".tex"}:
        raise ReferenceDocumentBridgeError("References can only target Markdown or LaTeX files.")
    kind = str(kind or "citation").strip().lower()
    if kind not in {"citation", "note"}:
        raise ReferenceDocumentBridgeError("Reference snippet kind must be 'citation' or 'note'.")

    paper_id = _clean(paper.get("PaperID"))
    bibkey = _clean(paper.get("BibKey"))
    title = _clean(paper.get("Title")) or _clean(paper.get("Filename")) or "Untitled reference"

    if kind == "citation" and not bibkey:
        raise ReferenceDocumentBridgeError(
            "This reference has no BibKey. Add/import a BibTeX key or insert a reference note instead."
        )

    if suffix in {".md", ".markdown"}:
        if kind == "citation":
            return f'<!-- PAH-REF paper_id="{paper_id}" bibkey="{bibkey}" -->\n[@{bibkey}]\n'
        return f'<!-- PAH-REF paper_id="{paper_id}" title="{title}" -->\n{_markdown_note(paper)}\n'

    if kind == "citation":
        return f"% PAH-REF paper_id={paper_id} bibkey={bibkey}\n\\cite{{{bibkey}}}\n"
    note = _latex_escape(_markdown_note(paper).replace("**", ""))
    return f"% PAH-REF paper_id={paper_id} title={_latex_escape(title)}\n{note}\n"
