#!/usr/bin/env python3
"""Explicitly align a local pyPIQUE full-extra PAH_Shared pin with the installed PAH venv.

Does not install packages, contact an index, or modify unrelated TOML keys.
"""
from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import re
import sys
import tomllib


class RepairError(ValueError):
    pass


def repaired_content(content: str, installed_version: str) -> str:
    try:
        original = tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        raise RepairError(f"Invalid pyproject.toml: {exc}") from exc
    full = original.get('project', {}).get('optional-dependencies', {}).get('full', [])
    if not isinstance(full, list):
        raise RepairError('Missing [project.optional-dependencies] full array')
    dependencies = [x for x in full if isinstance(x, str) and re.match(r'^pah[-_]shared\b', x, re.I)]
    if len(dependencies) != 1:
        raise RepairError('Expected exactly one pah-shared requirement in pyPIQUE full extra')
    major_minor = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)(?:\.post\d+)?', installed_version)
    if major_minor is None:
        raise RepairError('Installed PAH_Shared version must be a stable X.Y.Z release')
    major, minor = map(int, major_minor.group(1, 2))
    required = f'pah-shared>={major}.{minor},<{major}.{minor+1}'
    old = dependencies[0]
    if old == required:
        return content
    # Only rewrite the single exact quoted TOML dependency in the full extra.
    section = re.search(r'(?ms)^\[project\.optional-dependencies\]\s*$.*?(?=^\[|\Z)', content)
    if not section:
        raise RepairError('Could not locate optional dependency section for safe editing')
    literal = re.compile(r'(["\'])' + re.escape(old) + r'\1')
    matches = list(literal.finditer(section.group()))
    if len(matches) != 1:
        raise RepairError('Ambiguous dependency declaration; no files changed')
    item = matches[0]
    start = section.start() + item.start()
    end = section.start() + item.end()
    updated = content[:start] + item.group(1) + required + item.group(1) + content[end:]
    parsed = tomllib.loads(updated)
    if required not in parsed['project']['optional-dependencies']['full']:
        raise RepairError('Updated TOML did not retain intended requirement')
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pypique', type=Path, default=Path('modules/pypique'))
    parser.add_argument('--apply', action='store_true', help='Write pyPIQUE pyproject.toml; default is dry run')
    args = parser.parse_args(argv)
    target = args.pypique / 'pyproject.toml'
    if not target.is_file() or target.is_symlink():
        parser.error(f'Expected ordinary local pyPIQUE pyproject.toml: {target}')
    try:
        installed = version('pah-shared')
    except PackageNotFoundError:
        parser.error('pah-shared is not installed in this Python environment')
    try:
        original = target.read_text(encoding='utf-8')
        updated = repaired_content(original, installed)
    except (RepairError, UnicodeError) as exc:
        parser.error(str(exc))
    if original == updated:
        print(f'Already aligned with installed pah-shared {installed}: {target}')
        return 0
    if args.apply:
        target.write_text(updated, encoding='utf-8')
        print(f'Updated {target} for installed pah-shared {installed}; review git diff before reinstalling')
    else:
        print(f'Would align {target} to installed pah-shared {installed}; rerun with --apply to write')
    return 0


if __name__ == '__main__':
    sys.exit(main())
