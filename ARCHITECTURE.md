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
