# UCA-01 — Repository-scoped source selection contract

**Status:** versioned Python contract + in-memory coordinator only. No HTTP route,
UI listeners, browser messaging, or live source inspection added in this increment.

## Contract

`pah.source-selection@1` carries `workspace_id`, `project_id`, `repository_id`,
`relative_path` (strict project-relative POSIX path), `source_sha256` (lowercase
hex digest of **verified source bytes**), `producer` (`editor`, `pypique`, or
`code_analyzer`), `start_line` and `end_line` (inclusive, 1-based), optional
inclusive 1-based `start_column` / `end_column`, `artifact_id`, and
`semantic_node_id`. Column coordinates are *logical* character coordinates;
modules must explicitly translate any byte/decoded/UTF-16 coordinate system.

A navigation event supplies an opaque `event_id`, local `epoch`, monotonic
`sequence`, and the validated selection. The producer never receives its own
event as a consumer; consumers suppress redispatch by remembered `event_id`.
Selection is in-memory only and **not** an authorization or a source inspection
result. The actual source view must still authorize the user and validate the
path, open the source safely, and rehash exact bytes (P5-18 resolver).

Switching workspace, project, or repository increments the epoch and clears the
current selection. Events created in prior epochs cannot be published or
consumed in the new scope. Selecting a new source revision does not silently
rewrite a prior scientific artifact. Consumers must display revision mismatch
as stale/unverified, not relocate findings automatically.

Historical findings lacking trusted source hashes cannot emit this contract.
The selection coordinator intentionally does not read source or update caches,
execute SAT or parsing jobs, modify files, store user state, or create network
connections. Future UCA-02–06 adapters must enforce authorization and preserve
module standalone operation.

## Acceptance status

- [x] Schema validation, strict paths, source hash requirement, bounded spans
- [x] Scoped event source, monotonic ordering, event-loop suppression, epoch invalidation
- [x] Pure-Python contract tests, no external dependencies or scientific changes
- [ ] Integrated PAH workspace lifecycle and installed project identity (UCA-02)
- [ ] Browser/editor selection adapters and full navigation authorization (UCA-03–06)
- [ ] Real cross-module/hosted behavior and revision parity (UCA-11)

No legacy code may be retired based on these checks.
