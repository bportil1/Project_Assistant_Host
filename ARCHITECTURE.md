# PAH Architecture

PAH (Project Assistant Host) is a local-first host application that combines a native project workspace with independently maintained tools for code analysis, technical documents, and research references. This document describes the architecture of PAH 0.9.1.

The central architectural rule is simple:

> PAH owns the workspace and cross-tool coordination. Specialized modules own their specialized behavior and remain independently runnable.

## System overview

```text
                              PAH
                     Project Assistant Host
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
   Native Workspace        Host Services      Hosted Modules
          │                    │                    │
   ┌──────┼──────┐       ┌─────┼─────┐       ┌─────┼──────────┐
   │      │      │       │     │     │       │     │          │
 Editor Files Terminal   Git  Env  Windows  Analysis Documents References
   │              │                         │          │          │
  Ace          xterm.js                 Code       Document   Reference
                + PTY                  Analyzer     Engine      Manager
                                                                  │
                                                                  ▼
                                                            Research Search
```

PAH runs as a local Flask application. The primary host normally listens on `127.0.0.1:8765` and coordinates local services rather than requiring a remote backend.

## Architectural principles

### Local first

Core project work does not require a network connection. Files, editing, terminal sessions, Python environments, local Git, and installed modules operate against local resources.

Remote Git and Overleaf synchronization are separate capabilities that require explicit user permission and explicit actions.

### Modular ownership

The Code Repository Cataloguer, Research Document Workbench, and Research Paper Repository Manager are maintained as separate repositories and included through Git submodules.

They do not depend on one another. Cross-module workflows belong to PAH.

### Host-owned coordination

PAH owns concerns that apply to the whole project rather than to a specialized module:

* workspace selection;
* filesystem operations;
* editor tabs and unsaved-buffer state;
* terminal sessions;
* Python environment selection;
* local and remote Git coordination;
* detachable-window lifecycle;
* presentation state;
* cross-module artifact workflows.

### Explicit state changes

PAH avoids hidden synchronization and automatic destructive actions. Examples include:

* opening a directory does not run `git init`;
* configured remotes are not contacted automatically;
* code analysis is marked stale after relevant edits instead of being recomputed silently;
* Overleaf synchronization occurs only through explicit Fetch, Pull, or Push actions;
* `.bib` files are not silently imported into the reference library;
* unsaved editor buffers are not silently staged, committed, or overwritten.

## Repository organization

```text
Project_Assistant_Host/
├── pah/
│   ├── core/                 # host-owned project services
│   ├── integrations/         # cross-module coordination
│   ├── web/                  # PAH browser UI
│   ├── app.py                # host HTTP application
│   └── full_tools.py         # hosted standalone-tool lifecycle
│
├── modules/
│   ├── code_analyzer/        # Git submodule
│   ├── tech_documents/       # Git submodule
│   └── reference_manager/    # Git submodule
│       └── modules/
│           └── paper_searcher/
│
├── scripts/
├── tests/
└── run.py
```

## Native Workspace

Workspace is PAH-native rather than an embedded specialized module.

### Filesystem

The host filesystem layer operates directly on the selected project directory and supports normal file and directory operations. PAH does not require a proprietary workspace format.

PAH-specific state is stored separately from the project, normally under:

```text
~/.local/share/pah/
```

This keeps opened repositories free from hidden PAH metadata unless the user explicitly creates project artifacts.

### Editor

The Workspace editor uses Ace as the browser editing component.

PAH remains responsible for:

* opening and closing project files;
* tab management;
* dirty-buffer tracking;
* save behavior;
* project-aware Run behavior;
* integration-generated edits and insertions;
* deciding when clean buffers should be refreshed from disk.

Ace owns editor mechanics such as cursor placement, selections, syntax rendering, undo history, search, folding, indentation behavior, and clipboard-friendly editing.

Each open PAH tab is associated with its own Ace editing session so editor state can remain associated with the file while tabs are switched.

Ace is vendored into PAH's static assets. Normal runtime does not load editor code from a CDN.

### Terminal

The native Terminal consists of two layers:

```text
xterm.js in the browser
        ↕ raw terminal input/output
PAH terminal HTTP transport
        ↕
local PTY
        ↕
user shell
```

The shell—not PAH JavaScript—owns command history, tab completion, command-line cursor editing, control sequences, and interactive command behavior.

The terminal manager creates a real PTY and forwards raw terminal data. xterm.js provides browser-side terminal emulation. Window-size changes are propagated back to the PTY so shell applications receive the appropriate terminal dimensions.

One terminal session is retained across docked, collapsed, and detached presentation states.

### Python environments and execution

The host can create and select project Python environments and uses the selected environment when launching the terminal or running Python code through PAH.

This is a Workspace concern rather than a responsibility of Analysis, Documents, or References.

## Workspace presentation model

PAH favors available work area over permanent secondary panels.

The Project Tree, Project Tools, and Terminal are collapsible. Their expanded dimensions can be resized and the resulting presentation preferences can be retained in browser local storage.

Presentation state is separate from project state. Collapsing a pane does not clear its underlying selection, terminal session, open files, or tool data.

Secondary services are exposed through compact menus and transient dialogs instead of permanent sidebars.

## Window surfaces

PAH has a generic window-surface controller for tools that can leave the main browser window.

Depending on the surface, presentation states may include:

```text
closed
  │
  ├── docked
  │     └── collapsed
  │
  └── detached
```

The controller is responsible for common behavior such as:

* opening a detached browser window;
* focusing an existing detached window rather than duplicating it;
* detecting manual window close;
* reattaching dockable surfaces;
* keeping presentation state synchronized.

Tool-specific adapters handle the differences between hosted applications, the native terminal, and companion services.

## Specialized modules

### Code Repository Cataloguer

The Code Analyzer owns repository-analysis algorithms and their full user interface.

PAH integrates with its public façade for operations such as analysis state, serialized entities, dependencies, similarity, clustering, and related project facts.

Analysis is explicit. When relevant Python files change, PAH can mark prior results stale. Workflows that depend on analyzer facts require current analysis rather than silently treating stale results as authoritative.

### Research Document Workbench

The Document Workbench owns document-specific behavior such as Markdown/LaTeX/BibTeX workflows, diagram semantics, document builds, and previews.

When hosted inside PAH, the document application is adapted to the current PAH workspace rather than forcing users into a second project hierarchy.

### Research Paper Repository Manager

The Reference Manager owns paper-library and bibliographic behavior. Its selected paper library may be separate from the current software/document workspace.

PAH can use reference records for writing-time workflows without absorbing the manager's full archival and library-management implementation.

### Research Search

Research Search remains a nested module owned by the Reference Manager. PAH exposes it as an optional companion service through the References menu.

It is not a permanent PAH work mode and does not reserve workspace area when unused.

## Hosted full-tool applications

The mature standalone module interfaces are not merged into PAH's Flask route namespace. Instead, PAH can run the installed standalone applications on private loopback services and display them inside the host or in detachable windows.

Conceptually:

```text
PAH host
  ├── Workspace       native PAH UI
  ├── Analysis   ──── hosted Code Analyzer UI
  ├── Documents  ──── hosted Document Workbench UI
  └── References ──── hosted Reference Manager UI
```

This approach preserves the modules' independent interfaces and route structures while allowing PAH to coordinate project context around them.

The host starts these services lazily and shuts them down with the PAH process.

## Cross-module integration layer

Cross-module behavior belongs under `pah/integrations/` rather than inside the specialized repositories.

Major integration responsibilities include:

### Analyzer → document references

PAH can serialize analyzer entities into bounded Markdown or LaTeX blocks. Traceability metadata can identify the source entity, file, qualified name, and line range.

### Analyzer → diagrams

Analyzer entities and relationships can be transformed into human-editable `.diagram` source. Diagram parsing and normalization remain Document Workbench responsibilities.

### Diagram → documentation

Generated Mermaid content can be inserted into bounded document regions with an explicit link back to the source `.diagram` file.

### Analyzer → documentation scaffolds

PAH can generate deterministic documentation scaffolds from known analyzer facts. The integration is intended to expose known structure, not to present inferred prose as ground truth.

### References → documents

Reference records can be transformed into citation or bibliographic-note snippets. Citation generation uses existing bibliography keys; PAH does not invent citation keys silently.

### Artifact traceability

PAH can scan explicit markers in Markdown and LaTeX to show relationships among code entities, documents, diagrams, and research papers.

Traceability is based on explicit metadata rather than heuristic guessing.

## Git architecture

Git is a host service and is optional for every workspace.

### Local Git

The local Git layer can provide:

* repository detection and initialization;
* status;
* working and staged diffs;
* stage/unstage;
* commits;
* local history;
* local branch inspection and switching;
* recursive submodule inspection;
* local remote-configuration inspection.

A plain directory remains a plain directory until the user explicitly enables Git or opens an existing repository.

### Remote Git permission boundary

Each workspace begins in **Local Only** mode.

Network-capable operations require the user to explicitly switch the current workspace to **Manual Remote**. The permission is enforced in the host Git service rather than only by disabled buttons.

Manual Remote allows explicit operations such as:

* Fetch;
* fast-forward-only Pull;
* Push;
* Clone;
* recursive submodule update when missing objects may require remote access.

It does not start background synchronization.

Changing workspaces resets the remote permission to Local Only.

### Credentials

PAH does not store Git passwords, personal access tokens, or private SSH keys. Git credential helpers and SSH agents remain responsible for authentication.

## Overleaf integration

Overleaf is implemented as an integration over ordinary local files plus the existing Git service.

### ZIP import

Downloaded source archives can be imported locally without enabling Git. The importer validates archive paths, rejects unsafe entries, preserves directory structure, and inspects the resulting project for likely main TeX files, bibliographies, figures, and LaTeX support files.

The imported project is then just an ordinary PAH workspace.

### Git-backed projects

Overleaf Git projects use the same Manual Remote boundary as other remote repositories. PAH recognizes Overleaf-oriented remotes and provides explicit Fetch, fast-forward-only Pull, and Push actions.

Remote comparison state is based on Git tracking references. PAH distinguishes cached state from state refreshed by an explicit Fetch and does not imply continuous knowledge of the remote.

Pull and Push operations include safeguards for dirty worktrees, unsaved editor buffers, unresolved conflicts, and known behind/diverged states where appropriate.

### Bibliography handoff

Detected `.bib` files remain ordinary project files. PAH can open them in the Workspace editor or explicitly import them into the selected Reference Manager library.

No automatic bibliography transfer occurs.

## State and synchronization rules

PAH coordinates several kinds of state without merging their ownership.

### Workspace changes

Opening a different project rebinds host services and hosted tools to the new project where appropriate.

Remote Git permission resets to Local Only.

### Editor versus disk

Dirty editor buffers are not silently overwritten by background or module changes. When PAH returns from a tool that may have modified files, clean buffers can be refreshed from disk while unsaved buffers remain protected.

### Analysis freshness

Python edits can invalidate existing analyzer results. PAH records this as stale analysis rather than automatically invoking analysis algorithms.

### Reference-library state

Reference-library selection is allowed to remain separate from the code/document workspace. When the hosted Reference Manager changes the active library, PAH can adopt that selection for its own reference integrations.

## Privacy and network boundaries

The core system is designed to function locally.

PAH does not require cloud storage or a remote application server for ordinary Workspace, Analysis, Documents, References, terminal, or local Git usage.

Network activity is associated with explicit features, such as:

* Git remote operations;
* Git-backed Overleaf operations;
* external capabilities owned by individual optional modules.

PAH's own remote Git boundary starts disabled for every workspace.

## Third-party browser components

PAH vendors the browser components used for its native editing and terminal experiences:

* Ace for code editing;
* xterm.js and the fit addon for terminal emulation.

These assets are served locally by PAH. A source checkout can populate the pinned assets through the provided vendor scripts; release distributions can include the vendored files directly.

Normal project use does not require loading these components from a CDN.

## Dependency rules

The architecture follows these rules:

1. PAH owns general workspace behavior and cross-module coordination.
2. Specialized modules remain independently runnable.
3. Specialized modules do not import one another through PAH.
4. Cross-module workflows belong to PAH's integration layer.
5. PAH remains useful when optional specialized modules are unavailable.
6. User projects remain ordinary filesystem projects rather than PAH-specific containers.
7. PAH state is kept outside user projects unless the user explicitly creates an artifact.
8. Unsaved editor buffers are protected from silent replacement.
9. Network Git activity requires explicit per-workspace permission and explicit user action.
10. Credentials remain outside PAH's project metadata.
11. Traceability uses explicit markers and known facts rather than hidden heuristic state.
12. Presentation choices such as collapse or detach must not create duplicate backend sessions when one shared session is intended.

## Design intent

PAH is not a wrapper around one monolithic application. It is a host that gives several independent local tools a shared project context and a consistent workspace.

The architecture intentionally keeps these concerns distinct:

```text
Workspace ownership        → PAH
Code analysis              → Code Analyzer
Document semantics/builds  → Document Workbench
Paper/library management   → Reference Manager
Research acquisition       → Research Search
Version control            → PAH Git service
Overleaf coordination      → PAH integration layer
```

This separation allows each component to evolve independently while PAH focuses on the workflows that connect them.

