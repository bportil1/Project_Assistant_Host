#!/usr/bin/env python3
"""UCA-00: offline, read-only integration interface inventory.

Supply explicit checkout roots. No imports from modules, network calls, writes to
checkouts, discovery of unrelated files, or execution of project-specific code.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

CHECKS = {
    "pah": {
        "workspace_owner": "pah/core/workspace.py",
        "host_app": "pah/app.py",
        "code_analysis_controller": "pah/labs/code_analysis.py",
        "editor_shell": "pah/web/templates/index.html",
        "module_contract": "pah/contracts/module.py",
    },
    "pypique": {
        "scientific_module": "src/pique_py/__init__.py",
        "visualizer": "src/pique_py/visualizer.py",
    },
    "code_analyzer": {
        "public_api": "code_analyzer/api.py",
        "python_catalog": "code_analyzer/catalog/scanner.py",
        "source_refactor": "code_analyzer/catalog/refactor/function_mover.py",
        "web_app": "code_analyzer/web/app.py",
    },
    "cps": {
        "atlas_lexer": "src/cps_lab/atlas/lexer.py",
        "atlas_parser": "src/cps_lab/atlas/parser.py",
        "atlas_analysis": "src/cps_lab/atlas/analysis.py",
        "artifact_contract": "src/cps_lab/integration/contracts.py",
        "integration_spec": "docs/INTEGRATION_CONTRACTS.md",
    },
}

# These are expected only if the corresponding prior migration was applied.
OPTIONAL = {
    "pah": {"p5_source_evidence": "pah/labs/source_evidence.py"},
    "pypique": {"p5_finding_evidence": "src/pique_py/finding_evidence.py"},
    "code_analyzer": {"p5_source_index": "code_analyzer/catalog/source_index.py"},
    "cps": {},
}


def _inspect(root: Path, required: dict[str, str], optional: dict[str, str]) -> dict:
    if not root.is_dir():
        return {"status": "missing_checkout", "required": {}, "optional": {}, "missing_required": list(required)}
    # lstat-esque inspection avoids reading or following links within a checkout.
    def exists_regular(rel: str) -> bool:
        cur = root
        for part in Path(rel).parts:
            cur = cur / part
            if cur.is_symlink():
                return False
        return cur.is_file()
    req = {name: {"relative_path": rel, "present": exists_regular(rel)} for name, rel in required.items()}
    opt = {name: {"relative_path": rel, "present": exists_regular(rel)} for name, rel in optional.items()}
    missing = [name for name, item in req.items() if not item["present"]]
    return {"status": "incomplete" if missing else "interface_files_present",
            "required": req, "optional": opt, "missing_required": missing}


def inspect_repositories(roots: dict[str, Path]) -> dict:
    """Return a metadata-only report; existence is not operational acceptance."""
    checks = {name: _inspect(roots[name], required, OPTIONAL[name])
              for name, required in CHECKS.items()}
    return {
        "schema": "pah.uca.baseline@1",
        "privacy": "local_metadata_only",
        "scope": "interface_presence_not_runtime_or_parity",
        "repositories": checks,
        "all_required_present": all(x["status"] == "interface_files_present" for x in checks.values()),
        "acceptance": {
            "flask_browser": "unverified",
            "sat_execution": "unverified",
            "atlas_semantics": "unverified",
            "source_revision_sync": "unverified",
            "scientific_parity": "unverified",
            "standalone_compatibility": "unverified",
        },
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    for name in CHECKS:
        p.add_argument("--" + name.replace("_", "-"), type=Path, required=True,
                       help=f"Local {name} checkout root")
    p.add_argument("--output", type=Path, help="Optional local JSON report (stdout by default)")
    args = p.parse_args(argv)
    roots = {name: getattr(args, name) for name in CHECKS}
    result = inspect_repositories(roots)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        # Do not overwrite any existing report or repository file.
        with args.output.open("x", encoding="utf-8") as f:
            f.write(rendered)
    else:
        sys.stdout.write(rendered)
    return 0 if result["all_required_present"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
