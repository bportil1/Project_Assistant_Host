# PAH — Project Assistant Host

PAH is a local-first workspace for software projects, technical documentation, and research references. It combines a native project workspace with independently maintained analysis, document, and reference tools while keeping the underlying files and repositories ordinary and accessible outside PAH.

PAH is designed for people who want one place to move between code, documentation, literature, terminal work, and project history without turning the application into a monolithic IDE or requiring a cloud service.

**Current version:** 0.9.1

## Highlights

* Local project browser and file operations
* Ace-based code editor with real cursor, selection, undo, syntax highlighting, folding, search, and normal clipboard behavior
* xterm.js terminal connected to a real local PTY, with shell history, tab completion, control keys, interactive programs, and resize support
* Collapsible and resizable workspace panes
* Detachable Analysis, Documents, References, Git, and Terminal surfaces
* Python virtual-environment creation and selection
* Direct execution of the active Python file
* Repository analysis through the Code Repository Cataloguer
* Markdown, LaTeX, BibTeX, diagram, and document-build workflows through the Research Document Workbench
* PDF, BibTeX, citation, and literature-library workflows through the Research Paper Repository Manager
* Research Search as an optional companion service
* Optional local Git tools, with remote Git disabled until explicitly enabled
* Overleaf ZIP import and optional Git-backed Overleaf synchronization
* Cross-module workflows for code references, diagrams, citations, and traceable documentation

## Interface

PAH has four primary work modes:

```text
[ Workspace ] [ Analysis ] [ Documents ] [ References ]
```

Secondary services are opened on demand from menus instead of occupying permanent screen space.

### Workspace

Workspace is the native PAH environment for everyday project work. It includes:

* local filesystem browsing;
* file and directory creation, rename, move, and delete;
* tabbed editing through Ace;
* save, undo/redo, search, indentation, folding, and normal copy/paste;
* an xterm.js terminal backed by a real shell PTY;
* Python environment selection and creation;
* active-file Python execution;
* contextual project tools;
* optional Git controls.

The Project Tree, Project Tools, and Terminal panes are collapsible and resizable. The editor expands into reclaimed space when a pane is collapsed. Layout preferences are stored locally in the browser rather than written into the opened project.

### Analysis

Analysis hosts the Code Repository Cataloguer against the current workspace. Depending on the repository and module configuration, it can provide:

* Python entity and structure inspection;
* incoming and outgoing dependencies;
* repository maps;
* pairwise source and semantic comparisons;
* global similarity matrices;
* clustering;
* duplication analysis;
* dependency views.

Analysis is explicit. Editing source code marks previously generated analysis as stale rather than continuously re-running expensive analysis in the background.

### Documents

Documents hosts the Research Document Workbench against the current PAH workspace. It supports workflows around:

* Markdown;
* LaTeX;
* BibTeX;
* `.diagram` files;
* diagrams and Mermaid output;
* LaTeX builds;
* generated previews and PDFs;
* technical-document authoring.

PAH can also import downloaded Overleaf source ZIPs as ordinary local projects. Git-backed Overleaf projects can be cloned and synchronized when remote Git access has been explicitly enabled.

### References

References hosts the Research Paper Repository Manager and can work with a paper library that is separate from the current source-code workspace. Its responsibilities include:

* PDF libraries;
* paper metadata;
* BibTeX records;
* topics, statuses, and notes;
* duplicate-management workflows;
* citation and document integration;
* local paper organization.

Research Search is available as an optional companion window through the References menu when its nested module is installed.

## Detachable tools

Analysis, Documents, References, Git, and Terminal can be opened outside the main PAH window when more screen space is useful. A detached tool continues using the same PAH project or service state rather than creating an unrelated second session.

The Terminal keeps one shell session when moving between docked, collapsed, and detached presentation states.

## Git

Git is optional and is treated as a secondary workspace service.

A normal directory does not become a Git repository just because it is opened in PAH. Local Git can be enabled explicitly, or PAH can use an existing repository.

Local Git features include:

* repository status;
* working-tree and staged diffs;
* stage and unstage;
* local commits;
* local history;
* branch inspection and switching;
* recursive submodule status.

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
    ├── Documents
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
├── tech_documents/      → Research Document Workbench
└── reference_manager/   → Research Paper Repository Manager
    └── modules/
        └── paper_searcher/  → Research Search
```

The three primary modules remain independently runnable and maintain their own repositories, tests, and interfaces. PAH coordinates them rather than copying their implementations into the host.

## Installation

### Requirements

* Python 3.10 or newer
* Git
* A POSIX-style local environment for the PTY terminal, such as Linux
* Any additional system tools required by optional module features, such as a LaTeX toolchain for document compilation

Clone the repository with its submodules:

```bash
git clone --recurse-submodules <PAH_REPO_URL>
cd Project_Assistant_Host
```

Run the setup script:

```bash
./scripts/setup.sh
```

For a source checkout that does not already contain the vendored browser assets, install the pinned local editor and terminal assets once:

```bash
python3 scripts/vendor_ace.py
python3 scripts/vendor_xterm.py
```

These scripts are installation/development steps. After the assets are present under `pah/web/static/vendor/`, normal PAH use loads them locally and does not require a CDN.

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

To pull the PAH repository and restore the submodules to the revisions recorded by the host repository:

```bash
./scripts/update.sh
```

If submodules were not initialized during clone:

```bash
git submodule update --init --recursive
```

Because the specialized modules are independent repositories, PAH pins known-compatible module revisions rather than silently following the newest commit on every module branch.

## Tests

Run the PAH test suite with:

```bash
pytest
```

The specialized modules also maintain their own test suites.

## Project scope

PAH is intended to provide a coherent local working environment around software, documents, research references, and related project artifacts. It is not intended to reproduce every feature of a full IDE, Git client, publishing platform, or literature-management application.

The project favors:

* local ownership of files;
* explicit actions over hidden automation;
* modular tools over a monolithic application;
* usable screen space over permanent secondary panels;
* ordinary project files over proprietary project formats;
* traceable deterministic integrations over opaque generated state.

The result is a workspace in which code, documents, diagrams, references, terminal work, and version history can remain separate artifacts while still participating in one project workflow.

