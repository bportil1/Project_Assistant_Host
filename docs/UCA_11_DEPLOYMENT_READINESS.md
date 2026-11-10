# UCA-11 — Consolidated deployment-readiness assessment

## Purpose

This is an **evidence inventory**, not automatic deployment certification. It consumes
reports already produced locally by the UCA-11 static, cross-repository, hosted-layout,
and source-navigation runners. No network requests, source modifications, or model
computations occur. Report content is not copied into the summary; only allowlisted
states and counts are recorded.

## Usage

Run each existing acceptance runner separately, saving their output JSON. Then run:

```sh
python scripts/uca11_readiness_report.py \
  --baseline path/to/baseline.json \
  --cross-repository path/to/cross-repo.json \
  --hosted-layout path/to/layout.json \
  --source-navigation path/to/navigation.json \
  --output path/to/new-readiness.json
```

All inputs are optional, but omitted inputs are reported as not provided, **not passed**.
Outputs are create-only. File inputs must be normal non-symlink files no larger than
500 KiB. A blocking failure returns exit code 1; missing hosted evidence remains an
unverified gate even if the runner returns exit code 0.

## Hard gates requiring actual installed-environment evidence

- Deployed patch/version consistency across the PAH, pyPIQUE and Code Analyzer checkouts
- PAH Flask endpoints and all seven pane layouts with a single preserved editable buffer
- Verified bidirectional source navigation, matching revisions, and actual Ace cursor movement
- Real project switching, stale requests and source-revision rejection
- Python and ATLAS provider execution on representative files (no assumed IEEE 716 semantics)
- Producer-owned job/artifact handoffs, source fingerprints and isolation
- Scientific numerical parity where original and migrated paths overlap
- Original standalone launches and workflows, including CPS Analysis Lab
- Source edit authorization, move/Undo, crash recovery and security boundaries

A verified hosted smoke check is still only a **partial observation**, not a pass
for every gate. Explicit user review of evidence is required before deployment
sign-off. Existing legacy paths remain in place. **No legacy retirement is
approved by this report.** P5-20 remains on hold.

## Preservation

Keep original data and scientific methods authoritative, use module-owned SQLite
stores, do not install dependencies or run any external search, and do not delete
or modify code from this acceptance tool. Missing evidence remains visible.
