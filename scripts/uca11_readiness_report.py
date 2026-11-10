#!/usr/bin/env python3
"""Combine locally produced UCA-11 reports without elevating partial checks to sign-off.

No network access, application imports, test execution, or changes to repositories.
Reports are read as JSON and only stable, allowlisted status fields are copied.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCHEMA = "pah.uca.deployment-readiness@1"
INPUTS = {
    "baseline": "pah.uca.acceptance@1",
    "cross_repository": "pah.uca.cross-repository-acceptance@1",
    "hosted_layout": "pah.uca.hosted-workspace-acceptance@1",
    "source_navigation": "pah.uca.source-navigation-acceptance@1",
}
# A broad gate is never established by static presence or a single smoke check.
GATES = (
    "installed_checkout_patch_and_version_consistency",
    "hosted_flask_routes",
    "all_seven_pane_layouts_and_editor_buffer_preservation",
    "verified_bidirectional_source_navigation",
    "project_switching_and_stale_revision_rejection",
    "python_and_atlas_provider_behavior",
    "job_to_artifact_provenance",
    "scientific_numerical_parity",
    "legacy_standalone_behavior",
    "source_edit_security_and_recovery",
)

def _load(path: Path, expected: str) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 512_000:
        raise ValueError("report must be a regular non-symlink JSON file <= 500 KiB")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("report is unreadable or invalid JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema") != expected:
        raise ValueError("report schema does not match the declared input type")
    return payload

def _status(payload: dict, label: str) -> dict:
    if label == "baseline":
        interfaces = payload.get("interfaces")
        tests = payload.get("local_tests")
        present = isinstance(interfaces, dict) and bool(interfaces) and all(v is True for v in interfaces.values())
        tested = isinstance(tests, dict) and tests.get("status") == "passed"
        return {"interface_presence": "passed" if present else "incomplete",
                "selected_tests": "passed" if tested else "unverified"}
    if label == "cross_repository":
        records = payload.get("repositories")
        present = isinstance(records, dict) and all(name in records and isinstance(records[name], dict) and records[name].get("status") == "present" for name in ("pah", "pypique", "code_analyzer", "cps"))
        tested = present and all(records[name].get("selected_tests", {}).get("status") == "passed" for name in ("pah", "pypique", "code_analyzer", "cps"))
        return {"interface_presence": "passed" if present else "incomplete",
                "selected_tests": "passed" if tested else "unverified"}
    checks = payload.get("checks")
    checks = checks if isinstance(checks, dict) else {}
    passed = sum(v == "passed" for v in checks.values())
    failed = sum(v == "failed" for v in checks.values())
    result = payload.get("result")
    return {"observed_checks_passed": passed, "observed_checks_failed": failed,
            "run_state": "ran" if result not in (None, "not_run") else "not_run",
            "scope": "partial_hosted_observation_not_full_end_to_end_acceptance"}

def consolidate(reports: dict[str, dict | None]) -> dict:
    evidence = {name: ({"status": "not_provided"} if payload is None else _status(payload, name))
                for name, payload in reports.items()}
    has_failure = any(v.get("interface_presence") == "incomplete" or v.get("observed_checks_failed", 0) > 0
                      for v in evidence.values() if v.get("status") != "not_provided")
    return {
        "schema": SCHEMA,
        "assessment": "blocked_by_observed_failure" if has_failure else "awaiting_installed_hosted_acceptance",
        "reports": evidence,
        "acceptance_gates": {gate: "unverified" for gate in GATES},
        "legacy_retirement": "not_authorized",
        "production_deployment_signoff": "not_granted",
        "note": "Tool and smoke-test success cannot establish full workflow parity or authorize legacy removal",
    }

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in INPUTS:
        parser.add_argument("--" + name.replace("_", "-"), type=Path)
    parser.add_argument("--output", type=Path, help="New JSON file, never overwrite")
    args = parser.parse_args(argv)
    try:
        reports = {name: _load(getattr(args, name), schema) if getattr(args, name) is not None else None
                   for name, schema in INPUTS.items()}
        result = consolidate(reports)
        rendered = json.dumps(result, sort_keys=True, indent=2) + "\n"
        if args.output:
            if args.output.is_symlink():
                raise ValueError("refusing symlink output")
            with args.output.open("x", encoding="utf-8") as fh:
                fh.write(rendered)
        else:
            sys.stdout.write(rendered)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 0 if result["assessment"] != "blocked_by_observed_failure" else 1

if __name__ == "__main__":
    raise SystemExit(main())
