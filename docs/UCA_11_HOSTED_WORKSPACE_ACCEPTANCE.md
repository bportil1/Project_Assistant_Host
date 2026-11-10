# UCA-11 — Local hosted workspace acceptance

This optional smoke runner uses a **locally installed** Playwright Python package and Chromium browser to inspect an **already running** local PAH host. It does not install dependencies, start PAH, execute SAT, run Code Analyzer, save source files, or modify legacy implementations.

## Usage

Default mode validates the URL without connecting:

```sh
python scripts/uca11_hosted_workspace.py --url http://127.0.0.1:5000/
```

Explicitly run a local browser smoke test:

```sh
python scripts/uca11_hosted_workspace.py --url http://127.0.0.1:5000/ --run-browser
```

Use the port of the existing locally running PAH instance. A numeric loopback HTTP host and explicit port are required; external connections and redirects to other origins are blocked. Browser storage is temporary. Reports omit source data and HTTP response bodies. `--output` creates a new report file and will not overwrite an existing report.

## Automated browser checks

- Unified Analysis mode loads and renders.
- Each of the seven nonempty pane combinations can be selected.
- The existing editor remains a single DOM instance and docks in the editor pane.
- Editor docking reverses on return to Workspace.
- Width controls affect the editor pane's layout.

These checks deliberately **do not click** source-editing, SAT execution, provider execution, or artifact publication controls.

## Acceptance still requiring installed-environment/manual verification

- Open a real repository and exercise project/workspace switching with two distinct project identities.
- Open a file with unsaved edits; switch modes and verify both the buffer and dirty state are preserved.
- Verify pyPIQUE finding navigation only for matching scan-time source hashes, including stale findings.
- Verify editor → findings and Code Analyzer → editor navigation with verified source revisions.
- Exercise Python and ATLAS providers on representative sources, checking diagnostics and provenance.
- Compare producer-issued job/artifact references with actual module-owned results.
- Run standalone legacy interfaces and relevant scientific/rollback tests.

A passing browser smoke test **does not** close any of these gates. No legacy retirement is authorized by this runner.
