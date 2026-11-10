# UCA-00 — Unified Code Analysis baseline and integration boundaries

Status: **inventory harness, not integrated functionality**. P5-20 remains on hold.
This document records only interfaces inspected in the supplied archive snapshots;
installed Git revisions and previously applied P5 patches may differ.

## Repositories and authority

| Checkout | Existing boundary | Authority after integration |
| --- | --- | --- |
| PAH | `pah/core/workspace.py`, `pah/labs/code_analysis.py`, `pah/web/templates/index.html` | Active project/repository, pane lifecycle and navigation events |
| pyPIQUE | `src/pique_py/visualizer.py` and SAT/MI pipeline | Findings, provenance, SAT, model/MI scientific semantics |
| Code Analyzer | `code_analyzer/api.py`, `catalog/scanner.py`, `catalog/refactor/function_mover.py` | Language-specific parsing, symbols, structural graphs, controlled edits |
| CPS Analysis Lab | `src/cps_lab/atlas/{lexer,parser,analysis}.py`, `integration/contracts.py` | ATLAS parser/heuristic semantics, until provider integration is validated |

## Scope boundaries

- A pane is a view, not a new repository session. PAH coordinates source selection;
  source editors and scientific modules retain their existing authority.
- Source identity should include project, repository-relative path, revision/hash,
  source span, producer artifact and optional semantic node reference.
- Historical SAT source positions without verified fingerprints remain unverified.
- CPS's `cps.atlas.analysis@1` reports structural/heuristic results. Preserve
  `semantic_status=unverified`; do not infer verified IEEE 716 coverage or
  hardware behavior. Maintain source-span coordinate definitions.
- Python AST and ATLAS syntax are not interchangeable AST semantics. A future
  provider API must advertise capabilities and explicit unsupported operations.
- Existing source-edit/undo, SAT execution, graph interactions, standalone
  launches and project-local SQLite ownership remain unchanged during UCA.

## Run the metadata-only check

From PAH checkout, with explicit **local** checkout paths:

```sh
python3 scripts/uca_baseline.py \
  --pah . --pypique ../pyPIQUE \
  --code-analyzer ../Code_Repository_Cataloguer \
  --cps ../CPS-Analysis-Lab \
  --output /tmp/uca_baseline.json
```

Paths are examples, not discovered locations. Missing required interface files
return nonzero; optional prior-P5 markers are reported without failing. No
arbitrary repository scripts run. The report omits original file content and
absolute local paths; it reports existence only, not semantic parity or safety.

## UCA-00 acceptance / remaining gates

- [x] Explicit no-network, non-mutating interface inventory command
- [x] Missing interfaces fail, optional features are not falsely marked passed
- [x] Regression tests for missing roots, symlinks and report content
- [ ] Installed checkout and post-P5 revision verification
- [ ] Record actual Flask/browser and SAT job test outcomes
- [ ] Verify Code Analyzer and CPS standalone tests under installed dependencies
- [ ] Approve UCA-01 source-selection version, event loop suppression and revision rules

**Legacy policy:** do not remove or redirect any existing route, parser or edit
path until the unified workspace is operational and accepted in installed PAH.
