# UCA-11 — Initial integrated acceptance gate

This first increment provides a **local, non-destructive** inventory and an
optional selected regression runner. It never creates data, starts an analysis,
changes a repository, calls an HTTP endpoint, or downloads dependencies.

From the PAH repository root:

```bash
python scripts/uca11_acceptance.py --pah .
python scripts/uca11_acceptance.py --pah . --run-local-tests
```

The first command verifies known UCA seam files without importing application
code. The second additionally executes selected `test_uca*.py` unittest files
and Node ESM tests. Any missing dependency or executable is reported as
failed/unverified, never silently skipped or installed. Outputs contain statuses
and return codes only, not source text or subprocess output. Use `--output`
with a previously nonexistent local filename to save a JSON report.

## Hosted acceptance still required

The following need explicit testing in installed PAH with its real module
adapters and representative source repositories:

- One/two/three-pane layouts, resizing, and buffer preservation
- Workspace and project switching; stale request invalidation
- Verified pyPIQUE finding → editor and reverse lookup
- Code Analyzer structural candidate vs verified-revision semantics
- Python and ATLAS provider results; unsupported language behavior
- Job observation and separately validated producer artifact handoff
- Source-edit authorization and rollback; no navigation-triggered writes
- Standalone launch and existing module workflows
- Scientific numerical parity and immutable provenance
- Recovery, isolation, and security gates

**Never mark hosted or scientific equivalence accepted based only on interface
presence, component tests, or HTTP availability.** Preserve legacy paths.

## Scope boundaries

PAH owns navigation and workspace identity, pyPIQUE owns SAT and MI, Code
Analyzer owns provider and structure data, and the existing editor owns buffers.
No database ownership or scientific computation moves in UCA-11.
