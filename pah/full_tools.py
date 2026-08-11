from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from werkzeug.serving import WSGIRequestHandler, make_server


class _QuietHandler(WSGIRequestHandler):
    def log_request(self, code: int | str = "-", size: int | str = "-") -> None:
        # Full-tool servers are internal implementation details of PAH. Their
        # normal access logs would otherwise duplicate every iframe request in
        # the host terminal.
        try:
            if int(code) < 400:
                return
        except Exception:
            pass
        super().log_request(code, size)


class _Server:
    def __init__(self, name: str, host: str, port: int):
        self.name = name
        self.host = host
        self.port = port
        self._server = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    @property
    def running(self) -> bool:
        return self._server is not None

    def start(self, app) -> None:
        self.stop()
        self._server = make_server(
            self.host,
            self.port,
            app,
            threaded=True,
            request_handler=_QuietHandler,
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name=f"pah-{self.name}-ui",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        if server is not None:
            try:
                server.shutdown()
            except Exception:
                pass
            try:
                server.server_close()
            except Exception:
                pass
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=1.5)


class FullToolManager:
    """Host the existing standalone module UIs as PAH full-workspace modes.

    The module Flask applications still run unchanged at their own loopback
    ports. PAH displays them inside persistent full-workspace frames, which
    lets root-relative `/api/...` calls in the mature standalone frontends keep
    working without copying or rewriting those interfaces into PAH.
    """

    def __init__(
        self,
        *,
        state_dir: str | Path,
        host: str = "127.0.0.1",
        analyzer_port: int = 8766,
        documents_port: int = 8767,
        references_port: int = 8768,
    ):
        self.state_dir = Path(state_dir).expanduser().resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.host = host
        self._workspace: Path | None = None
        self._reference_library: Path | None = None
        self._errors: dict[str, str | None] = {
            "analysis": None,
            "documents": None,
            "references": None,
        }
        self._servers = {
            "analysis": _Server("analysis", host, analyzer_port),
            "documents": _Server("documents", host, documents_port),
            "references": _Server("references", host, references_port),
        }
        self._document_engine = None

    def bind_workspace(self, root: str | Path | None) -> None:
        self._workspace = Path(root).expanduser().resolve() if root else None
        # Full tool servers are started lazily when the browser first opens a
        # full mode. If they are already running, synchronize them immediately.
        if self._servers["documents"].running:
            self._start_documents()
        if self._servers["analysis"].running:
            # The analyzer web application closes over its CodeAnalyzer instance,
            # so recreating only this internal server is the cleanest way to
            # synchronize repository changes while preserving its standalone UI.
            self._start_analysis()

    def bind_reference_library(self, root: str | Path | None) -> None:
        self._reference_library = Path(root).expanduser().resolve() if root else None
        self._write_reference_config()

    def start_available(self) -> None:
        self._start_documents()
        self._start_references()
        if self._workspace is not None:
            self._start_analysis()

    def stop_all(self) -> None:
        for server in self._servers.values():
            server.stop()

    def reference_library_from_tool(self) -> Path | None:
        try:
            payload = json.loads(self._reference_config_path().read_text(encoding="utf-8"))
            raw = str(payload.get("library_root") or "").strip()
            if not raw:
                return None
            path = Path(raw).expanduser().resolve()
            return path if path.exists() and path.is_dir() else None
        except Exception:
            return None

    def status(self) -> dict[str, Any]:
        tools = {}
        for key, server in self._servers.items():
            tools[key] = {
                "available": server.running,
                "url": server.url if server.running else None,
                "error": self._errors.get(key),
            }
        tools["analysis"]["bound_workspace"] = str(self._workspace) if self._workspace else None
        tools["documents"]["bound_workspace"] = str(self._workspace) if self._workspace else None
        tools["references"]["library_root"] = str(self._reference_library) if self._reference_library else None
        return {"tools": tools}

    # ------------------------------------------------------------------
    # Analyzer full UI
    # ------------------------------------------------------------------
    def _start_analysis(self) -> None:
        server = self._servers["analysis"]
        if self._workspace is None:
            server.stop()
            self._errors["analysis"] = "Open a PAH workspace before using full Analysis mode."
            return
        try:
            from code_analyzer.web.app import create_app

            app = create_app(self._workspace)
            server.start(app)
            self._errors["analysis"] = None
        except Exception as exc:
            server.stop()
            self._errors["analysis"] = f"{type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------
    # Document Workbench full UI
    # ------------------------------------------------------------------
    def _start_documents(self) -> None:
        try:
            from tech_documents.api import DocumentEngine
            from tech_documents.errors import (
                InvalidPathError,
                ItemConflictError,
                ItemNotFoundError,
                UnsupportedFileTypeError,
            )
            from tech_documents.paths import (
                ALLOWED_EXTENSIONS,
                DIAGRAM_ASSET_EXTENSIONS,
                normalize_relative_path,
                safe_name,
            )
            import tech_documents.web.app as web_app

            manager = self

            class WorkspaceDocumentEngine(DocumentEngine):
                _ignored_dirs = {
                    ".git", ".hg", ".svn", ".venv", "venv", "env",
                    "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache",
                    ".ruff_cache", "dist", ".tox",
                }

                def __init__(self):
                    # Keep build products and temporary archives outside the user's
                    # source repository while document files themselves remain real
                    # project files.
                    super().__init__(base_dir=manager.state_dir / "document-workbench")

                def _root(self) -> Path:
                    if manager._workspace is None:
                        raise ItemNotFoundError("Open a PAH workspace first.")
                    return manager._workspace

                def _project_name(self) -> str:
                    return safe_name(self._root().name, "workspace")

                def project_path(self, project: str) -> Path:
                    expected = self._project_name()
                    if safe_name(project, "workspace") != expected:
                        raise ItemNotFoundError("PAH Document mode is bound to the current workspace.")
                    return self._root()

                def item_path(self, project: str, relative_path: str, *, allow_empty: bool = False) -> Path:
                    root = self.project_path(project).resolve()
                    normalized = normalize_relative_path(relative_path, allow_empty=allow_empty)
                    path = (root / normalized).resolve() if normalized else root
                    if path != root and root not in path.parents:
                        raise InvalidPathError("Path leaves the PAH workspace.")
                    return path

                def editable_file_path(self, project: str, relative_path: str) -> Path:
                    path = self.item_path(project, relative_path)
                    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
                        raise UnsupportedFileTypeError("Unsupported editable file type.")
                    return path

                def build_project_tree(self, project_path: Path):
                    flat_files: list[dict[str, Any]] = []
                    visible_ext = set(ALLOWED_EXTENSIONS) | set(DIAGRAM_ASSET_EXTENSIONS)

                    def walk(directory: Path):
                        nodes = []
                        try:
                            children = sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
                        except (FileNotFoundError, PermissionError, OSError):
                            return []
                        for child in children:
                            if child.is_symlink():
                                continue
                            if child.is_dir():
                                if child.name in self._ignored_dirs:
                                    continue
                                branch = walk(child)
                                if branch:
                                    nodes.append({
                                        "type": "directory",
                                        "name": child.name,
                                        "path": child.relative_to(project_path).as_posix(),
                                        "children": branch,
                                    })
                                continue
                            if not child.is_file() or child.suffix.lower() not in visible_ext:
                                continue
                            rel = child.relative_to(project_path).as_posix()
                            info = {
                                "type": "file",
                                "name": child.name,
                                "path": rel,
                                "extension": child.suffix.lower(),
                                "size": child.stat().st_size,
                                "editable": child.suffix.lower() in ALLOWED_EXTENSIONS,
                            }
                            nodes.append(info)
                            flat_files.append(info.copy())
                        return nodes

                    return walk(project_path), flat_files

                def list_projects(self):
                    if manager._workspace is None:
                        return []
                    root = self._root()
                    tree, files = self.build_project_tree(root)
                    return [{"name": self._project_name(), "tree": tree, "files": files}]

                def create_project(self, name: str) -> str:
                    raise ItemConflictError("PAH Document mode uses the current workspace; create folders/files inside it instead.")

                def delete_project(self, project: str) -> None:
                    raise ItemConflictError("The current PAH workspace cannot be deleted from Document mode.")

            if self._document_engine is None:
                self._document_engine = WorkspaceDocumentEngine()
                web_app.engine = self._document_engine
                # The standalone frontend's project concept becomes the PAH
                # workspace, so hide the now-inapplicable New Project button.
                @web_app.app.after_request
                def _pah_document_chrome(response):
                    content_type = response.headers.get("Content-Type", "")
                    if "text/html" in content_type:
                        text = response.get_data(as_text=True)
                        marker = "</head>"
                        addition = (
                            "<style>#newProjectBtn{display:none!important}</style>"
                            "<meta name=\"pah-full-tool\" content=\"documents\">"
                        )
                        if marker in text and "pah-full-tool" not in text:
                            response.set_data(text.replace(marker, addition + marker, 1))
                            response.headers["Content-Length"] = str(len(response.get_data()))
                    return response
                self._servers["documents"].start(web_app.app)
            self._errors["documents"] = None
        except Exception as exc:
            self._servers["documents"].stop()
            self._document_engine = None
            self._errors["documents"] = f"{type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------
    # Reference Manager full UI
    # ------------------------------------------------------------------
    def _reference_config_path(self) -> Path:
        return self.state_dir / "reference-manager-config.json"

    def _write_reference_config(self) -> None:
        config_path = self._reference_config_path()
        payload = {"library_root": str(self._reference_library) if self._reference_library else ""}
        config_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _start_references(self) -> None:
        try:
            import reference_manager.web.config as web_config

            web_config.CONFIG_PATH = self._reference_config_path()
            from reference_manager.web.app import create_app
            if not web_config.CONFIG_PATH.exists():
                self._write_reference_config()
            if not self._servers["references"].running:
                self._servers["references"].start(create_app())
            self._errors["references"] = None
        except Exception as exc:
            self._servers["references"].stop()
            self._errors["references"] = f"{type(exc).__name__}: {exc}"
