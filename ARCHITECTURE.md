# PAH Architecture

PAH (Project Assistant Host) is a local-first host application that combines a native project workspace with independently maintained tools for code analysis, technical documents, Jupyter notebooks, presentations, and research references. This document describes the current architecture of the PAH 0.9.x system and its specialized modules.

The central architectural rule is:

> PAH owns the workspace, shared project context, and cross-tool coordination. Specialized modules own their specialized behavior and remain independently runnable.

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
                + PTY                  Analyzer    Workbench    Manager
                                                     │            │
                                          ┌──────────┼──────┐     ▼
                                          │          │      │ Research Search
                                       Text docs  Notebook  Presentation
```

PAH runs as a local Flask application. The primary host normally listens on `127.0.0.1:8765` and coordinates local services rather than requiring a remote backend.

## Architectural principles

### Local first

Core project work does not require a network connection. Files, editing, terminal sessions, Python environments, local Git, installed modules, notebook execution, and locally available presentation/document tooling operate against local resources.

Remote Git and Overleaf synchronization are separate capabilities that require explicit user permission and explicit actions.

### Modular ownership

The Code Repository Cataloguer, Research Document Workbench, and Research Paper Repository Manager are maintained as separate repositories and included through Git submodules.

They do not depend on one another. Cross-module workflows belong to PAH.

### Host-owned coordination

PAH owns concerns that apply to the whole project rather than to a specialized module:

- workspace selection;
- filesystem operations;
- editor tabs and unsaved-buffer state;
- terminal sessions;
- Python environment selection;
- local and remote Git coordination;
- detachable-window lifecycle;
- presentation state for host surfaces;
- cross-module artifact workflows;
- shared project provenance and traceability conventions.

### Explicit state changes

PAH avoids hidden synchronization and automatic destructive actions. Examples include:

- opening a directory does not run `git init`;
- configured remotes are not contacted automatically;
- code analysis is marked stale after relevant edits instead of being recomputed silently;
- Overleaf synchronization occurs only through explicit Fetch, Pull, or Push actions;
- `.bib` files are not silently imported into the reference library;
- unsaved editor buffers are not silently staged, committed, or overwritten;
- notebook export uses stored outputs rather than silently re-running code.

### Reusable artifacts

The system increasingly treats graphs, figures, diagrams, citations, notebook outputs, and other generated results as reusable project artifacts rather than one-off screen output.

The module that creates an artifact owns its domain semantics. PAH owns the relationship between that artifact and other project outputs.

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

- opening and closing project files;
- tab management;
- dirty-buffer tracking;
- save behavior;
- project-aware Run behavior;
- integration-generated edits and insertions;
- deciding when clean buffers should be refreshed from disk.

Ace owns editor mechanics such as cursor placement, selections, syntax rendering, undo history, search, folding, indentation behavior, and clipboard-friendly editing.

Each open PAH tab is associated with its own Ace editing session so editor state can remain associated with the file while tabs are switched.

Ace is served from PAH's local static assets. Normal runtime does not require a public editor CDN.

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

- opening a detached browser window;
- focusing an existing detached window rather than duplicating it;
- detecting manual window close;
- reattaching dockable surfaces;
- keeping presentation state synchronized.

Tool-specific adapters handle the differences between hosted applications, the native terminal, and companion services.

## Specialized modules

### Code Repository Cataloguer

The Code Analyzer owns repository-analysis algorithms and their full user interface.

PAH integrates with its public façade for operations such as analysis state, serialized entities, dependencies, similarity, clustering, and graph data.

Analysis is explicit. When relevant Python files change, PAH can mark prior results stale. Workflows that depend on analyzer facts require current analysis rather than silently treating stale results as authoritative.

#### Reachable call networks

The Repository Map separates graph discovery from display limits. Call traversal can use a finite hop count or continue until no additional statically resolved call nodes are reachable.

Unlimited traversal is cycle-safe because discovered nodes are visited once and traversal stops at a fixed point.

Conceptually:

```text
focus function
      │
      ▼
breadth-first call traversal
      │
      ├── incoming edges when enabled
      ├── outgoing edges when enabled
      ├── visited-node tracking
      └── finite depth or full closure
```

For broader module, directory, or project scopes, complete call-network views can include all functions/methods and their resolved call relationships rather than enforcing a display-oriented node cap.

#### Canonical graph artifacts

Graph output is not defined only by the rendered SVG. The Analyzer exposes structured network data containing node, edge, traversal, and summary metadata.

Export formats include:

```text
Canonical graph
     │
     ├── JSON      structured PAH/module reuse
     ├── GraphML   graph-analysis tools
     ├── DOT       Graphviz pipelines
     └── SVG       document/presentation rendering
```

The structured representation is the preferred integration boundary for PAH. SVG is a presentation artifact, not the source of graph semantics.

### Research Document Workbench

The Document Workbench owns document-specific behavior such as Markdown/LaTeX/BibTeX workflows, diagram semantics, document builds, notebook semantics, and document/presentation previews.

When hosted inside PAH, the application is adapted to the current PAH workspace rather than forcing users into a second project hierarchy.

#### Text documents

Markdown, LaTeX, BibTeX, and `.diagram` files continue to use the Workbench's text-document model and document-specific rendering/build tools.

#### Notebook document model

`.ipynb` files use a structured notebook surface rather than the text editor.

The Workbench uses the Jupyter notebook format as the persistence boundary and preserves standard notebook structures such as:

- cell IDs;
- Markdown, code, and raw cells;
- notebook and cell metadata;
- Markdown attachments;
- execution counts;
- output MIME bundles.

Unknown metadata is preserved rather than discarded simply because the Workbench does not interpret it.

#### Python kernel execution

Notebook execution is Python-centered.

```text
Workbench notebook UI
       │
       ▼
jupyter_client
       │
       ▼
local ipykernel
       │
       ▼
project Python environment
```

A notebook keeps a persistent kernel session so state can survive between executed cells. Kernel operations include execution, interruption, restart, and shutdown.

Execution occurs with the notebook project as the working directory so relative project paths behave naturally.

Common Jupyter output types are mapped back into notebook output records, including text streams, results, HTML, JSON, raster/vector images, and tracebacks.

#### Live presentation model

Notebook presentation metadata uses the standard Jupyter `slideshow.slide_type` convention rather than a PAH-specific schema.

Supported roles include:

```text
slide
subslide
fragment
skip
notes
```

The Workbench can create a Reveal.js-based live presentation from the same notebook model. The presentation does not require a separate presentation source file.

Where permitted by the presentation UI, code can execute through the same notebook kernel and presentation output can update from the resulting notebook cell output.

#### Notebook export model

Notebook export is intentionally separated from notebook execution.

```text
saved notebook outputs
        │
        ▼
export orchestration
   ├── nbconvert paths
   └── optional Quarto paths
        │
        ▼
document/presentation artifact
```

Export does not automatically execute code. This avoids hidden reruns of expensive, stateful, or destructive cells.

The Workbench uses capability detection so formats are offered according to the local toolchain. HTML, Markdown, and Reveal-style exports rely on notebook conversion support; additional DOCX, PPTX, PDF, and Beamer paths can depend on Quarto and LaTeX availability.

The live presentation path is independent of whether every static export format is available.

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

The goal is not to make the modules import one another. PAH translates between stable public artifacts and APIs.

### Analyzer → document references

PAH can serialize analyzer entities into bounded Markdown or LaTeX blocks. Traceability metadata can identify the source entity, file, qualified name, and line range.

### Analyzer → diagrams

Analyzer entities and relationships can be transformed into human-editable `.diagram` source. Diagram parsing and normalization remain Document Workbench responsibilities.

### Analyzer graphs → reusable artifacts

Full Analyzer networks now have a structured export boundary in addition to SVG rendering.

The intended integration model is:

```text
Code Analyzer
   │
   ├── structured graph JSON
   └── rendered SVG
          │
          ▼
PAH integration layer
   │
   ├── document insertion/reference
   ├── notebook use
   └── presentation use
```

PAH should consume the structured representation when it needs graph semantics and use SVG when it needs a stable visual artifact.

### Diagram → documentation

Generated Mermaid content can be inserted into bounded document regions with an explicit link back to the source `.diagram` file.

### Analyzer → documentation scaffolds

PAH can generate deterministic documentation scaffolds from known analyzer facts. The integration is intended to expose known structure, not to present inferred prose as ground truth.

### References → documents and notebooks

Reference records can be transformed into citation or bibliographic-note snippets. Citation generation uses existing bibliography keys; PAH does not invent citation keys silently.

The same reference primitives can be reused in document prose and notebook Markdown without requiring the Reference Manager to depend on the Document Workbench.

### Notebook artifacts → documents and presentations

Notebook outputs can represent figures, tables, text results, or other project evidence. The architecture treats those outputs as candidates for reuse in documents and presentations rather than requiring independent copies of the same result.

The notebook remains the computational source; downstream documents or presentations should retain enough provenance to identify that source where practical.

### Artifact traceability

PAH can scan explicit markers in Markdown and LaTeX to show relationships among code entities, documents, diagrams, and research papers.

The same model can be extended to structured graph exports and notebook-generated artifacts.

Traceability is based on explicit metadata rather than heuristic guessing.

## Unified artifact model

The emerging system model is centered on reusable project knowledge rather than file-type isolation.

```text
                     Project knowledge
                           │
          ┌────────────────┼────────────────┐
          │                │                │
          ▼                ▼                ▼
      Source code      Research papers   Computation
          │                │                │
          ▼                ▼                ▼
      Analyzer          References        Notebook
          │                │                │
          ├── graph        ├── citation     ├── figures
          ├── entities     └── metadata     ├── results
          └── relations                     └── narrative
          │                │                │
          └──────────────┬─┴────────────────┘
                         ▼
                   PAH integration
                         │
              ┌──────────┼───────────┐
              ▼          ▼           ▼
          Document   Presentation   Other artifact
```

This does not require a monolithic project database. The preferred model is explicit links, stable artifact formats, and provenance that can be understood without hidden application state.

## Git architecture

Git is a host service and is optional for every workspace.

### Local Git

The local Git layer can provide:

- repository detection and initialization;
- status;
- working and staged diffs;
- stage/unstage;
- commits;
- local history;
- local branch inspection and switching;
- recursive submodule inspection;
- local remote-configuration inspection.

A plain directory remains a plain directory until the user explicitly enables Git or opens an existing repository.

### Remote Git permission boundary

Each workspace begins in **Local Only** mode.

Network-capable operations require the user to explicitly switch the current workspace to **Manual Remote**. The permission is enforced in the host Git service rather than only by disabled buttons.

Manual Remote allows explicit operations such as:

- Fetch;
- fast-forward-only Pull;
- Push;
- Clone;
- recursive submodule update when missing objects may require remote access.

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

### Notebook state

Notebook code execution, notebook persistence, and notebook export are separate operations.

A running kernel may contain state that has not yet been represented in saved notebook outputs. Export consumes the saved/current notebook representation and must not silently re-run cells merely to create an output file.

### Reference-library state

Reference-library selection is allowed to remain separate from the code/document workspace. When the hosted Reference Manager changes the active library, PAH can adopt that selection for its own reference integrations.

## Component lifecycle

PAH uses independently versioned Git submodules, Python dependencies, and locally served browser components.

That independence is valuable, but it creates an integration lifecycle that must be managed explicitly:

```text
PAH host revision
      │
      ├── recorded module revisions
      ├── Python runtime dependencies
      ├── local browser assets
      └── PAH-host compatibility hooks
```

A source checkout may currently require local provisioning of pinned browser assets such as Ace, xterm.js, or Reveal.js. Those assets are served locally at runtime rather than loaded from a public CDN.

The architectural direction is to centralize component readiness and update checks at the PAH level so users do not need to understand each module's internal dependency lifecycle. This lifecycle work must preserve the modules' ability to run standalone.

## Privacy and network boundaries

The core system is designed to function locally.

PAH does not require cloud storage or a remote application server for ordinary Workspace, Analysis, Documents, notebooks, presentations, References, terminal, or local Git usage.

Network activity is associated with explicit features, such as:

- Git remote operations;
- Git-backed Overleaf operations;
- external capabilities owned by individual optional modules.

PAH's own remote Git boundary starts disabled for every workspace.

## Third-party browser components

PAH and its modules use established browser components for specialized interaction rather than reimplementing editor, terminal, or presentation engines.

Current examples include:

- Ace for PAH code editing;
- xterm.js and the fit addon for terminal emulation;
- Ace for notebook code-cell editing in the Document Workbench;
- Reveal.js for live notebook presentations.

These assets are intended to be served locally by PAH or the owning module. Source checkouts can populate pinned assets through repository vendor/provisioning scripts; packaged releases can include those assets directly.

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
13. Full graph discovery must be independent of display-oriented graph limits.
14. Structured graph data, not rendered SVG, is the preferred semantic integration boundary.
15. Notebook persistence must preserve valid Jupyter metadata that the Workbench does not interpret.
16. Notebook export must not silently execute notebook code.
17. Notebook presentation metadata should use standard Jupyter slideshow semantics where possible.
18. Reusable artifacts should retain enough provenance to identify their originating analysis, notebook, reference, diagram, or project context.

## Design intent

PAH is not a wrapper around one monolithic application. It is a host that gives several independent local tools a shared project context and a consistent workspace.

The architecture intentionally keeps these concerns distinct:

```text
Workspace ownership         → PAH
Code analysis               → Code Analyzer
Graph discovery/export      → Code Analyzer
Document semantics/builds   → Document Workbench
Notebook execution          → Document Workbench + Jupyter kernel
Notebook presentation       → Document Workbench + Reveal.js
Paper/library management    → Reference Manager
Research acquisition        → Research Search
Version control             → PAH Git service
Overleaf coordination       → PAH integration layer
Artifact relationships      → PAH integration layer
```

This separation allows each component to evolve independently while PAH focuses on the workflows that connect them. The goal is a unified local research/project environment in which code, analysis, documents, notebooks, presentations, references, diagrams, and generated artifacts can remain independently useful while participating in one traceable project workflow.
