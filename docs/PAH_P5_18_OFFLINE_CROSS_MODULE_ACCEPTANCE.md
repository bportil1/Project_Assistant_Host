# P5-18 — Offline cross-module source-evidence acceptance

This incremental test suite checks the actual pyPIQUE producer projection against
PAH's descriptor-safe read-only source resolver. Both modules remain independent;
no runtime imports are added to PAH's production paths. No source-editing API is
called, and the test fixtures are temporary local files.

Run from the PAH repository with a compatible local pyPIQUE checkout on the
Python path:

```sh
PYTHONPATH=.:../pyPIQUE/src python -m pytest -q tests/test_p5_18_cross_module_acceptance.py
```

The suite uses `pytest.importorskip` for pyPIQUE; an absent producer is a **skip**,
not evidence that integration passed. Run with `-rs` to see skipped dependencies.
It checks source identity, immutable finding projection, read-only excerpts,
project switching, stale source rejection, symlink replacement, unsafe paths,
and historical findings without source hashes.

## Unverified gates

- Real provider scan with opt-in source provenance across provider execution
- PAH Flask auth and workspace resource resolution with installed modules
- Browser interaction and project changes under real sessions
- Code Analyzer inspection integration and evidence handoff
- Source mutation races beyond the descriptor-safe tests

The scientific results and existing source editors are outside this test's scope.
Do not close P5-18 or remove legacy paths based on this suite alone.
