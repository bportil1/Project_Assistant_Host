from __future__ import annotations

import atexit
import os
import shlex
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file

from .core.environments import EnvironmentError, EnvironmentManager
from .core.filesystem import FileSystemError, FileSystemService
from .core.git import GitError, LocalGitService
from .core.terminal import TerminalError, TerminalManager
from .core.workspace import WorkspaceError, WorkspaceManager
from .full_tools import FullToolManager
from .integrations import (
    AnalysisDiagramBridgeError,
    AnalyzerIntegration,
    AnalyzerIntegrationError,
    ArtifactLinkIndex,
    CodeDocumentBridgeError,
    DocumentIntegration,
    DocumentIntegrationError,
    DiagramDocumentBridgeError,
    DocumentationScaffoldError,
    ReferenceDocumentBridgeError,
    ReferenceIntegration,
    ReferenceIntegrationError,
    code_document_snippet,
    diagram_document_snippet,
    entity_dependency_diagram,
    entity_scaffold,
    file_scaffold,
    project_scaffold,
    reference_document_snippet,
    refresh_code_references,
    suggested_diagram_path,
)


def create_app(*, state_dir: str | Path | None = None) -> Flask:
    app = Flask(__name__, template_folder="web/templates", static_folder="web/static")
    workspaces = WorkspaceManager(state_dir=state_dir)
    environments = EnvironmentManager(workspaces)
    terminals = TerminalManager()
    git_service = LocalGitService(workspaces.root)
    analyzer = AnalyzerIntegration()
    documents = DocumentIntegration(state_dir=workspaces.state_dir / "document-engine")
    references = ReferenceIntegration(state_dir=workspaces.state_dir / "references")
    full_tools = FullToolManager(
        state_dir=workspaces.state_dir / "full-tools",
        analyzer_port=int(os.environ.get("PAH_ANALYSIS_PORT", "8766")),
        documents_port=int(os.environ.get("PAH_DOCUMENTS_PORT", "8767")),
        references_port=int(os.environ.get("PAH_REFERENCES_PORT", "8768")),
    )
    if workspaces.root is not None:
        analyzer.bind(workspaces.root)
        documents.bind(workspaces.root)
        references.bind_workspace(workspaces.root)
    if workspaces.root is not None:
        full_tools.bind_workspace(workspaces.root)
    ref_status = references.status()
    if ref_status.get("configured") and ref_status.get("library_root"):
        full_tools.bind_reference_library(ref_status.get("library_root"))
    atexit.register(terminals.stop_all)
    atexit.register(full_tools.stop_all)

    def fs() -> FileSystemService:
        return FileSystemService(workspaces.require_root())


    def analyzer_relevant_path(relative: str) -> bool:
        """Return whether a pre-existing path can affect Python analysis."""
        try:
            path = fs().resolve(relative, must_exist=True)
        except Exception:
            return str(relative).lower().endswith(".py")
        if path.is_file():
            return path.suffix.lower() == ".py"
        if path.is_dir():
            return any(item.is_file() and item.suffix.lower() == ".py" for item in path.rglob("*.py"))
        return False

    def require_current_analysis() -> None:
        status = analyzer.status()
        if not status.get("analyzed"):
            raise AnalyzerIntegrationError("Analyze the current project before generating analyzer-backed artifacts.")
        if status.get("stale"):
            raise AnalyzerIntegrationError("Re-analyze the project before generating or refreshing analyzer-backed artifacts.")

    def error_response(exc: Exception, status: int = 400):
        return jsonify({"ok": False, "error": str(exc)}), status

    @app.errorhandler(WorkspaceError)
    @app.errorhandler(FileSystemError)
    @app.errorhandler(EnvironmentError)
    @app.errorhandler(TerminalError)
    @app.errorhandler(GitError)
    @app.errorhandler(AnalyzerIntegrationError)
    @app.errorhandler(DocumentIntegrationError)
    @app.errorhandler(CodeDocumentBridgeError)
    @app.errorhandler(ReferenceIntegrationError)
    @app.errorhandler(ReferenceDocumentBridgeError)
    @app.errorhandler(AnalysisDiagramBridgeError)
    @app.errorhandler(DocumentationScaffoldError)
    @app.errorhandler(DiagramDocumentBridgeError)
    def handle_known_error(exc):
        return error_response(exc)

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/workspace")
    def get_workspace():
        return jsonify({"ok": True, **workspaces.snapshot()})

    @app.post("/api/workspace/open")
    def open_workspace():
        payload = request.get_json(force=True)
        root = workspaces.open(payload.get("path", ""))
        analyzer.bind(root)
        documents.bind(root)
        references.bind_workspace(root)
        full_tools.bind_workspace(root)
        git_service.bind(root)
        return jsonify({
            "ok": True,
            "root": str(root),
            **workspaces.snapshot(),
            "analyzer": analyzer.status(),
            "documents": documents.status(),
            "references": references.status(),
            "full_tools": full_tools.status(),
            "git": git_service.status(),
        })


    @app.get("/git")
    def git_workspace():
        return render_template("git.html")

    @app.get("/api/git/status")
    def git_status():
        return jsonify({"ok": True, **git_service.status()})

    @app.post("/api/git/init")
    def git_init():
        return jsonify({"ok": True, **git_service.init()})

    @app.get("/api/git/diff")
    def git_diff():
        staged = request.args.get("staged", "0").lower() in {"1", "true", "yes"}
        path = request.args.get("path") or None
        return jsonify({"ok": True, **git_service.diff(path=path, staged=staged)})

    @app.post("/api/git/stage")
    def git_stage():
        payload = request.get_json(silent=True) or {}
        return jsonify({"ok": True, **git_service.stage(payload.get("paths") or [])})

    @app.post("/api/git/unstage")
    def git_unstage():
        payload = request.get_json(silent=True) or {}
        return jsonify({"ok": True, **git_service.unstage(payload.get("paths") or [])})

    @app.post("/api/git/commit")
    def git_commit():
        payload = request.get_json(silent=True) or {}
        return jsonify({"ok": True, **git_service.commit(str(payload.get("message", "")))})

    @app.get("/api/git/history")
    def git_history():
        limit = request.args.get("limit", "40")
        try:
            parsed_limit = int(limit)
        except ValueError:
            raise GitError("Git history limit must be an integer.")
        return jsonify({"ok": True, "history": git_service.history(limit=parsed_limit)})

    @app.get("/api/git/branches")
    def git_branches():
        return jsonify({"ok": True, **git_service.branches()})

    @app.post("/api/git/branches/switch")
    def git_switch_branch():
        payload = request.get_json(silent=True) or {}
        result = git_service.switch_branch(str(payload.get("name", "")))
        # A branch switch may replace Python/document files on disk. Preserve
        # dirty editor buffers client-side, but invalidate quick analysis so PAH
        # never presents pre-switch analyzer results as current.
        analyzer.mark_stale()
        return jsonify({"ok": True, **result})

    @app.post("/api/git/connectivity")
    def git_connectivity():
        payload = request.get_json(silent=True) or {}
        return jsonify({"ok": True, **git_service.set_connectivity(str(payload.get("mode", "")))})

    @app.get("/api/git/remotes")
    def git_remotes():
        status = git_service.status()
        return jsonify({
            "ok": True,
            "remotes": status.get("remotes", []),
            "tracking": status.get("tracking"),
            "connectivity_mode": status.get("connectivity_mode"),
            "local_only": status.get("local_only", True),
            "remote_enabled": status.get("remote_enabled", False),
        })

    @app.post("/api/git/remotes")
    def git_add_remote():
        payload = request.get_json(silent=True) or {}
        return jsonify({
            "ok": True,
            **git_service.add_remote(str(payload.get("name", "")), str(payload.get("url", ""))),
        })

    @app.delete("/api/git/remotes/<name>")
    def git_remove_remote(name: str):
        return jsonify({"ok": True, **git_service.remove_remote(name)})

    @app.post("/api/git/fetch")
    def git_fetch():
        payload = request.get_json(silent=True) or {}
        return jsonify({
            "ok": True,
            **git_service.fetch(payload.get("remote") or None, prune=bool(payload.get("prune", True))),
        })

    @app.post("/api/git/pull")
    def git_pull():
        payload = request.get_json(silent=True) or {}
        result = git_service.pull(payload.get("remote") or None)
        analyzer.mark_stale()
        return jsonify({"ok": True, **result})

    @app.post("/api/git/push")
    def git_push():
        payload = request.get_json(silent=True) or {}
        return jsonify({
            "ok": True,
            **git_service.push(
                payload.get("remote") or None,
                set_upstream=bool(payload.get("set_upstream", False)),
            ),
        })

    @app.post("/api/git/clone")
    def git_clone():
        payload = request.get_json(silent=True) or {}
        result = git_service.clone(
            str(payload.get("url", "")),
            str(payload.get("destination", "")),
            branch=str(payload.get("branch", "")) or None,
        )
        return jsonify({"ok": True, **result})

    @app.post("/api/git/submodules/update")
    def git_update_submodules():
        payload = request.get_json(silent=True) or {}
        result = git_service.update_submodules(str(payload.get("mode", "recorded")))
        analyzer.mark_stale()
        return jsonify({"ok": True, **result})

    @app.get("/api/tree")
    def get_tree():
        relative = request.args.get("path", ".")
        return jsonify({"ok": True, "path": relative, "tree": fs().list_directory(relative)})

    @app.get("/api/file")
    def read_file():
        result = fs().read_text(request.args.get("path", ""))
        result["language"] = fs().language_for(result["path"])
        return jsonify({"ok": True, **result})

    @app.put("/api/file")
    def save_file():
        payload = request.get_json(force=True)
        relative = payload.get("path", "")
        result = fs().write_text(relative, payload.get("content", ""))
        if str(relative).lower().endswith(".py"):
            analyzer.mark_stale()
        return jsonify({"ok": True, **result, "analyzer_stale": analyzer.status()["stale"]})

    @app.post("/api/fs/create")
    def create_item():
        payload = request.get_json(force=True)
        relative = payload.get("path", "")
        kind = payload.get("kind", "file")
        result = fs().create(relative, kind)
        if kind == "file" and str(relative).lower().endswith(".py"):
            analyzer.mark_stale()
        return jsonify({"ok": True, **result})

    @app.post("/api/fs/rename")
    def rename_item():
        payload = request.get_json(force=True)
        relative = payload.get("path", "")
        relevant = analyzer_relevant_path(relative) or str(payload.get("new_name", "")).lower().endswith(".py")
        result = fs().rename(relative, payload.get("new_name", ""))
        if relevant:
            analyzer.mark_stale()
        return jsonify({"ok": True, **result})

    @app.post("/api/fs/move")
    def move_item():
        payload = request.get_json(force=True)
        relative = payload.get("path", "")
        relevant = analyzer_relevant_path(relative) or str(payload.get("destination", "")).lower().endswith(".py")
        result = fs().move(relative, payload.get("destination", ""))
        if relevant:
            analyzer.mark_stale()
        return jsonify({"ok": True, **result})

    @app.delete("/api/fs")
    def delete_item():
        relative = request.args.get("path", "")
        relevant = analyzer_relevant_path(relative)
        fs().delete(relative)
        if relevant:
            analyzer.mark_stale()
        return jsonify({"ok": True})

    @app.get("/api/environment")
    def environment_status():
        return jsonify({"ok": True, **environments.status()})

    @app.post("/api/environment/create")
    def environment_create():
        payload = request.get_json(silent=True) or {}
        return jsonify({"ok": True, **environments.create(payload.get("path", ".venv"), payload.get("python"))})

    @app.post("/api/environment/select")
    def environment_select():
        payload = request.get_json(force=True)
        return jsonify({"ok": True, **environments.select(payload.get("path"))})

    @app.post("/api/terminal/start")
    def terminal_start():
        session = terminals.start(workspaces.require_root(), environments.process_env())
        return jsonify({"ok": True, "id": session.id})

    @app.get("/api/terminal/read")
    def terminal_read():
        return jsonify({"ok": True, **terminals.read(request.args.get("id", ""))})

    @app.post("/api/terminal/input")
    def terminal_input():
        payload = request.get_json(force=True)
        terminals.write(payload.get("id", ""), payload.get("data", ""))
        return jsonify({"ok": True})

    @app.delete("/api/terminal")
    def terminal_stop():
        terminals.stop(request.args.get("id", ""))
        return jsonify({"ok": True})

    @app.post("/api/run")
    def run_python():
        payload = request.get_json(force=True)
        relative = payload.get("path", "")
        file_path = fs().resolve(relative, must_exist=True)
        if not file_path.is_file() or file_path.suffix.lower() != ".py":
            raise FileSystemError("Run File currently supports Python (.py) files only.")
        session_id = payload.get("terminal_id")
        if not session_id:
            session_id = terminals.start(workspaces.require_root(), environments.process_env()).id
        args = payload.get("args", [])
        if not isinstance(args, list):
            raise FileSystemError("Run arguments must be a list.")
        command = shlex.join([str(environments.interpreter()), str(file_path), *[str(x) for x in args]])
        terminals.write(session_id, command + "\n")
        return jsonify({"ok": True, "terminal_id": session_id, "command": command})

    @app.get("/api/analyzer/status")
    def analyzer_status():
        if workspaces.root is not None:
            analyzer.bind(workspaces.root)
        return jsonify({"ok": True, **analyzer.status()})

    @app.post("/api/analyzer/analyze")
    def analyzer_analyze():
        analyzer.bind(workspaces.require_root())
        return jsonify({"ok": True, **analyzer.analyze()})

    @app.get("/api/analyzer/functions")
    def analyzer_functions():
        return jsonify({"ok": True, "functions": analyzer.functions(), "stale": analyzer.status()["stale"]})

    @app.get("/api/analyzer/file")
    def analyzer_file():
        return jsonify({"ok": True, **analyzer.file_entities(request.args.get("path", ""))})

    @app.get("/api/analyzer/entity")
    def analyzer_entity():
        return jsonify({"ok": True, "entity": analyzer.entity(request.args.get("id", "")), "stale": analyzer.status()["stale"]})

    @app.get("/api/analyzer/dependencies")
    def analyzer_dependencies():
        return jsonify({"ok": True, **analyzer.dependencies(request.args.get("id", ""))})

    @app.get("/api/analyzer/similar")
    def analyzer_similar():
        return jsonify({
            "ok": True,
            **analyzer.similar(
                request.args.get("id", ""),
                limit=int(request.args.get("limit", 8)),
                context_depth=int(request.args.get("context_depth", 1)),
                distance_decay=float(request.args.get("distance_decay", 0.5)),
                external_import_weight=float(request.args.get("external_import_weight", 0.20)),
            ),
        })

    @app.post("/api/analyzer/compare")
    def analyzer_compare():
        payload = request.get_json(silent=True) or {}
        return jsonify({
            "ok": True,
            **analyzer.compare(
                payload.get("left_id", ""),
                payload.get("right_id", ""),
                context_depth=int(payload.get("context_depth", 1)),
                distance_decay=float(payload.get("distance_decay", 0.5)),
                external_import_weight=float(payload.get("external_import_weight", 0.20)),
            ),
        })

    @app.post("/api/analyzer/matrix")
    def analyzer_matrix():
        payload = request.get_json(silent=True) or {}
        return jsonify({
            "ok": True,
            **analyzer.matrix(
                include_matrix=bool(payload.get("include_matrix", False)),
                context_depth=int(payload.get("context_depth", 1)),
                distance_decay=float(payload.get("distance_decay", 0.5)),
                external_import_weight=float(payload.get("external_import_weight", 0.20)),
                ordering=str(payload.get("ordering", "qualified_name")),
            ),
        })

    @app.post("/api/analyzer/duplicates")
    def analyzer_duplicates():
        payload = request.get_json(silent=True) or {}
        return jsonify({
            "ok": True,
            **analyzer.duplicates(
                threshold=float(payload.get("threshold", 0.65)),
                limit=int(payload.get("limit", 25)),
                factor_limit=int(payload.get("factor_limit", 12)),
                context_depth=int(payload.get("context_depth", 1)),
                distance_decay=float(payload.get("distance_decay", 0.5)),
                external_import_weight=float(payload.get("external_import_weight", 0.20)),
                include_source=bool(payload.get("include_source", False)),
            ),
        })

    @app.post("/api/analyzer/clusters")
    def analyzer_clusters():
        payload = request.get_json(silent=True) or {}
        return jsonify({
            "ok": True,
            **analyzer.clusters(
                k=int(payload.get("k", 3)),
                random_state=int(payload.get("random_state", 42)),
                context_depth=int(payload.get("context_depth", 1)),
                distance_decay=float(payload.get("distance_decay", 0.5)),
                external_import_weight=float(payload.get("external_import_weight", 0.20)),
                ordering=str(payload.get("ordering", "qualified_name")),
                common_factor_limit=int(payload.get("common_factor_limit", 12)),
            ),
        })


    @app.get("/api/documents/status")
    def document_status():
        if workspaces.root is not None:
            documents.bind(workspaces.root)
        return jsonify({"ok": True, **documents.status()})

    @app.get("/api/documents/files")
    def document_files():
        documents.bind(workspaces.require_root())
        return jsonify({"ok": True, "files": documents.files()})

    @app.post("/api/documents/diagram/parse")
    def document_parse_diagram():
        payload = request.get_json(silent=True) or {}
        return jsonify({
            "ok": True,
            **documents.parse_diagram(
                str(payload.get("content", "")),
                direction=payload.get("direction"),
                preset=payload.get("preset"),
            ),
        })

    @app.post("/api/documents/latex/compile")
    def document_compile_latex():
        documents.bind(workspaces.require_root())
        payload = request.get_json(silent=True) or {}
        return jsonify({"ok": True, **documents.compile_latex(str(payload.get("path", "")))})

    @app.get("/api/documents/build")
    def document_build_file():
        path = documents.build_file(
            request.args.get("build_id", ""),
            request.args.get("filename", ""),
        )
        return send_file(path, mimetype="application/pdf", as_attachment=False, download_name=path.name)

    @app.post("/api/documents/code-snippet")
    def document_code_snippet():
        payload = request.get_json(silent=True) or {}
        target = str(payload.get("target", ""))
        target_path = fs().resolve(target, must_exist=True)
        if not target_path.is_file():
            raise FileSystemError("Code-reference target must be a file.")
        entity = analyzer.entity(str(payload.get("entity_id", "")))
        snippet = code_document_snippet(
            entity,
            target,
            include_source=bool(payload.get("include_source", False)),
        )
        return jsonify({"ok": True, "target": target, "snippet": snippet, "entity": entity})


    @app.get("/api/full-tools/status")
    def full_tools_status():
        full_tools.start_available()
        return jsonify({"ok": True, **full_tools.status()})

    @app.post("/api/full-tools/refresh")
    def full_tools_refresh():
        if workspaces.root is not None:
            full_tools.bind_workspace(workspaces.root)
        full_tools.start_available()
        ref_status = references.status()
        full_tools.bind_reference_library(ref_status.get("library_root") if ref_status.get("configured") else None)
        return jsonify({"ok": True, **full_tools.status()})

    @app.post("/api/research-search/launch")
    def research_search_launch():
        try:
            return jsonify({"ok": True, **full_tools.launch_research_search()})
        except RuntimeError as exc:
            return error_response(exc, 503)

    @app.post("/api/full-tools/return")
    def full_tools_return():
        payload = request.get_json(silent=True) or {}
        mode = str(payload.get("mode", ""))
        # Full Analysis retains the standalone refactor controls, so returning
        # from it conservatively invalidates the quick-panel analyzer cache.
        if mode == "analysis":
            analyzer.mark_stale()
        # If the user changed the library from inside the full Reference Manager,
        # adopt that selection back into PAH's quick reference surface.
        if mode == "references":
            tool_root = full_tools.reference_library_from_tool()
            current = references.status().get("library_root")
            if tool_root is not None and str(tool_root) != str(current or ""):
                references.select_library(tool_root)
        return jsonify({
            "ok": True,
            "analyzer": analyzer.status(),
            "references": references.status(),
        })


    @app.get("/api/references/status")
    def reference_status():
        references.bind_workspace(workspaces.root)
        tool_root = full_tools.reference_library_from_tool()
        current = references.status().get("library_root")
        if tool_root is not None and str(tool_root) != str(current or ""):
            references.select_library(tool_root)
        return jsonify({"ok": True, **references.status()})

    @app.post("/api/references/library")
    def reference_select_library():
        payload = request.get_json(silent=True) or {}
        result = references.select_library(str(payload.get("path", "")))
        full_tools.bind_reference_library(result.get("library_root"))
        return jsonify({"ok": True, **result})

    @app.delete("/api/references/library")
    def reference_clear_library():
        result = references.clear_library()
        full_tools.bind_reference_library(None)
        return jsonify({"ok": True, **result})

    @app.post("/api/references/library/use-workspace")
    def reference_use_workspace():
        references.bind_workspace(workspaces.require_root())
        result = references.use_workspace()
        full_tools.bind_reference_library(result.get("library_root"))
        return jsonify({"ok": True, **result})

    @app.get("/api/references/papers")
    def reference_papers():
        return jsonify({
            "ok": True,
            **references.papers(
                query=request.args.get("q", ""),
                status=request.args.get("status", ""),
                topic=request.args.get("topic", ""),
                limit=int(request.args.get("limit", 500)),
            ),
        })

    @app.get("/api/references/paper")
    def reference_paper():
        return jsonify({"ok": True, "paper": references.paper(request.args.get("id", ""))})

    @app.put("/api/references/paper")
    def reference_save_paper():
        payload = request.get_json(silent=True) or {}
        paper = references.save_paper(
            str(payload.get("paper_id", "")),
            status=payload.get("status"),
            notes=payload.get("notes"),
        )
        return jsonify({"ok": True, "paper": paper, "summary": references.status().get("summary")})

    @app.post("/api/references/sync")
    def reference_sync():
        payload = request.get_json(silent=True) or {}
        return jsonify({
            "ok": True,
            **references.sync(
                detect_moves=bool(payload.get("detect_moves", True)),
                extract_titles=bool(payload.get("extract_titles", False)),
            ),
        })

    @app.get("/api/references/duplicates")
    def reference_duplicates():
        return jsonify({"ok": True, "groups": references.duplicates()})

    @app.post("/api/references/bibtex/import")
    def reference_import_bibtex():
        payload = request.get_json(silent=True) or {}
        return jsonify({"ok": True, **references.import_bibtex(str(payload.get("content", "")))})

    @app.get("/api/references/pdf")
    def reference_pdf():
        path = references.pdf_file(request.args.get("id", ""))
        return send_file(path, mimetype="application/pdf", as_attachment=False, download_name=path.name)

    @app.post("/api/references/document-snippet")
    def reference_document_snippet_route():
        payload = request.get_json(silent=True) or {}
        target = str(payload.get("target", ""))
        target_path = fs().resolve(target, must_exist=True)
        if not target_path.is_file():
            raise FileSystemError("Reference target must be a file.")
        paper = references.paper(str(payload.get("paper_id", "")))
        snippet = reference_document_snippet(
            paper,
            target,
            kind=str(payload.get("kind", "citation")),
        )
        return jsonify({"ok": True, "target": target, "snippet": snippet, "paper": paper})

    # ------------------------------------------------------------------
    # PAH-owned cross-module workflows (0.5)
    # ------------------------------------------------------------------
    @app.post("/api/workflows/diagram/entity")
    def workflow_entity_diagram():
        require_current_analysis()
        payload = request.get_json(silent=True) or {}
        entity = analyzer.entity(str(payload.get("entity_id", "")))
        dependencies = analyzer.dependencies(str(entity.get("id", "")))
        source = entity_dependency_diagram(
            entity,
            dependencies,
            direction=str(payload.get("direction", "LR") or "LR"),
            preset=str(payload.get("preset", "architecture") or "architecture"),
        )
        # Validation/rendering remains DocumentEngine-owned.
        parsed = documents.parse_diagram(source)
        target = str(payload.get("target") or suggested_diagram_path(entity))
        if not target.lower().endswith(".diagram"):
            raise FileSystemError("Generated analyzer diagrams must use the .diagram extension.")
        target_path = fs().resolve(target)
        if target_path.exists():
            raise FileSystemError(f"Diagram already exists: {target}")
        result = fs().write_text(target, source)
        return jsonify({
            "ok": True,
            "path": result["path"],
            "source": source,
            "mermaid": parsed.get("mermaid", ""),
            "graph": parsed.get("graph", {}),
            "entity": entity,
        })

    @app.post("/api/workflows/diagram/document-snippet")
    def workflow_diagram_document_snippet():
        payload = request.get_json(silent=True) or {}
        diagram_path = str(payload.get("diagram_path", ""))
        target = str(payload.get("target", ""))
        diagram_file = fs().resolve(diagram_path, must_exist=True)
        target_file = fs().resolve(target, must_exist=True)
        if not diagram_file.is_file() or diagram_file.suffix.lower() != ".diagram":
            raise FileSystemError("Open a .diagram file before inserting it into a document.")
        if not target_file.is_file():
            raise FileSystemError("Diagram insertion target must be a file.")
        parsed = documents.parse_diagram(str(payload.get("content", "")))
        snippet = diagram_document_snippet(diagram_path, target, str(parsed.get("mermaid", "")))
        return jsonify({"ok": True, "target": target, "snippet": snippet, "graph": parsed.get("graph", {})})

    @app.post("/api/workflows/docs/scaffold")
    def workflow_documentation_scaffold():
        require_current_analysis()
        payload = request.get_json(silent=True) or {}
        kind = str(payload.get("kind", "entity") or "entity").lower()
        target = str(payload.get("target") or "").strip()

        if kind == "entity":
            entity = analyzer.entity(str(payload.get("entity_id", "")))
            content = entity_scaffold(entity, analyzer.dependencies(str(entity.get("id", ""))))
            default_name = str(entity.get("qualified_name") or entity.get("name") or "entity").replace(".", "_")
            suggested = f"docs/code/{default_name}.md"
        elif kind == "file":
            path = str(payload.get("path", ""))
            content = file_scaffold(path, analyzer.file_entities(path)["entities"])
            stem = Path(path).stem or "module"
            suggested = f"docs/code/{stem}.md"
        elif kind == "project":
            content = project_scaffold(analyzer.overview(), analyzer.functions())
            suggested = "docs/technical_overview.md"
        else:
            raise DocumentationScaffoldError("Scaffold kind must be entity, file, or project.")

        destination = target or suggested
        if not destination.lower().endswith((".md", ".markdown")):
            raise FileSystemError("PAH 0.5 documentation scaffolds are Markdown files.")
        destination_path = fs().resolve(destination)
        if destination_path.exists():
            raise FileSystemError(f"Documentation file already exists: {destination}")
        result = fs().write_text(destination, content)
        return jsonify({"ok": True, "path": result["path"], "content": content, "kind": kind})

    @app.post("/api/workflows/code/refresh")
    def workflow_refresh_code_references():
        require_current_analysis()
        payload = request.get_json(silent=True) or {}
        target = str(payload.get("target", ""))
        target_path = fs().resolve(target, must_exist=True)
        if not target_path.is_file():
            raise FileSystemError("Code-reference refresh target must be a file.")
        result = refresh_code_references(
            str(payload.get("content", "")),
            target,
            analyzer.resolve_entity_marker,
        )
        return jsonify({"ok": True, "target": target, **result, "stale": analyzer.status()["stale"]})

    @app.post("/api/workflows/links")
    def workflow_artifact_links():
        payload = request.get_json(silent=True) or {}
        index = ArtifactLinkIndex(workspaces.require_root())
        data = index.index()
        response = {"ok": True, "summary": data["summary"]}

        entity_id = str(payload.get("entity_id", "")).strip()
        if entity_id:
            entity = analyzer.entity(entity_id)
            response["entity"] = entity
            response["entity_used_in"] = index.entity_usage(entity)

        paper_id = str(payload.get("paper_id", "")).strip()
        if paper_id:
            response["paper_id"] = paper_id
            response["paper_used_in"] = index.paper_usage(paper_id)

        document_path = str(payload.get("document_path", "")).strip()
        if document_path:
            content = payload.get("document_content")
            if content is None:
                content = fs().read_text(document_path)["content"]
            response["document"] = index.inspect_content(document_path, str(content))
        return jsonify(response)

    @app.get("/api/health")
    def health():
        return jsonify({
            "ok": True,
            "service": "PAH",
            "version": "0.8.6",
            "analyzer": analyzer.status(),
            "documents": documents.status(),
            "references": references.status(),
            "full_tools": full_tools.status(),
            "git": git_service.status(),
        })

    return app
