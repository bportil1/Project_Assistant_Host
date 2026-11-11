#!/usr/bin/env python3
"""Offline diagnosis/opt-in repair of PAH's Code Analyzer ATLAS installation.

This changes only the selected Python environment's installed Code Analyzer
package. Source checkouts, scientific artifacts, and workspace data are untouched.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

REQUIRED_FILES = (
    "pyproject.toml",
    "code_analyzer/__init__.py",
    "code_analyzer/api.py",
    "code_analyzer/language_providers/inventory.py",
    "code_analyzer/language_providers/navigation.py",
    "code_analyzer/language_providers/_atlas_engine/parser.py",
    "code_analyzer/web/atlas_routes.py",
)

# No imports from Code Analyzer in this process; Python can retain old modules
# in sys.modules even after pip replaces the installed distribution.
PROBE = r"""
import importlib, json, sys
result = {"ok": False, "python": sys.executable}
try:
    package = importlib.import_module("code_analyzer")
    result["origin"] = getattr(package, "__file__", None)
    result["search_paths"] = list(getattr(package, "__path__", ()))
    from code_analyzer.api import CodeAnalyzer
    from code_analyzer.language_providers.inventory import atlas_files
    from code_analyzer.language_providers.navigation import build_navigation_snapshot
    from code_analyzer.web.atlas_routes import register_atlas_routes
    result["ok"] = all(callable(item) for item in
        (CodeAnalyzer, atlas_files, build_navigation_snapshot, register_atlas_routes))
except Exception as exc:
    result["error"] = f"{type(exc).__name__}: {exc}"
print(json.dumps(result))
sys.exit(0 if result["ok"] else 1)
"""


def source_problems(source: Path) -> list[str]:
    """Non-mutating, strict preflight for the local UCA-12 source package."""
    return [relative for relative in REQUIRED_FILES if not (source / relative).is_file()]


def probe_install(python: Path, cwd: Path) -> tuple[bool, dict]:
    run = subprocess.run(
        [str(python), "-c", PROBE], cwd=str(cwd), text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    try:
        report = json.loads(run.stdout.strip())
    except ValueError:
        report = {"ok": False, "error": "Import probe did not return JSON", "stderr": run.stderr[-1200:]}
    return bool(run.returncode == 0 and report.get("ok")), report


def install_source(python: Path, source: Path, cwd: Path) -> int:
    """Install the explicitly selected *local* tree; never contact package indexes."""
    cmd = [str(python), "-m", "pip", "install", "--no-index", "--no-deps",
           "--no-build-isolation", "--no-cache-dir", "--force-reinstall", str(source)]
    return subprocess.run(cmd, cwd=str(cwd), check=False).returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path,
                        help="Local Code_Repository_Cataloguer checkout containing UCA-12")
    parser.add_argument("--repair", action="store_true",
                        help="Explicitly reinstall Code Analyzer from --source into this Python environment")
    parser.add_argument("--pah-root", type=Path,
                        default=Path(__file__).resolve().parents[1],
                        help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    root = args.pah_root.resolve()
    target_venv = (root / ".venv").resolve()
    # A venv python is often a symlink to /usr/bin/python3.  Resolving it
    # selects the *system* interpreter and triggers PEP 668 during pip install.
    # Always invoke the actual venv entry point, retaining its symlink path.
    python = target_venv / "bin" / "python"
    if (Path(sys.prefix).resolve() != target_venv
            or not (target_venv / "pyvenv.cfg").is_file()
            or not python.is_file()):
        print(f"ERROR: Run with PAH's environment: {root}/.venv/bin/python {Path(__file__).name}", file=sys.stderr)
        return 2
    ok, report = probe_install(python, root)
    print("Installed Code Analyzer ATLAS imports:")
    print(json.dumps(report, indent=2))
    if args.source is None:
        if args.repair:
            parser.error("--repair requires --source to prevent reinstalling a stale checkout")
        return 0 if ok else 1
    source = args.source.expanduser().resolve()
    missing = source_problems(source)
    if missing:
        print(f"ERROR: Local source {source} lacks UCA-12 files: {', '.join(missing)}", file=sys.stderr)
        print("Apply UCA-07 through UCA-12 to that checkout before reinstalling; PAH's submodule may be older.", file=sys.stderr)
        return 2
    print(f"Local UCA-12 source: {source}")
    if not args.repair:
        print("Source is complete; add --repair to reinstall this local checkout into PAH's venv.")
        return 0 if ok else 1
    if install_source(python, source, root):
        print("ERROR: Offline Code Analyzer installation failed; check pip output above.", file=sys.stderr)
        return 1
    ok, report = probe_install(python, root)
    print("After local reinstall:")
    print(json.dumps(report, indent=2))
    if not ok:
        print("ERROR: Code Analyzer still resolves to an incompatible package; check its origin/search_paths above.", file=sys.stderr)
        return 1
    print("Code Analyzer ATLAS provider imports verified. Restart PAH to unload its previous modules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
