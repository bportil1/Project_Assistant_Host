from __future__ import annotations

from dataclasses import asdict, is_dataclass
import importlib
import os
from pathlib import Path
from threading import RLock
from typing import Any


class DocumentIntegrationError(RuntimeError):
    """Raised when PAH cannot use the optional DocumentEngine integration."""


class DocumentIntegration:
    """Narrow PAH adapter around ``tech_documents.DocumentEngine``.

    PAH owns the arbitrary local workspace and the general editor/file browser.
    This adapter only asks DocumentEngine for document-specific behavior: diagram
    parsing/normalization and isolated LaTeX compilation. The standalone document
    workbench remains completely independent.
    """

    DOCUMENT_EXTENSIONS = {".md", ".markdown", ".tex", ".bib", ".diagram"}
    INSERT_TARGET_EXTENSIONS = {".md", ".markdown", ".tex"}

    def __init__(self, *, state_dir: str | Path | None = None) -> None:
        self._lock = RLock()
        self._root: Path | None = None
        self._engine: Any | None = None
        self._document_class: Any | None = None
        self._import_error: str | None = None
        default = Path.home() / ".local" / "share" / "pah" / "documents"
        self._state_dir = Path(state_dir or default).expanduser().resolve()

    def _load_class(self) -> Any | None:
        if self._document_class is not None:
            return self._document_class
        try:
            module = importlib.import_module("tech_documents")
            document_class = getattr(module, "DocumentEngine")
        except Exception as exc:
            self._import_error = f"{type(exc).__name__}: {exc}"
            return None
        self._document_class = document_class
        self._import_error = None
        return document_class

    def _get_engine(self) -> Any:
        document_class = self._load_class()
        if document_class is None:
            raise DocumentIntegrationError(
                "DocumentEngine is not installed in the PAH environment. "
                "Initialize modules/tech_documents and run scripts/setup.sh."
                + (f" Import error: {self._import_error}" if self._import_error else "")
            )
        with self._lock:
            if self._engine is None:
                # DocumentEngine's own managed standalone projects/builds live in
                # PAH state, never inside the user's opened repository.
                self._engine = document_class(self._state_dir)
            return self._engine

    def bind(self, root: str | Path) -> None:
        resolved = Path(root).expanduser().resolve()
        with self._lock:
            self._root = resolved

    def clear(self) -> None:
        with self._lock:
            self._root = None

    def _require_root(self) -> Path:
        with self._lock:
            if self._root is None:
                raise DocumentIntegrationError("Open a PAH workspace before using document tools.")
            return self._root

    def status(self) -> dict[str, Any]:
        document_class = self._load_class()
        compilers = {"latexmk": False, "tectonic": False}
        if document_class is not None:
            try:
                compilers = dict(self._get_engine().health())
            except Exception:
                pass
        return {
            "available": document_class is not None,
            "import_error": self._import_error,
            "project_root": str(self._root) if self._root else None,
            "compilers": compilers,
        }

    def files(self) -> list[dict[str, Any]]:
        root = self._require_root()
        rows: list[dict[str, Any]] = []
        ignored_dirs = {".git", ".venv", "venv", "env", "node_modules", "__pycache__", ".pytest_cache"}
        for directory, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in ignored_dirs]
            base = Path(directory)
            for filename in filenames:
                path = base / filename
                suffix = path.suffix.lower()
                if suffix not in self.DOCUMENT_EXTENSIONS:
                    continue
                relative = path.relative_to(root).as_posix()
                rows.append(
                    {
                        "path": relative,
                        "name": path.name,
                        "extension": suffix,
                        "insert_target": suffix in self.INSERT_TARGET_EXTENSIONS,
                        "size": path.stat().st_size,
                    }
                )
        rows.sort(key=lambda row: row["path"].lower())
        return rows

    def parse_diagram(
        self,
        content: str,
        *,
        direction: str | None = None,
        preset: str | None = None,
    ) -> dict[str, Any]:
        engine = self._get_engine()
        try:
            return dict(engine.parse_diagram(content, direction=direction, preset=preset))
        except Exception as exc:
            raise DocumentIntegrationError(str(exc)) from exc

    def compile_latex(self, relative_path: str) -> dict[str, Any]:
        root = self._require_root()
        engine = self._get_engine()
        try:
            result = engine.compile_latex_path(root, relative_path)
        except Exception as exc:
            raise DocumentIntegrationError(str(exc)) from exc
        if is_dataclass(result):
            payload = asdict(result)
        else:
            payload = dict(vars(result))
        pdf_path = payload.pop("pdf_path", None)
        payload["success"] = bool(payload.pop("ok", False))
        payload["pdf_name"] = Path(pdf_path).name if pdf_path else None
        return payload

    def build_file(self, build_id: str, filename: str) -> Path:
        engine = self._get_engine()
        try:
            return Path(engine.build_file_path(build_id, filename))
        except Exception as exc:
            raise DocumentIntegrationError(str(exc)) from exc
