# PAH runtime adapter source contract repair

A module runtime may be published as a ready instance, a no-arg factory or an
adapter class. `RuntimeRegistry.register()` now resolves these forms once and
rejects factory-returned classes. Entry-point discovery no longer checks for
an attribute called `status` on classes (which is only an unbound descriptor).
This fixes HTTP 500 caused by `CodeAnalyzerRuntimeAdapter.status()` missing
`self` in `/api/orchestration/modules` and `/api/orchestration/code-analysis`.

Status calls are isolated at the host's runtime observation boundary. When an
adapter's status raises, PAH logs the full exception and reports the failing
module as unavailable in the workflow; other modules and already completed
scientific jobs remain inspectable. This does not mark a broken module healthy,
restart it, or discard any results. Launch errors still surface as errors.

The Code Analyzer companion source patch exports a factory from its installed
entry point, so both modern and older hosts receive a bound adapter. Neither
patch alters the analyzer engine, AST parser, analysis artifacts or SQLite data.
The PAH fix remains necessary for other third-party adapters exporting classes.

## Acceptance

Run `python -m pytest -q tests/test_runtime_registry.py tests/test_mi05_hosted_boundaries.py tests/test_code_analysis_lab.py` from the PAH root.
After installing the Code Analyzer package in the SAME PAH venv and restarting
that host, GET both `/api/orchestration/modules` and
`/api/orchestration/code-analysis`. Both should return HTTP 200; any unavailable
provider must be represented in the workflow instead of terminating the entire
snapshot. Check `pah.log` for full provider exceptions.

An installed metadata entry point is not updated merely by modifying its
`pyproject.toml`: run a trusted local editable install of the patched Code
Analyzer repo in the PAH venv. No network or external services are required.
