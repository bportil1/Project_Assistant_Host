from __future__ import annotations

import importlib
import json
from collections import Counter
from pathlib import Path
from threading import RLock
from typing import Any


class ReferenceIntegrationError(RuntimeError):
    """Raised when PAH cannot use the optional ReferenceManager integration."""


class ReferenceIntegration:
    """Narrow PAH adapter around ``reference_manager.ReferenceManager``.

    ReferenceManager continues to own paper-library behavior. PAH only owns the
    host presentation, persisted selection of a library, and cross-module
    workflows. The selected reference library is independent of the currently
    open code workspace, although the workspace can be chosen as the library.
    """

    ALLOWED_STATUSES = {"OK", "Needs Review", "Priority", "Read", "Ignore", "Cited"}

    def __init__(self, *, state_dir: str | Path | None = None) -> None:
        default = Path.home() / ".local" / "share" / "pah" / "references"
        self._state_dir = Path(state_dir or default).expanduser().resolve()
        self._config_path = self._state_dir / "library.json"
        self._lock = RLock()
        self._reference_class: Any | None = None
        self._manager: Any | None = None
        self._library_root: Path | None = None
        self._workspace_root: Path | None = None
        self._import_error: str | None = None
        self._restore_selection()

    def _load_class(self) -> Any | None:
        if self._reference_class is not None:
            return self._reference_class
        try:
            module = importlib.import_module("reference_manager")
            reference_class = getattr(module, "ReferenceManager")
        except Exception as exc:
            self._import_error = f"{type(exc).__name__}: {exc}"
            return None
        self._reference_class = reference_class
        self._import_error = None
        return reference_class

    def _restore_selection(self) -> None:
        try:
            payload = json.loads(self._config_path.read_text(encoding="utf-8"))
            value = payload.get("library_root")
            if value:
                root = Path(value).expanduser().resolve()
                if root.exists() and root.is_dir():
                    self._library_root = root
        except Exception:
            return

    def _persist_selection(self) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        payload = {"library_root": str(self._library_root) if self._library_root else None}
        self._config_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def bind_workspace(self, root: str | Path | None) -> None:
        with self._lock:
            self._workspace_root = Path(root).expanduser().resolve() if root else None

    def select_library(self, root: str | Path) -> dict[str, Any]:
        reference_class = self._load_class()
        if reference_class is None:
            raise ReferenceIntegrationError(
                "ReferenceManager is not installed in the PAH environment. "
                "Initialize modules/reference_manager and run scripts/setup.sh."
                + (f" Import error: {self._import_error}" if self._import_error else "")
            )
        resolved = Path(root).expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise ReferenceIntegrationError(f"Reference library does not exist: {resolved}")
        try:
            manager = reference_class(resolved)
        except Exception as exc:
            raise ReferenceIntegrationError(str(exc)) from exc
        with self._lock:
            self._library_root = resolved
            self._manager = manager
            self._persist_selection()
        return self.status()

    def use_workspace(self) -> dict[str, Any]:
        with self._lock:
            root = self._workspace_root
        if root is None:
            raise ReferenceIntegrationError("Open a PAH workspace before using it as the reference library.")
        return self.select_library(root)

    def clear_library(self) -> dict[str, Any]:
        with self._lock:
            self._library_root = None
            self._manager = None
            self._persist_selection()
        return self.status()

    def _get_manager(self) -> Any:
        reference_class = self._load_class()
        if reference_class is None:
            raise ReferenceIntegrationError(
                "ReferenceManager is not installed in the PAH environment. "
                "Initialize modules/reference_manager and run scripts/setup.sh."
                + (f" Import error: {self._import_error}" if self._import_error else "")
            )
        with self._lock:
            if self._library_root is None:
                raise ReferenceIntegrationError("Choose a reference-library directory first.")
            if self._manager is None:
                try:
                    self._manager = reference_class(self._library_root)
                except Exception as exc:
                    raise ReferenceIntegrationError(str(exc)) from exc
            return self._manager

    @staticmethod
    def _paper_view(row: dict[str, Any]) -> dict[str, Any]:
        result = dict(row)
        path = Path(str(row.get("Path") or "")) if row.get("Path") else None
        result["pdf_available"] = bool(
            row.get("FileState") == "Present"
            and path is not None
            and path.exists()
            and path.is_file()
            and path.suffix.lower() == ".pdf"
        )
        return result

    @staticmethod
    def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        statuses = Counter(str(row.get("Status") or "Unspecified") for row in rows)
        topics = Counter(str(row.get("Topic") or "Uncategorized") for row in rows)
        states = Counter(str(row.get("FileState") or "Unknown") for row in rows)
        return {
            "papers": len(rows),
            "status_counts": dict(sorted(statuses.items())),
            "topic_counts": dict(sorted(topics.items())),
            "file_state_counts": dict(sorted(states.items())),
            "bibkey_count": sum(1 for row in rows if str(row.get("BibKey") or "").strip()),
        }

    def status(self) -> dict[str, Any]:
        reference_class = self._load_class()
        payload: dict[str, Any] = {
            "available": reference_class is not None,
            "import_error": self._import_error,
            "library_root": str(self._library_root) if self._library_root else None,
            "workspace_root": str(self._workspace_root) if self._workspace_root else None,
            "configured": self._library_root is not None,
            "summary": None,
        }
        if reference_class is not None and self._library_root is not None:
            try:
                rows = self._get_manager().list_papers()
                payload["summary"] = self._summary(rows)
            except Exception as exc:
                payload["library_error"] = f"{type(exc).__name__}: {exc}"
        return payload

    def papers(
        self,
        *,
        query: str = "",
        status: str = "",
        topic: str = "",
        limit: int = 500,
    ) -> dict[str, Any]:
        try:
            all_rows = [dict(row) for row in self._get_manager().list_papers()]
        except Exception as exc:
            raise ReferenceIntegrationError(str(exc)) from exc
        all_summary = self._summary(all_rows)
        statuses = sorted({str(row.get("Status") or "") for row in all_rows if row.get("Status")})
        topics = sorted({str(row.get("Topic") or "") for row in all_rows if row.get("Topic")})
        rows = list(all_rows)
        query_norm = query.strip().lower()
        status_norm = status.strip()
        topic_norm = topic.strip()

        if query_norm:
            fields = ("Title", "Filename", "Authors", "Venue", "DOI", "BibKey", "Topic", "Notes", "Keywords")
            rows = [
                row
                for row in rows
                if any(query_norm in str(row.get(field) or "").lower() for field in fields)
            ]
        if status_norm:
            rows = [row for row in rows if str(row.get("Status") or "") == status_norm]
        if topic_norm:
            rows = [row for row in rows if str(row.get("Topic") or "") == topic_norm]

        rows.sort(key=lambda row: (
            str(row.get("Title") or row.get("Filename") or "").lower(),
            str(row.get("PaperID") or ""),
        ))
        limit = max(1, min(int(limit or 500), 2000))
        return {
            "papers": [self._paper_view(row) for row in rows[:limit]],
            "matched": len(rows),
            "truncated": len(rows) > limit,
            "summary": all_summary,
            "statuses": statuses,
            "topics": topics,
        }

    def paper(self, paper_id: str) -> dict[str, Any]:
        try:
            return self._paper_view(dict(self._get_manager().get_paper(paper_id)))
        except Exception as exc:
            raise ReferenceIntegrationError(str(exc)) from exc

    def save_paper(self, paper_id: str, *, status: str | None = None, notes: str | None = None) -> dict[str, Any]:
        manager = self._get_manager()
        try:
            rows = manager.list_papers()
            selected: dict[str, Any] | None = None
            for row in rows:
                if row.get("PaperID") == paper_id:
                    selected = row
                    break
            if selected is None:
                raise KeyError(f"Paper not found: {paper_id}")
            if status is not None:
                clean_status = str(status).strip()
                if clean_status not in self.ALLOWED_STATUSES:
                    raise ValueError(f"Unsupported status: {clean_status}")
                selected["Status"] = clean_status
            if notes is not None:
                selected["Notes"] = str(notes)
            manager.save_papers(rows)
            return self._paper_view(dict(selected))
        except Exception as exc:
            raise ReferenceIntegrationError(str(exc)) from exc

    def sync(self, *, detect_moves: bool = True, extract_titles: bool = False) -> dict[str, Any]:
        try:
            result = dict(self._get_manager().sync(detect_moves=detect_moves, extract_titles=extract_titles))
        except Exception as exc:
            raise ReferenceIntegrationError(str(exc)) from exc
        result["summary"] = self.status().get("summary")
        return result

    def duplicates(self) -> list[list[dict[str, Any]]]:
        try:
            groups = self._get_manager().find_duplicates()
            return [[self._paper_view(dict(row)) for row in group] for group in groups]
        except Exception as exc:
            raise ReferenceIntegrationError(str(exc)) from exc

    def import_bibtex(self, text: str) -> dict[str, Any]:
        if not str(text).strip():
            raise ReferenceIntegrationError("BibTeX content is empty.")
        try:
            result = dict(self._get_manager().import_bibtex_text(text))
        except Exception as exc:
            raise ReferenceIntegrationError(str(exc)) from exc
        result["summary"] = self.status().get("summary")
        return result

    def pdf_file(self, paper_id: str) -> Path:
        paper = self.paper(paper_id)
        if paper.get("FileState") != "Present":
            raise ReferenceIntegrationError("Only present PDF files can be opened from PAH.")
        raw_path = str(paper.get("Path") or "")
        if not raw_path:
            raise ReferenceIntegrationError("This paper has no local PDF path.")
        path = Path(raw_path).expanduser().resolve()
        root = self._library_root
        if root is None:
            raise ReferenceIntegrationError("Choose a reference library first.")
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ReferenceIntegrationError("Paper path escapes the selected reference library.") from exc
        if not path.exists() or not path.is_file() or path.suffix.lower() != ".pdf":
            raise ReferenceIntegrationError(f"PDF is unavailable: {path}")
        return path
