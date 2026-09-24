# PAH — Project Assistant Host

PAH is a local-first workspace for software projects, technical documents, notebooks, research references, and related project artifacts. It combines a native project workspace with independently maintained analysis, document, and reference tools while keeping the underlying files and repositories ordinary and accessible outside PAH.

PAH is intended for people who want one place to move between code, analysis, writing, notebooks, presentations, literature, terminal work, and project history without turning the application into a monolithic IDE or requiring a cloud service.

**Current PAH host version:** 0.9.12

## Highlights

- Local project browser and file operations
- Ace-based code editor with real cursor, selection, undo, syntax highlighting, folding, search, and normal clipboard behavior
- xterm.js terminal connected to a real local PTY, with shell history, tab completion, control keys, interactive programs, and resize support
- Collapsible and resizable workspace panes
- Detachable Analysis, Documents, References, Git, and Terminal surfaces
- Python virtual-environment creation and selection
- Direct execution of the active Python file
- Repository analysis through the Code Repository Cataloguer
- Full reachable call-network exploration with JSON, GraphML, Graphviz DOT, and SVG export
- Markdown, LaTeX, BibTeX, diagram, and document-build workflows through the Research Document Workbench
- First-class Jupyter notebook creation, editing, execution, output handling, and live presentation
- Notebook export paths for common document and presentation formats when the required local tooling is available
- PDF, BibTeX, citation, and literature-library workflows through the Research Paper Repository Manager
- Research Search as an optional companion service
- Optional local Git tools, with remote Git disabled until explicitly enabled
- Overleaf ZIP import and optional Git-backed Overleaf synchronization
- Cross-module workflows for code references, diagrams, citations, graph artifacts, notebooks, and traceable documentation

## Interface

PAH has four primary work modes:

```text
[ Workspace ] [ Analysis ] [ Documents ] [ References ]
```

Secondary services are opened on demand from menus instead of occupying permanent screen space.

### Workspace

Workspace is the native PAH environment for everyday project work. It includes:

- local filesystem browsing;
- file and directory creation, rename, move, and delete;
- tabbed editing through Ace;
- save, undo/redo, search, indentation, folding, and normal copy/paste;
- an xterm.js terminal backed by a real shell PTY;
- Python environment selection and creation;
- active-file Python execution;
- contextual project tools;
- optional Git controls.

The Project Tree, Project Tools, and Terminal panes are collapsible and resizable. The editor expands into reclaimed space when a pane is collapsed. Layout preferences are stored locally in the browser rather than written into the opened project.

### Analysis

Analysis hosts the Code Repository Cataloguer against the current workspace. Depending on the repository and module configuration, it can provide:

- Python entity and structure inspection;
- incoming and outgoing dependencies;
- repository maps;
- pairwise source and semantic comparisons;
- global similarity matrices;
- clustering;
- duplication analysis;
- dependency views;
- bounded or full reachable call-network exploration.

Repository Map traversal can follow a finite number of hops or continue until the complete reachable call neighborhood has been discovered. Broader module, directory, or project scopes can also expose complete call networks rather than stopping at a small display-oriented cap.

The resulting graph is reusable outside the Analyzer. Supported graph exports include:

- JSON for structured reuse and PAH integration;
- GraphML for graph-analysis tools;
- Graphviz DOT for graph-layout pipelines;
- SVG for documents and presentations.

Analysis remains explicit. Editing source code marks previously generated analysis as stale rather than continuously re-running expensive analysis in the background.

### Documents

Documents hosts the Research Document Workbench against the current PAH workspace. It supports workflows around:

- Markdown;
- LaTeX;
- BibTeX;
- `.diagram` files;
- diagrams and Mermaid output;
- LaTeX builds;
- generated previews and PDFs;
- technical-document authoring;
- Jupyter notebooks.

#### Jupyter notebooks

`.ipynb` files are first-class Workbench documents rather than raw JSON files. The Workbench supports:

- Markdown, code, and raw cells;
- add, delete, duplicate, reorder, and cell-type conversion;
- persistent local Python kernel execution;
- run-cell, run-all, interrupt, restart, and clear-output controls;
- common Jupyter text, HTML, image, JSON, result, stream, and traceback outputs;
- preservation of notebook metadata, cell metadata, cell IDs, attachments, execution counts, and outputs.

Notebook execution is Python-centered and uses the project environment and working directory so local imports and relative project paths behave naturally.

#### Live notebook presentations

Notebooks can also act as presentation sources. Cells can use standard Jupyter slideshow roles such as slide, sub-slide, fragment, skip, and speaker notes. The Workbench can enter a Reveal.js-based live presentation mode without creating a separate presentation copy.

The presentation remains connected to the notebook and its running Python kernel, allowing code cells to be executed during a presentation when desired.

#### Notebook export

The Workbench provides a unified export interface rather than requiring users to remember several unrelated command-line tools. Available formats depend on the local environment. Common paths include HTML, Markdown, and Reveal.js presentation output through notebook conversion tooling, with additional Word, PowerPoint, PDF, or Beamer output available when compatible Quarto and LaTeX tooling is installed.

Export uses the outputs already stored in the notebook and does not automatically re-run notebook code.

The live presentation workflow is the most direct presentation path. File export remains dependent on the capabilities of the locally installed conversion toolchain.

PAH can also import downloaded Overleaf source ZIPs as ordinary local projects. Git-backed Overleaf projects can be cloned and synchronized when remote Git access has been explicitly enabled.

### References

References hosts the Research Paper Repository Manager and can work with a paper library that is separate from the current source-code workspace. Its responsibilities include:

- PDF libraries;
- paper metadata;
- BibTeX records;
- topics, statuses, and notes;
- duplicate-management workflows;
- citation and document integration;
- local paper organization.

Research Search is available as an optional companion window through the References menu when its nested module is installed.

## Goal-oriented labs and reusable modules

PAH is evolving from a fixed set of work modes toward goal-oriented lab
collections built from reusable modules. A lab is a host-owned workflow view,
not a repository owner or plugin sandbox.

The first collection identities are **Code Analysis Lab** and **ML Lab**. A
single module may appear in more than one collection, and modules are not
required to own a browser UI. This allows specialized UI-owning tools and
headless engines to participate through the same small host contract.

PAH exposes the current semantic registry through:

```text
GET /api/orchestration/modules
GET /api/orchestration/labs
GET /api/orchestration/labs/<lab-id>
```

Optional standalone modules can register semantic manifests through the
`pah.modules` Python entry-point group rather than requiring a new hard-coded
import in the host. Independently runnable modules can separately expose
launch/status/shutdown adapters through the `pah.runtimes` entry-point group.
The runtime contract is UI-neutral: an adapter may return a PAH-owned surface,
a standalone URL, or represent a headless service. Cross-module scientific
conversions remain lab-controller responsibilities rather than being added
pairwise to the individual repositories.

## A unified artifact workflow

PAH keeps specialized tools independent, but it is designed around artifacts that can be reused across those tools.

```text
Source code
   │
   ▼
Code Analyzer
   │
   ├── graph JSON / GraphML / DOT
   └── graph SVG
          │
          ▼
Document Workbench
   ├── Markdown / LaTeX
   ├── Notebook
   └── Presentation

Reference Manager
   └── citations / bibliography
          │
          ├──► documents
          └──► notebook Markdown

Notebook
   ├── code + results
   ├── figures
   ├── narrative
   └── live presentation
```

The long-term integration model is reuse rather than duplication: a graph, figure, citation, result, diagram, or other project artifact should remain traceable to its source while being usable in more than one output.

PAH owns those cross-tool relationships. The individual modules do not need to import one another directly.

## Detachable tools

Analysis, Documents, References, Git, and Terminal can be opened outside the main PAH window when more screen space is useful. A detached tool continues using the same PAH project or service state rather than creating an unrelated second session.

The Terminal keeps one shell session when moving between docked, collapsed, and detached presentation states.

## Git

Git is optional and is treated as a secondary workspace service.

A normal directory does not become a Git repository just because it is opened in PAH. Local Git can be enabled explicitly, or PAH can use an existing repository.

Local Git features include:

- repository status;
- working-tree and staged diffs;
- stage and unstage;
- local commits;
- local history;
- branch inspection and switching;
- recursive submodule status.

### Local Only by default

Every workspace begins in **Local Only** mode. PAH does not fetch, pull, push, clone, or update remote submodules until the user explicitly enables **Manual Remote** for the current workspace.

Remote operations remain manual even after they are enabled. There is no background synchronization loop.

PAH does not store Git passwords, personal access tokens, or SSH private keys. Authentication remains the responsibility of Git, SSH agents, and system credential helpers.

## Overleaf

PAH supports two Overleaf workflows.

### Source ZIP import

A downloaded Overleaf project ZIP can be imported without enabling Git or contacting Overleaf. PAH safely extracts the archive, preserves its directory structure, and identifies likely LaTeX entry points, bibliography files, figures, and support files.

The resulting directory is an ordinary local PAH workspace and can remain completely offline.

### Git-backed projects

When Manual Remote Git is enabled, PAH can clone a Git-backed Overleaf project and can expose explicit Overleaf-oriented Fetch, fast-forward-only Pull, and Push controls.

PAH checks local state before synchronization and avoids silent merge or rebase behavior. Cached remote information is distinguished from state refreshed by an explicit Fetch.

Detected `.bib` files can be opened in the Workspace editor or explicitly imported into the selected Reference Manager library.

## Local-first and privacy model

PAH is designed to remain useful without a network connection.

Core functionality operates on local files and local services:

```text
Project files
    ↓
PAH Workspace
    ├── Editor
    ├── Terminal
    ├── Python environments
    ├── Local Git
    ├── Analysis
    ├── Documents / Notebooks / Presentations
    └── References
```

Remote Git and Overleaf synchronization require explicit user action. PAH does not automatically upload projects, initialize repositories, or contact configured remotes.

PAH state is normally stored outside the opened project under:

```text
~/.local/share/pah/
```

Browser-only presentation preferences such as pane sizes and collapsed state are stored in browser local storage.

## Modules

PAH keeps its specialized applications as separate Git submodules:

```text
modules/
├── code_analyzer/       → Code Repository Cataloguer
├── pypique/             → pyPIQUE
├── hsqa_dbn/            → HSQA_DBN / EBM-DBN Analysis Lab
├── tech_documents/      → Research Document Workbench
└── reference_manager/   → Research Paper Repository Manager
    └── modules/
        └── paper_searcher/  → Research Search
```

The three primary modules remain independently runnable and maintain their own repositories, tests, and interfaces. PAH coordinates them rather than copying their implementations into the host.

## Goal-oriented labs

PAH can present independently runnable modules as higher-level research workflows without moving scientific code into the host. The first collection is **Code Analysis Lab**, available from the **Labs** menu. Labs now occupy the top-navigation position previously used by the standalone Analysis launcher; the underlying Code Analyzer full surface remains available through its registered runtime adapter.

Its controller currently models this workflow:

```text
Repository analysis        → Code Analyzer (optional)
Quality evidence/model     → pyPIQUE
Representation learning    → HSQA_DBN
Latent-information analysis→ HSQA_DBN
```

The lab surface reports three kinds of state separately:

- whether the expected module is registered with PAH;
- whether the provider advertises the required capability;
- whether the generic input/output artifacts required for the next handoff are registered.

PAH does not mark a workflow step complete merely because its button was visited. Completion is artifact-driven. Missing modules or handoffs remain visible as blocked states rather than being replaced with hidden module-specific subprocess logic.

Sprint 5B intentionally does not yet implement the pyPIQUE → HSQA_DBN conversion itself. That adapter belongs to the Code Analysis Lab integration layer in a later sprint.

## Installation

### Requirements

- Python 3.10 or newer
- Git
- A POSIX-style local environment for the PTY terminal, such as Linux
- `ipykernel`, `jupyter_client`, `nbformat`, and `nbconvert` for notebook workflows
- Any additional system tools required by optional module features, such as Quarto or a LaTeX toolchain for selected document/presentation exports

Clone the repository with its submodules:

```bash
git clone --recurse-submodules <PAH_REPO_URL>
cd Project_Assistant_Host
```

The Code Analysis Lab providers are normal PAH Git submodules. Add them from their canonical GitHub repositories once in the PAH repository:

```bash
git submodule add git@github.com:bportil1/pyPIQUE.git modules/pypique
git submodule add git@github.com:bportil1/HSQA_DBN.git modules/hsqa_dbn
```

Commit the resulting `.gitmodules` entries and gitlinks in PAH. Thereafter, ordinary clones use `--recurse-submodules`, and `./scripts/setup.sh` installs Code Analyzer, `pyPIQUE[full]`, and `hsqa-dbn[visual]` editable into PAH's `.venv`, allowing their `pah.modules` and `pah.runtimes` entry points to be discovered automatically.

Run the setup script:

```bash
./scripts/setup.sh
```

For source checkouts that do not already contain the pinned browser assets, populate the local browser dependencies once. PAH uses Ace and xterm.js; the Document Workbench uses Ace and Reveal.js for notebook editing/presentation.

Typical source-checkout provisioning commands are:

```bash
python3 scripts/vendor_ace.py
python3 scripts/vendor_xterm.py
python3 modules/tech_documents/scripts/vendor_ace.py
python3 modules/tech_documents/scripts/vendor_reveal.py
```

These are local provisioning steps rather than runtime CDN dependencies. Once the assets are present in the repositories' static directories, normal PAH use loads them locally.

Activate the environment:

```bash
source .venv/bin/activate
```

Start PAH:

```bash
python run.py
```

Or open a project immediately:

```bash
python run.py /path/to/project
```

By default PAH listens only on the local loopback interface:

```text
http://127.0.0.1:8765
```

Use `--no-browser` if you do not want PAH to open a browser automatically.

## Updating

PAH and its specialized tools are separate Git repositories connected through submodules. The parent repository records known-compatible module revisions.

To restore submodules to the revisions recorded by PAH:

```bash
git submodule update --init --recursive
```

Following the newest remote commit of every module is a different operation and can expose local integration changes or incompatible revisions. It should be done deliberately rather than as part of normal application startup.

The project is moving toward a more unified component lifecycle so normal updates can verify module revisions, Python dependencies, browser assets, and hosting compatibility together. Until that lifecycle is fully consolidated, source checkouts should treat module updates and browser-asset provisioning as explicit maintenance operations.

## Tests

Run the PAH test suite with:

```bash
pytest
```

The specialized modules also maintain their own test suites. Module-level tests are important because the Analyzer, Document Workbench, Reference Manager, and Research Search remain independently runnable applications.

## Project scope

PAH is intended to provide a coherent local working environment around software, analysis, documents, notebooks, presentations, research references, and related project artifacts. It is not intended to reproduce every feature of a full IDE, Git client, JupyterLab, publishing platform, or literature-management application.

The project favors:

- local ownership of files;
- explicit actions over hidden automation;
- modular tools over a monolithic application;
- usable screen space over permanent secondary panels;
- ordinary project files over proprietary project formats;
- reusable artifacts over duplicated output;
- traceable deterministic integrations over opaque generated state.

The result is a workspace in which code, graphs, documents, notebooks, diagrams, references, terminal work, presentations, and version history can remain distinct artifacts while still participating in one project workflow.


## Component versions and dependency status

PAH exposes **Tools → Component Versions** for managed submodules. Local refreshes are read-only and never contact remotes. The panel distinguishes the revision recorded by the parent repository, the currently checked-out revision, and the latest cached/fetched remote revision. Remote fetch/update actions are explicit. Updates use fast-forward-only Git operations, reinstall affected editable Python packages, and can run compatibility tests before the new gitlinks are recorded. **Record Component Versions** creates local parent Git commits only; it never pushes.


## 0.9.12 — New Research Workspace initialization

PAH now has a dedicated New Research Workspace flow instead of relying on a
name-only quick-create action. The initializer exposes generic presets (Blank,
Document Creation, Literature Review, Software Analysis, ML / Data Research,
and Full Research Workspace), capability/category selection, per-module
customization, and initial mappings for repository, documents, papers,
bibliography, datasets, assets, notes, outputs, and archive resources.

Preset choices remain editable before creation. Unavailable registered roots are
shown but cannot be selected during initialization, and the host validates both
module availability and resource availability again at the API boundary.
Workspace creation applies the selected module profile and resource map
atomically so an invalid mapping does not leave a partially created workspace.

## 0.9.11 — Workspace module profiles

Research workspaces now persist an explicit enabled-module profile. PAH keeps
**Installed**, **Enabled**, and **Running** as separate states, migrates legacy
workspaces to enable the modules installed at migration time, and preserves
enabled-but-unavailable module identifiers so portable workspace intent is not
lost on machines with different module installations.

The workspace Resources dialog now includes grouped module controls using
general research capabilities such as Document Creation, Literature &
References, Software Analysis, Machine Learning, and Data / Research Utilities.
Disabled modules are removed from workspace navigation and lab provider views,
blocked at runtime launch boundaries, and left otherwise untouched so their
files and registered artifacts remain available if the module is re-enabled.

## 0.9.10 — Workspace save shortcut

`Ctrl+S` (or `Cmd+S` on macOS) now saves the active PAH workspace file even
when focus has moved away from the Ace editor to another control in the main
workspace. Embedded/detached tools keep responsibility for their own shortcuts,
and held-key repeats do not issue duplicate save requests.

## 0.9.9 — Research workspace resource management

PAH now exposes research workspaces and shared/registered roots directly in the
host UI. A workspace can map independent repository, document, paper, dataset,
asset, bibliography, note, output, and archive resources without forcing them
under one physical project directory. Registered-root filesystem paths remain
machine-local while workspace mappings use logical root identifiers.

The hosted Research Document Workbench now receives the workspace `documents`
resource as its Document Root, falling back to the Repository Root only when no
Document Root is mapped. PAH's repository editor remains repository-bound, so a
separate Document Root is edited through the full Documents workspace rather than
being incorrectly treated as a repository-relative file.

## 0.9.8 — Research workspace foundation

PAH's workspace state now models logical research workspaces, registered roots,
resource-role mappings, resource availability, synchronization boundaries, and
resource-aware module context while preserving the legacy Open Directory flow.

## 0.9.7 — ML Lab integration

PAH now recognizes ML Lab as a first-class managed Python/Git component. ML Lab
remains independently runnable; PAH discovers its module/runtime adapters through
Python entry points, launches ML Lab's own UI, docks it in the Labs workspace, and
imports recognized ML Lab result artifacts into PAH's neutral artifact registry.

Add the ML Lab repository once at `modules/ml_lab` (for example with the helper
`./scripts/add_ml_lab_submodule.sh <ml-lab-git-url>`), then run `./scripts/setup.sh`
to install `modules/ml_lab[ui]` into PAH's environment.
