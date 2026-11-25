#!/usr/bin/env python3
"""Retire PAH-owned Git gitlinks without deleting embedded working-tree data.

Dry-run by default. Explicit --apply moves all legacy module directory entries
into a sibling recovery directory, then stages deletion of index gitlinks only.
The standalone source repositories are never accessed or modified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
import sys


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )
    if result.returncode:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def tracked_gitlinks(root: Path) -> tuple[list[tuple[str, str]], list[str]]:
    proc = subprocess.run(
        ["git", "ls-files", "--stage", "-z", "--", "modules"],
        cwd=root, capture_output=True, check=True,
    )
    links: list[tuple[str, str]] = []
    unexpected: list[str] = []
    for row in proc.stdout.split(b"\0"):
        if not row:
            continue
        meta, path_bytes = row.split(b"\t", 1)
        mode, oid, stage = meta.decode("ascii").split()
        path = path_bytes.decode("utf-8", errors="surrogateescape")
        if mode == "160000" and stage == "0" and path.startswith("modules/"):
            links.append((path, oid))
        elif path != "modules/README.md":
            unexpected.append(path)
    return links, unexpected


def inspect(root: Path) -> tuple[list[tuple[str, str]], list[str], list[Path]]:
    root = root.resolve()
    if git(root, "rev-parse", "--show-toplevel").strip() != str(root):
        raise RuntimeError("Run from the standalone PAH host Git repository root")
    if not (root / "pah" / "components.py").is_file():
        raise RuntimeError("This is not a PAH host source checkout")
    modules = root / "modules"
    if modules.is_symlink():
        raise RuntimeError("PAH/modules is a symlink: refuse to touch its target")
    if (root / ".gitmodules").exists():
        raise RuntimeError("Apply the PAH source-ownership patch before retirement (.gitmodules still exists)")
    links, unexpected = tracked_gitlinks(root)
    entries = sorted(modules.iterdir()) if modules.is_dir() else []
    if any(p.is_symlink() for p in entries):
        raise RuntimeError("Found symlink inside modules; inspect it manually before retiring the directory")
    return links, unexpected, entries


def retire(root: Path, *, apply: bool = False) -> Path | None:
    root = root.resolve()
    links, unexpected, entries = inspect(root)
    if unexpected:
        raise RuntimeError("Unexpected tracked module files (refusing to stage their deletion): " + ", ".join(unexpected))
    print(f"PAH host: {root}")
    print(f"Tracked legacy gitlinks: {len(links)}")
    for path, oid in links:
        print(f"  {path} -> {oid[:12]}")
    print(f"Physical legacy entries: {len(entries)}")
    for entry in entries:
        print(f"  {entry.name}/" if entry.is_dir() else f"  {entry.name}")
    if not links and not entries:
        print("Already retired: no tracked gitlinks or embedded worktrees remain.")
        return None
    if not apply:
        print("DRY RUN — nothing changed. Use --apply for recovery move and index cleanup.")
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    recovery = root.parent / f"{root.name}_embedded_module_recovery_{timestamp}"
    if recovery.exists():
        raise RuntimeError(f"Recovery destination already exists: {recovery}")
    recovery.mkdir(mode=0o700)
    (recovery / "modules").mkdir()
    manifest = [
        "PAH embedded-module recovery (source files preserved, not deleted)",
        f"Original PAH root: {root}",
        "Legacy tracked gitlinks:",
        *[f"  {path}: {oid}" for path, oid in links],
        "",
        "The original embedded worktree entries were moved under modules/ here.",
        "Dirty/untracked files and folders are retained as-is. A submodule .git",
        "pointer may still reference Git metadata under the original PAH/.git/modules",
        "directory; move back before using the original submodule Git metadata.",
        "Reconcile any needed files with your STANDALONE source repositories manually.",
        "Do not delete this recovery tree until those differences are reviewed.",
        "The standalone source repositories were never touched.",
    ]
    (recovery / "RECOVERY_README.txt").write_text("\n".join(manifest) + "\n", encoding="utf-8")
    for entry in entries:
        shutil.move(str(entry), str(recovery / "modules" / entry.name))

    if links:
        # git rm --cached removes the *index gitlinks* only. The worktrees are
        # already preserved outside PAH; this never invokes `git submodule`.
        git(root, "rm", "--cached", "-f", "--ignore-unmatch", "--", *[p for p, _ in links])
    (root / "modules").mkdir(exist_ok=True)
    print(f"Recovery copy: {recovery}")
    print("Tracked gitlink removals staged; review `git diff --cached --submodule=short`.")
    print("Stage remaining PAH patch files separately, then commit the Git removals.")
    return recovery


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Move embedded entries to sibling recovery directory and stage index gitlink removal")
    args = parser.parse_args(argv)
    try:
        retire(Path(__file__).resolve().parents[1], apply=args.apply)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
