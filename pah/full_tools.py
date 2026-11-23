from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path

from pah_jobs.exchange import monitor_directory
from typing import Any, Callable

from .hosted_compat import code_analyzer_app, document_workbench_app, reference_manager_app

from werkzeug.serving import WSGIRequestHandler, make_server


class _WorkspaceMonitorWSGI:
    """Bind a hosted module request to its explicit workspace for read-only telemetry."""

    def __init__(self, application, workspace: Path | None):
        self.application = application
        self.workspace = workspace

    def __call__(self, environ, start_response):
        if self.workspace is None:
            return self.application(environ, start_response)
        with monitor_directory(self.workspace / ".pah" / "job_monitor"):
            return self.application(environ, start_response)


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
    """Compatibility host for pre-existing standalone UI surfaces.

    This maintains the old iframe presentation until modules opt into explicit
    process launch contracts. It must not own, replace, or restrict a module's
    internal project manager. Rebinding PAH's workspace does not mutate an
    already-running hosted application.
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
        self._workspace: Path | None = None  # next requested host workspace
        self._analysis_bound: Path | None = None  # actual scope of running analysis UI
        self._document_root: Path | None = None  # hint for PAH document bridges only
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
        self._analysis_change_callback: Callable[[Any, str], Any] | None = None

    def set_analysis_change_callback(
        self, callback: Callable[[Any, str], Any] | None
    ) -> None:
        """Receive hosted Code Analyzer lifecycle events without coupling it to PAH."""
        self._analysis_change_callback = callback

    def bind_workspace(self, root: str | Path | None) -> None:
        """Update PAH's selection, never silently rebind a running module.

        Code Analyzer stays pinned to the repository it opened. Its explicit
        stop/start lifecycle is the only way to rebind a legacy hosted UI.
        """
        self._workspace = Path(root).expanduser().resolve() if root else None

    def analysis_bound_to(self, root: str | Path | None) -> bool:
        """True only for the running hosted analyzer's original repository."""
        return (
            self._servers["analysis"].running
            and root is not None
            and self._analysis_bound is not None
            and self._analysis_bound == Path(root).expanduser().resolve()
        )

    def bind_document_root(self, root: str | Path | None) -> None:
        """Record a PAH document-resource hint, not a Workbench project root."""
        self._document_root = Path(root).expanduser().resolve() if root else None

    def bind_reference_library(self, root: str | Path | None) -> None:
        self._reference_library = Path(root).expanduser().resolve() if root else None
        # The module owns its running library selection. Initial configuration
        # may be seeded before launch, but a host workspace switch must not
        # overwrite Reference Manager's active config behind its back.
        if not self._servers["references"].running and not self._reference_config_path().exists():
            self._write_reference_config()

    def start_available(self) -> None:
        self._start_documents()
        self._start_references()
        if self._workspace is not None:
            self._start_analysis()

    def start(self, name: str) -> dict[str, Any]:
        """Start one hosted standalone module UI by stable surface id."""
        starters = {
            "analysis": self._start_analysis,
            "documents": self._start_documents,
            "references": self._start_references,
        }
        try:
            starter = starters[str(name)]
        except KeyError as exc:
            raise KeyError(f"Unknown full-tool surface {name!r}") from exc
        starter()
        return dict(self.status()["tools"][str(name)])

    def stop(self, name: str) -> None:
        try:
            self._servers[str(name)].stop()
        except KeyError as exc:
            raise KeyError(f"Unknown full-tool surface {name!r}") from exc
        if name == "analysis":
            self._analysis_bound = None

    def stop_all(self) -> None:
        for server in self._servers.values():
            server.stop()
        self._analysis_bound = None

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
        tools["analysis"]["bound_workspace"] = str(self._analysis_bound) if self._analysis_bound else None
        tools["analysis"]["selected_workspace"] = str(self._workspace) if self._workspace else None
        tools["analysis"]["selection_differs"] = bool(
            self._servers["analysis"].running and self._workspace != self._analysis_bound
        )
        # Workbench is no longer scoped to the PAH document resource.
        tools["documents"]["bound_workspace"] = None
        tools["documents"]["suggested_document_root"] = str(self._document_root) if self._document_root else None
        tools["documents"]["project_owner"] = "tech_documents"
        tool_library = self.reference_library_from_tool() if self._servers["references"].running else None
        tools["references"]["library_root"] = (
            str(tool_library or self._reference_library) if (tool_library or self._reference_library) else None
        )
        tools["research_search"] = self.research_search_status()
        return {"tools": tools}

    # ------------------------------------------------------------------
    # Reference Manager companion service: Research Search
    # ------------------------------------------------------------------
    def _research_search_module_root(self) -> Path | None:
        try:
            import reference_manager

            return Path(reference_manager.__file__).resolve().parents[1] / "modules" / "paper_searcher"
        except Exception:
            return None

    def research_search_status(self) -> dict[str, Any]:
        module_root = self._research_search_module_root()
        run_file = module_root / "run.py" if module_root is not None else None
        available = bool(run_file and run_file.exists())
        return {
            "available": available,
            "url": "http://127.0.0.1:8770/research-search" if available else None,
            "error": None if available else (
                "Research Search module is not installed under the Reference Manager nested modules directory."
            ),
            "owner": "references",
            "window_only": True,
        }

    def launch_research_search(self) -> dict[str, Any]:
        """Ask the hosted Reference Manager to launch its Research Search companion.

        PAH intentionally does not own or reimplement the nested paper_searcher
        process. The Reference Manager remains the service owner; PAH only
        coordinates presentation and window lifecycle.
        """
        status = self.research_search_status()
        if not status["available"]:
            raise RuntimeError(status["error"] or "Research Search is unavailable.")

        self._start_references()
        if self._errors.get("references"):
            raise RuntimeError(self._errors["references"] or "Reference Manager is unavailable.")

        endpoint = self._servers["references"].url.rstrip("/") + "/api/research-search/launch"
        request = urllib.request.Request(
            endpoint,
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=6.0) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                message = str(payload.get("error") or exc.reason)
            except Exception:
                message = str(exc.reason)
            raise RuntimeError(message) from exc
        except Exception as exc:
            raise RuntimeError(f"Unable to launch Research Search through Reference Manager: {exc}") from exc

        if payload.get("error"):
            raise RuntimeError(str(payload["error"]))
        return {
            "url": str(payload.get("url") or status["url"]),
            "already_running": bool(payload.get("already_running", False)),
            "owner": "references",
        }

    # ------------------------------------------------------------------
    # Analyzer full UI (legacy hosted compatibility)
    # ------------------------------------------------------------------
    def _start_analysis(self) -> None:
        server = self._servers["analysis"]
        if server.running:
            return  # Running analyzers cannot be rebound by PAH workspace changes.
        workspace = self._workspace
        if workspace is None:
            self._analysis_bound = None
            self._errors["analysis"] = "Open a PAH workspace before using full Analysis mode."
            return
        try:
            with monitor_directory(workspace / ".pah" / "job_monitor"):
                app = code_analyzer_app(workspace, on_analysis=self._analysis_change_callback)
            server.start(_WorkspaceMonitorWSGI(app, workspace))
            self._analysis_bound = workspace
            self._errors["analysis"] = None
        except Exception as exc:
            server.stop()
            self._analysis_bound = None
            self._errors["analysis"] = f"{type(exc).__name__}: {exc}"

    # ------------------------------------------------------------------
    # Document Workbench full UI -- Workbench owns its own projects.
    # ------------------------------------------------------------------
    def _start_documents(self) -> None:
        server = self._servers["documents"]
        if server.running:
            return
        try:
            # Do not replace DocumentEngine, hide New Project, or bind module roots.
            app = document_workbench_app()
            server.start(app)
            self._errors["documents"] = None
        except Exception as exc:
            server.stop()
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
        server = self._servers["references"]
        if server.running:
            return
        try:
            if not self._reference_config_path().exists():
                self._write_reference_config()
            app = reference_manager_app(self._reference_config_path())
            server.start(_WorkspaceMonitorWSGI(app, self._workspace))
            self._errors["references"] = None
        except Exception as exc:
            server.stop()
            self._errors["references"] = f"{type(exc).__name__}: {exc}"
