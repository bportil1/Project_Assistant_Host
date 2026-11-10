#!/usr/bin/env python3
"""UCA-11 initial acceptance inventory; offline and read-only by default.

Interface presence is not browser, scientific, security, or integration parity.
An explicit --run-local-tests executes only this repository's selected tests.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

# Files with names that define UCA integration seams. No imported application code.
PAH_CONTRACTS = {
    "selection": "pah/contracts/uca_scope.py",  # scope authority
    "source_revision": "pah/contracts/uca_source_revision.py",
    "layout": "pah/web/static/uca-layout.mjs",
    "single_editor": "pah/web/static/uca-editor-dock.mjs",
    "pypique_findings": "pah/web/static/uca-pypique-findings.mjs",
    "code_analyzer": "pah/web/static/uca-analyzer.mjs",
    "navigation": "pah/web/static/uca-navigation.mjs",
    "provider_navigation": "pah/web/static/uca-provider-navigation.mjs",
    "jobs": "pah/web/static/uca-observations.mjs",
    "artifact_handoff": "pah/web/static/uca-handoff.mjs",
}
# Record acceptance requirements explicitly; a static file never passes them.
MANUAL_GATES = (
    "hosted_flask_routes", "one_two_three_pane_layout", "editor_buffer_preservation",
    "workspace_project_switching", "verified_sat_to_editor", "editor_to_sat",
    "code_analyzer_to_editor", "python_atlas_provider", "job_artifact_provenance",
    "legacy_standalone", "scientific_parity", "security_and_recovery",
)
LOCAL_TESTS = (
    "tests/test_uca_source_selection.py", "tests/test_uca_scope.py",
    "tests/test_uca_source_revision.py", "tests/test_uca_coordination.py",
    "tests/test_uca_handoff_integration.py", "tests/test_uca_provider_navigation_contract.py",
)
JS_TESTS = (
    "tests/uca_layout.test.mjs", "tests/uca_editor_dock.test.mjs",
    "tests/uca_pypique_findings.test.mjs", "tests/uca_analyzer.test.mjs",
    "tests/uca_navigation.test.mjs", "tests/uca_provider_navigation.test.mjs",
    "tests/uca_observations.test.mjs",
)

def safe_file(root: Path, rel: str) -> bool:
    """Reject symlink components; inspect only relative, known contract paths."""
    here = root
    for part in Path(rel).parts:
        here = here / part
        if here.is_symlink():
            return False
    return here.is_file()

def inventory(root: Path) -> dict:
    found = {name: safe_file(root, rel) for name, rel in PAH_CONTRACTS.items()}
    return {"schema": "pah.uca.acceptance@1", "kind": "static_interface_inventory",
            "interfaces": found, "missing": [name for name, yes in found.items() if not yes],
            "gates": {gate: "unverified" for gate in MANUAL_GATES},
            "local_tests": {"status":"not_run"},
            "scope": "static_contract_presence_does_not_prove_runtime_behavior"}

def _test_command(root: Path, command: list[str], timeout: int = 90) -> dict:
    try:
        completed = subprocess.run(command, cwd=root, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, timeout=timeout,
                                   env=None, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "unverified", "reason": type(exc).__name__}
    # Never include subprocess stdout, stderr, source text, or environment in reports.
    return {"status": "passed" if completed.returncode == 0 else "failed",
            "returncode": completed.returncode}

def run_local_tests(root: Path) -> dict:
    if not all(safe_file(root, rel) for rel in LOCAL_TESTS + JS_TESTS):
        return {"status": "unverified", "reason": "missing_selected_tests"}
    python = _test_command(root, [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_uca*.py'])
    node = _test_command(root, ['node', '--test', *JS_TESTS])
    return {"status": "passed" if python['status'] == node['status'] == 'passed' else 'incomplete',
            "python": python, "javascript": node}

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pah', required=True, type=Path, help='Local PAH checkout')
    parser.add_argument('--run-local-tests', action='store_true')
    parser.add_argument('--output', type=Path, help='New JSON report file; never overwritten')
    args = parser.parse_args(argv)
    root = args.pah.resolve(strict=True)
    result = inventory(root)
    if args.run_local_tests:
        result['local_tests'] = run_local_tests(root)
    output = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.output:
        with args.output.open('x', encoding='utf-8') as file:
            file.write(output)
    else:
        sys.stdout.write(output)
    return 0 if not result['missing'] and (not args.run_local_tests or result['local_tests']['status'] == 'passed') else 1
if __name__ == '__main__':
    raise SystemExit(main())
