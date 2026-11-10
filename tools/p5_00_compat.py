#!/usr/bin/env python3
"""Replay curated, offline Phase-4 tests without importing sibling modules.

Run from the PAH checkout. Requires only the Python standard library; individual
repositories are tested by their own Python interpreters in isolated subprocesses.
No external services are contacted by this runner.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

MANIFEST = Path(__file__).resolve().parents[1] / 'docs' / 'compatibility' / 'p5_00_suites.json'
SUMMARY = re.compile(r'(?P<count>\d+) (?P<kind>passed|failed|skipped|error|errors)', re.I)


def _pairs(items: list[str], kind: str) -> dict[str, str]:
    result = {}
    for item in items:
        name, sep, value = item.partition('=')
        if not sep or not name or not value or name in result:
            raise ValueError(f'{kind} must be a distinct module=path assignment: {item!r}')
        result[name] = value
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _tests_for(module: dict, profile: str) -> list[str]:
    suites = module['suites']
    if profile == 'scenario':
        if 'scenario' not in suites:
            return []
        return list(suites['scenario'])
    tests = list(suites['baseline'])
    if profile == 'all':
        tests.extend(suites.get('scenario', []))
    return list(dict.fromkeys(tests))


def _run_one(name: str, cfg: dict, *, root: Path, python: Path, profile: str,
             timeout: int) -> dict:
    chosen = _tests_for(cfg, profile)
    result = {'module':name, 'root':str(root), 'python':str(python),
              'archive_baseline':cfg['archive_baseline'],
              'profile':profile, 'selected_tests':chosen, 'file_sha256':{},
              'status':'not_run', 'exit_code':None, 'duration_seconds':0.0,
              'counts':{}, 'output_tail':''}
    if not chosen:
        result['reason'] = 'no tests defined for this profile'
        return result
    if not root.is_dir():
        result.update(status='unavailable',reason='repository root does not exist')
        return result
    missing = [test for test in chosen if not (root/test).is_file() and not (root/test).is_dir()]
    if missing:
        result.update(status='unavailable',reason='missing test paths',missing=missing)
        return result
    result['file_sha256'] = {p:_sha256(root/p) for p in chosen if (root/p).is_file()}
    if not python.is_file():
        # Accept Python names on PATH, but do not invoke a shell.
        import shutil
        resolved = shutil.which(str(python))
        if resolved is None:
            result.update(status='unavailable',reason='python interpreter not available')
            return result
        python = Path(resolved)
    cmd = [str(python), '-m', 'pytest', '-q', '-rs', '-o', 'addopts=', '-p', 'no:cacheprovider', *chosen]
    result['command'] = cmd
    env = os.environ.copy()
    env.update({'PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1', 'PYTHONDONTWRITEBYTECODE':'1'})
    env['PYTHONPATH'] = str((root / cfg['pythonpath']).resolve())
    started = time.monotonic()
    try:
        completed = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True,
                                   timeout=timeout, check=False)
        output = completed.stdout + '\n' + completed.stderr
        result['exit_code'] = completed.returncode
        result['status'] = 'passed' if completed.returncode == 0 else 'failed'
    except subprocess.TimeoutExpired as exc:
        def decode(value):
            return value.decode('utf-8', errors='replace') if isinstance(value, bytes) else (value or '')
        output = decode(exc.stdout) + '\n' + decode(exc.stderr)
        result['status'] = 'timed_out'
        result['reason'] = f'pytest exceeded {timeout} seconds'
    result['duration_seconds'] = round(time.monotonic() - started, 3)
    result['output_tail'] = output[-12000:]
    for match in SUMMARY.finditer(output):
        count, kind = int(match['count']), match['kind'].lower()
        result['counts'][kind] = count
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', action='append', default=[], metavar='MODULE=PATH',
                        help='Source checkout root for a module (repeatable)')
    parser.add_argument('--interpreter', action='append', default=[], metavar='MODULE=PYTHON',
                        help='Optional repository-local Python interpreter')
    parser.add_argument('--module', action='append', default=[],
                        help='Run this known module; can be repeated (default: pah)')
    parser.add_argument('--all-modules', action='store_true', help='Run all five module baselines')
    parser.add_argument('--profile', choices=['baseline','scenario','all'], default='baseline')
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--output', type=Path, help='Write a local JSON result report')
    args = parser.parse_args(argv)
    if args.timeout < 1:
        parser.error('--timeout must be positive')
    try:
        roots = _pairs(args.repo, '--repo')
        interpreters = _pairs(args.interpreter, '--interpreter')
    except ValueError as exc:
        parser.error(str(exc))
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    registered = manifest['modules']
    selected = list(registered) if args.all_modules else (list(dict.fromkeys(args.module)) or ['pah'])
    unknown = set(selected + list(roots) + list(interpreters)) - set(registered)
    if unknown:
        parser.error(f'unknown module(s): {", ".join(sorted(unknown))}')
    default_root = MANIFEST.parents[2]
    entries = []
    for name in selected:
        root = Path(roots[name]).expanduser().resolve() if name in roots else (default_root if name == 'pah' else Path('__missing_repo__'))
        python = Path(interpreters[name]).expanduser() if name in interpreters else Path(sys.executable)
        entry = _run_one(name, registered[name], root=root, python=python,
                         profile=args.profile, timeout=args.timeout)
        entries.append(entry)
        counts = ', '.join(f'{key}={value}' for key, value in entry['counts'].items())
        print(f"{name}: {entry['status']}" + (f' ({counts})' if counts else '') +
              (f" — {entry['reason']}" if entry.get('reason') else ''))
    document = {'schema':'pah.compatibility.p5_00_result', 'version':1,
                'generated_at':datetime.now(timezone.utc).isoformat(),
                'manifest_sha256':_sha256(MANIFEST), 'results':entries}
    if args.output:
        destination = args.output.expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(document, indent=2, sort_keys=True) + '\n',encoding='utf-8')
        print('Report:',destination)
    return 0 if entries and all(r['status'] == 'passed' for r in entries) else 1


if __name__ == '__main__':
    raise SystemExit(main())
