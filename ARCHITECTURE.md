# PAH architecture

## Core rule

PAH is the host. `CodeAnalyzer`, `DocumentEngine`, and `ReferenceManager` remain independently runnable repositories and must not import each other.

```text
                         PAH
                          │
              ┌───────────┼───────────┐
              ▼           ▼           ▼
        CodeAnalyzer  DocumentEngine  ReferenceManager
```

Cross-module behavior belongs to PAH's integration layer.

## Host responsibilities

`pah/core/` owns general local-project behavior:

- workspace selection and external state
- filesystem operations
- Python environment selection/creation
- PTY terminal sessions
- running Python source

`pah/web/` owns the shared lightweight editing interface.

PAH metadata is stored outside user projects, under the PAH state directory (normally `~/.local/share/pah/`). Generated documentation and diagrams are ordinary user-requested project files, not hidden PAH metadata.

## Module integration boundaries

### CodeAnalyzer

`pah/integrations/analyzer.py` imports only the public `code_analyzer.CodeAnalyzer` façade.

Analysis is explicit. Editing never invokes analyzer algorithms continuously. After Python-tree changes, existing results are marked stale until the user re-analyzes.

Cross-module generation that depends on code facts requires **current, non-stale analysis**.

### DocumentEngine

`pah/integrations/documents.py` imports only the public `tech_documents.DocumentEngine` façade.

PAH owns arbitrary project roots and the general editor. DocumentEngine supplies document-specific operations such as `.diagram` parsing/normalization and LaTeX compilation.

Analyzer-generated `.diagram` content is validated through DocumentEngine before PAH writes the generated file.

### ReferenceManager

`pah/integrations/references.py` imports only the public `reference_manager.ReferenceManager` façade.

The paper library may be separate from the current code workspace. The adapter exposes common writing-time operations while full archival/checkpoint/library administration stays in the standalone manager.

## PAH-owned cross-module bridges

### `code_document.py`

Creates bounded Markdown/LaTeX code-reference blocks from serialized analyzer entities.

New markers store:

- analyzer entity ID
- source path
- qualified entity name
- line range
- insertion mode (`reference` or `source`)

The same bridge can refresh bounded blocks after explicit re-analysis. Legacy unbounded 0.3/0.4 markers are recognized for traceability but are not rewritten automatically.

### `analysis_diagram.py`

Transforms a serialized analyzer entity plus incoming/outgoing relationships into human-editable `.diagram` source. It contains presentation mapping only; it does not perform code analysis or diagram parsing.

### `diagram_document.py`

Wraps DocumentEngine-generated Mermaid in a bounded Markdown block carrying the source `.diagram` path. This creates traceable `Analyzer → .diagram → Markdown` workflows without introducing a dependency from CodeAnalyzer to DocumentEngine.

### `documentation_scaffold.py`

Generates deterministic Markdown scaffolds from CodeAnalyzer facts. It does not infer undocumented behavior. Human-authored sections remain explicit placeholders.

### `artifact_links.py`

Scans explicit PAH markers in Markdown/LaTeX and builds a host-local traceability view.

Recognized relationships include:

```text
Code entity  → documents that reference it
Paper        → documents that cite/note it
Document     → code entities / diagrams / papers it links
```

Reverse usage searches saved files. Inspection of the active document may use the current unsaved editor buffer.

### `reference_document.py`

Creates Markdown/LaTeX citation or bibliographic-note snippets from serialized ReferenceManager records. Citation mode requires an existing `BibKey`; PAH never invents citation keys.

## Repository layout

```text
Project_Assistant_Host/
├── pah/
│   ├── core/
│   ├── integrations/
│   │   ├── analyzer.py
│   │   ├── documents.py
│   │   ├── references.py
│   │   ├── code_document.py
│   │   ├── reference_document.py
│   │   ├── analysis_diagram.py
│   │   ├── diagram_document.py
│   │   ├── documentation_scaffold.py
│   │   └── artifact_links.py
│   └── web/
├── modules/
│   ├── code_analyzer/          # submodule
│   ├── tech_documents/         # submodule
│   └── reference_manager/      # submodule
├── scripts/
├── tests/
└── run.py
```

## Dependency rules

1. Each major module remains independently runnable.
2. Major modules do not import one another.
3. PAH imports only documented public module façades.
4. Cross-module workflows live under `pah/integrations/` or PAH's web coordination layer.
5. PAH remains useful when optional modules are unavailable.
6. General editing, terminal, environment, and filesystem behavior remain host concerns.
7. Specialized analysis/document/reference behavior remains module-local.
8. Submodules pin known-compatible revisions rather than silently following latest `main`.
9. PAH state must not silently add hidden metadata directories to a user's project.
10. Cross-module snippets enter the unsaved editor buffer first; PAH does not overwrite an open draft behind the editor.
11. Analyzer-backed generation/refresh requires explicit current analysis; stale results are not silently treated as authoritative.
12. Traceability is based on explicit PAH markers, not heuristic text matching.
13. Generated documentation scaffolds may state deterministic analyzer facts but must not pretend inferred prose is ground truth.

## Full standalone UI hosting (PAH 0.6)

PAH 0.6 adds a presentation layer above the public-API integrations. It does **not** merge the standalone Flask applications into the PAH Flask routing table. Their mature frontends use absolute `/api/...` URLs, so merging them directly would cause route collisions and force module-specific frontend rewrites.

Instead, `pah/full_tools.py` runs each installed standalone web app on a private loopback port and PAH exposes them as switchable full work modes:

```text
PAH :8765
  ├── Workspace        native PAH UI
  ├── Analysis   ───── iframe ───── CodeAnalyzer UI :8766
  ├── Documents  ───── iframe ───── Document UI     :8767
  └── References ───── iframe ───── Reference UI    :8768
```

The loopback servers are started lazily when full-tool status is first requested. They are not additional user-managed processes. PAH stops them on host shutdown. Normal internal access logs are suppressed; errors remain visible.

### Document compatibility adapter

The standalone Document Workbench normally owns a `documents/<project>` hierarchy. PAH instead binds it to the current arbitrary workspace through a host-owned `WorkspaceDocumentEngine` adapter. The module UI and module routes remain unchanged. Project create/delete are disabled in this hosted mode; file/folder/document operations act on the real PAH workspace. Build outputs remain under PAH state rather than being injected into the source repository.

### State synchronization rules

1. PAH workspace changes rebind/restart the hosted analyzer UI.
2. The hosted document adapter resolves its project dynamically from the current PAH workspace.
3. The hosted reference manager uses a PAH-state config file, never the module repository's `config.json`.
4. Leaving a hosted tool refreshes clean PAH editor tabs from disk; dirty buffers are preserved.
5. Leaving hosted Analysis marks quick-panel analysis stale because refactor operations may have modified Python source.
6. Reference-library changes made in the hosted manager are adopted by PAH's quick reference adapter.

This hosting layer is a UI integration concern only. `CodeAnalyzer`, `DocumentEngine`, and `ReferenceManager` still do not import PAH or one another.


## Detachable tool windows (PAH 0.7)

Detachment is a host presentation concern. Analysis, Documents, and References continue to run on the same private loopback servers introduced in 0.6; a detached PAH browser window simply hosts the corresponding tool URL in its own frame. PAH intentionally avoids starting a second module backend.

The host keeps at most one detached window reference per tool. A detached top-level mode is focused rather than duplicated. Reattach or window close runs the same conservative state-handoff path used when leaving a full tool, refreshing clean editor buffers and relevant quick-panel state.

The terminal is different because it is PAH-native rather than a hosted module. Detachment transfers PTY polling to the popup while retaining the same server-side terminal id. The docked and detached terminal therefore never race to consume the PTY stream. Reattachment resumes polling in the main PAH window.


## Shared visual identity (PAH 0.7.1)

Visual identity remains a presentation concern. The host retains `pah/web/static/pah.css` as the behavioral/layout baseline and loads `pah-identity.css`, `pah-workspace.css`, and `pah-tools.css` afterward as reviewable overrides.

Standalone/detached services cannot inherit CSS through their iframe/window boundary, so each independently runnable module carries a synchronized copy of the kit's `pah-module-theme.css` plus a narrow `pah-compat.css` adapter for its existing markup. The Code Analyzer inlines these styles with its existing report CSS; Document Workbench, Reference Manager, and Research Search load them from their own static roots. This intentionally duplicates a small presentation asset so every module remains independently runnable.

The visual layer may add semantic classes/data attributes such as `pah-module` and `pah-tool-nav`, but it must not rename existing IDs, routes, APIs, or JavaScript contracts. Layout ownership, detach/reattach behavior, pane collapse behavior, and module boundaries remain unchanged.


## Flexible workspace pane contract (PAH 0.8 Sprint 1)

The native Workspace treats its auxiliary surfaces as presentation panes rather than permanent layout requirements. `project`, `context`, and `terminal` use one host-side pane-state contract with `expanded`/`collapsed` presentation state. Collapsing changes only DOM/layout presentation; it does not clear selected files, analysis/reference/document context, open editor tabs, or the terminal PTY.

The project and context panes collapse to narrow restore rails, and the editor grid expands into the released width. The terminal keeps its existing live PTY while collapsed and routes its existing detach/reattach behavior through the same pane-state helper. No pane state is persisted across browser sessions in Sprint 1; persistence is reserved for the later layout-persistence sprint.

## Compact service launcher (PAH 0.8 Sprint 2)

PAH no longer treats every secondary action as permanent top-bar or full-tool chrome. Workspace remains a direct mode, while Analysis, Documents, and References use compact split launchers: the primary button opens/focuses the tool and the adjacent menu exposes alternate presentation actions such as opening/focusing a detached window and reloading the hosted view.

Host-owned secondary workspace capabilities are grouped under `Tools`: Project Tree, Project Tools, Terminal, detached Terminal Window, and Python Environment. Pane entries route through the same pane-state contract introduced in Sprint 1, so launcher actions do not create duplicate state or separate sessions. Terminal Window continues to transfer the existing PTY rather than starting a second shell.

Launcher menus are transient presentation surfaces. They close on selection, outside click, or Escape, and do not reserve workspace width. Full-tool status strips retain status/binding information but no longer duplicate Detach/Reload controls that are already available from the launcher. This keeps the editor/work area visually dominant while preserving one-click access to core modes.


## Generic dock/detach controller (PAH 0.8 Sprint 3)

PAH 0.8.2 replaces the earlier per-tool popup lifecycle with a single window-surface controller in the host frontend. The controller owns popup references, detached-state detection, focus behavior, popup creation, reattachment, manual-window-close detection, and the shared watcher.

Registered surfaces currently include `analysis`, `documents`, `references`, and `terminal`. Analysis/Documents/References use the hosted-tool adapter and therefore continue to reuse their existing PAH-managed loopback servers. Terminal uses a PTY adapter: detaching transfers polling to the popup and reattaching resumes docked polling against the same terminal id.

Presentation state is normalized as `closed`, `docked`, `collapsed`, or `detached` where meaningful. Tool-specific code is limited to adapters for content/lifecycle differences; it no longer owns generic window bookkeeping. This is intentionally a presentation architecture only: module APIs, routes, workspace binding, terminal APIs, and submodule ownership are unchanged.


## Persistent workspace presentation state (PAH 0.8.3)

Sprint 4 keeps workspace presentation state entirely in the host frontend. `localStorage` key `pah.workspace.layout.v1` records only pane collapse flags, Project/Project Tools widths, Terminal height, and the last normal work mode. It does not store repository contents, credentials, remote configuration, terminal output, or detached-window handles. If browser storage is disabled/corrupt, PAH silently falls back to built-in layout defaults.

The three resizable panes use the existing pane-state contract rather than introducing another layout system. Project Tree and Project Tools retain collapsed rails; Terminal retains the same PTY lifecycle. Resize handles only mutate CSS custom properties (`--project-pane-width`, `--context-pane-width`, `--terminal-pane-height`) and persist the resulting numeric preferences on pointer release.

Detached surfaces remain owned by the PAH 0.8.2 window-surface controller. Their browser window objects and screen positions are intentionally ephemeral and are not restored from persistence. This keeps startup deterministic and avoids popup-policy failures.

Presentation persistence remains local-first: no layout action causes network access and no layout metadata is injected into the user's workspace.
