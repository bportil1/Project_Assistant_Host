#!/usr/bin/env python3
"""Read-only UCA-11 four-repository interface/regression acceptance.

Never treat static presence or selected tests as hosted integration parity.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess
import sys

SCHEMA = "pah.uca.cross-repository-acceptance@1"
CHECKS = {
    "pah": {
        "scope": "pah/contracts/uca_scope.py",
        "navigation": "pah/web/static/uca-navigation.mjs",
        "editor": "pah/web/static/uca-editor-dock.mjs",
        "sat_pane": "pah/web/static/uca-pypique-findings.mjs",
        "provider_pane": "pah/web/static/uca-provider-navigation.mjs",
        "handoff": "pah/web/static/uca-handoff.mjs",
        "acceptance": "scripts/uca11_acceptance.py",
    },
    "pypique": {
        "finding_projection": "src/pique_py/source_evidence_locator.py",
        "finding_tests": "tests/test_p518_source_evidence_locator.py",
    },
    "code_analyzer": {
        "provider_contract": "code_analyzer/language_providers/contracts.py",
        "python_provider": "code_analyzer/language_providers/python_provider.py",
        "atlas_provider": "code_analyzer/language_providers/atlas_provider.py",
        "atlas_engine": "code_analyzer/language_providers/_atlas_engine/parser.py",
        "source_navigation": "code_analyzer/language_providers/navigation.py",
        "navigation_tests": "tests/test_uca09_provider_navigation.py",
    },
    "cps": {
        "legacy_parser": "src/cps_lab/atlas/parser.py",
        "legacy_lexer": "src/cps_lab/atlas/lexer.py",
        "legacy_tests": "tests/test_parser.py",
    },
}
# Selected test files only, never invoke an arbitrary command read from repository content.
TESTS = {
    "pah": ["tests/test_uca11_acceptance.py", "tests/test_uca_source_selection.py"],
    "pypique": ["tests/test_p518_source_evidence_locator.py"],
    "code_analyzer": ["tests/test_uca07_language_providers.py", "tests/test_uca08_atlas_provider.py", "tests/test_uca09_provider_navigation.py"],
    "cps": ["tests/test_parser.py", "tests/test_lexer.py"],
}
UNVERIFIED = (
    "hosted_browser_panes", "cross_pane_navigation", "installed_provider_execution",
    "real_sat_finding_provenance", "scientific_numerical_parity",
    "live_project_isolation", "standalone_legacy_parity", "legacy_retirement",
)

def safe_file(root: Path, relative: str) -> bool:
    current = root
    for component in Path(relative).parts:
        if component in (".", "..") or not component:
            return False
        current = current / component
        if current.is_symlink():
            return False
    return current.is_file()

def check_root(root: Path, checks: dict[str, str]) -> dict:
    if not root.is_dir() or root.is_symlink():
        return {"status": "unverified", "reason": "missing_or_symlinked_repository", "interfaces": {}}
    found = {key: safe_file(root, rel) for key, rel in checks.items()}
    return {"status": "present" if all(found.values()) else "incomplete", "interfaces": found}

def run_selected(root: Path, paths: list[str]) -> dict:
    if not all(safe_file(root, rel) for rel in paths):
        return {"status": "unverified", "reason": "missing_selected_tests"}
    try:
        completed = subprocess.run([sys.executable, "-m", "pytest", "-q", *paths], cwd=root,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "unverified", "reason": type(exc).__name__}
    return {"status": "passed" if completed.returncode == 0 else "failed",
            "exit_code": completed.returncode}

def assess(roots: dict[str, Path], *, run_tests: bool = False) -> dict:
    records = {}
    for name, contracts in CHECKS.items():
        root = roots[name]
        record = check_root(root, contracts)
        record["selected_tests"] = (run_selected(root, TESTS[name]) if run_tests and
                                     record["status"] == "present" else
                                     {"status": "not_run" if not run_tests else "unverified"})
        records[name] = record
    complete = all(r["status"] == "present" for r in records.values())
    tests_ok = not run_tests or all(r["selected_tests"]["status"] == "passed" for r in records.values())
    return {"schema": SCHEMA, "result": "interface_ready" if complete and tests_ok else "incomplete",
            "repositories": records, "gates": {name: "unverified" for name in UNVERIFIED},
            "note": "Interface checks and selected local regressions do not establish hosted or scientific equivalence"}

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for name in CHECKS:
        p.add_argument("--" + name.replace("_", "-"), required=True, type=Path)
    p.add_argument("--run-selected-tests", action="store_true")
    p.add_argument("--output", type=Path, help="Write to a new local JSON file (never overwrite)")
    args = p.parse_args(argv)
    roots = {name: getattr(args, name).absolute() for name in CHECKS}
    result = assess(roots, run_tests=args.run_selected_tests)
    output = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as f:
            f.write(output)
    else:
        sys.stdout.write(output)
    return 0 if result["result"] == "interface_ready" else 1

if __name__ == "__main__":
    raise SystemExit(main())
