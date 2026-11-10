#!/usr/bin/env python3
"""Optional read-only UCA-11 SAT-to-editor navigation acceptance against a local PAH host.

Requires an existing, verified SAT finding in the selected repository. Does not run
analyzers, edit files, switch repositories, or infer missing source provenance.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

_HOSTED = Path(__file__).with_name('uca11_hosted_workspace.py')
_spec = importlib.util.spec_from_file_location('uca11_hosted_workspace', _HOSTED)
_hosted = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hosted)
SCHEMA = 'pah.uca.source-navigation-acceptance@1'
HASH = re.compile(r'^[0-9a-f]{64}$')
REQUIRED = ('workspace', 'repository', 'finding_id', 'relative_path', 'source_sha256', 'start_line')
GATES = ('sat_to_editor', 'analyzer_candidate_context', 'editor_to_sat',
         'analyzer_to_editor', 'stale_source_rejection', 'project_switching',
         'revision_parity', 'legacy_preservation')


def fixture_fields(obj):
    if not isinstance(obj, dict) or any(not isinstance(obj.get(k), str) or not obj[k]
                                        for k in REQUIRED[:-1]):
        raise ValueError('Fixture requires nonempty workspace, repository, finding_id, relative_path, and source_sha256')
    if not HASH.fullmatch(obj['source_sha256']):
        raise ValueError('Fixture requires a lowercase source SHA-256')
    rel = obj['relative_path']
    if (rel.startswith('/') or '\\' in rel or ':' in rel or '%' in rel or '\x00' in rel or
            any(seg in ('', '.', '..') for seg in rel.split('/'))):
        raise ValueError('Fixture source path must be a safe repository-relative path')
    if type(obj.get('start_line')) is not int or obj['start_line'] < 1:
        raise ValueError('Fixture start_line must be a positive integer')
    return {key: obj[key] for key in REQUIRED}


def initial_report():
    return {'schema': SCHEMA, 'result': 'not_run',
            'gates': {key: 'unverified' for key in GATES},
            'checks': {},
            'note': 'An observed selection is not proof of AST, scientific or legacy parity'}


def browser_probe(url, fixture):
    from playwright.sync_api import sync_playwright
    addr = urlsplit(url)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(base_url=url, accept_downloads=False, service_workers='block')
            def guard(route):
                remote = urlsplit(route.request.url)
                if (remote.scheme == 'http' and (remote.hostname, remote.port) ==
                        (addr.hostname, addr.port) and not remote.username and not remote.password):
                    route.continue_()
                else:
                    route.abort()
            context.route('**/*', guard)
            page = context.new_page()
            page.goto('/', wait_until='domcontentloaded', timeout=12000)
            if (page.locator('#researchWorkspaceSelect').input_value() != fixture['workspace'] or
                    page.locator('#workspacePath').input_value() != fixture['repository']):
                return {'scope': 'failed'}, 'unverified'
            page.locator('[data-mode="uca"]').click()
            page.evaluate("""() => {
              window.__uca11Observations = [];
              window.addEventListener('pah:uca-navigate-editor', e => {
                const s = e.detail?.selection;
                if(s) window.__uca11Observations.push({path:s.relative_path,
                  hash:s.source_sha256,line:s.start_line,producer:s.producer});
              });
            }""")
            page.locator('#ucaFindingLoad').click()
            page.wait_for_function("""() => !document.getElementById('ucaFindingLoad').disabled""", timeout=15000)
            options = page.locator('#ucaFindingSelect option').evaluate_all(
                '(nodes) => nodes.map(n => ({value:n.value,label:n.textContent,disabled:n.disabled}))')
            matching = [o for o in options if not o['disabled'] and fixture['finding_id'] in o['label']
                        and fixture['relative_path'] in o['label']]
            if len(matching) != 1:
                return {'matching_finding': 'failed'}, 'unverified'
            page.locator('#ucaFindingSelect').select_option(matching[0]['value'])
            page.wait_for_function("""() => window.__uca11Observations?.length > 0""", timeout=15000)
            observations = page.evaluate('window.__uca11Observations')
            match = any(o['path'] == fixture['relative_path'] and
                        o['hash'] == fixture['source_sha256'] and
                        o['line'] == fixture['start_line'] and o['producer'] == 'pypique'
                        for o in observations)
            checks = {'matching_finding': 'passed', 'verified_navigation_dispatch': 'passed' if match else 'failed'}
            # Confirm the existing editor is still a single element. Its actual
            # source hash/cursor correctness is enforced by PAH, but cannot be
            # inferred from receipt of a navigation event alone.
            checks['single_editor'] = 'passed' if page.locator('#editor').count() == 1 else 'failed'
            return checks, 'observed' if match else 'unverified'
        finally:
            browser.close()


def assess(url, fixture, *, execute=False):
    _hosted.validate_loopback_url(url)
    fixture = fixture_fields(fixture)
    report = initial_report()
    if not execute:
        return report
    try:
        checks, navigation = browser_probe(url, fixture)
    except Exception as exc:
        report['result'] = 'unverified'
        report['reason'] = type(exc).__name__
        return report
    report['checks'] = checks
    if navigation == 'observed' and all(x == 'passed' for x in checks.values()):
        report['gates']['sat_to_editor'] = 'navigation_event_observed'
        report['result'] = 'observed_not_fully_verified'
    else:
        report['result'] = 'failed' if any(x == 'failed' for x in checks.values()) else 'unverified'
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--fixture', type=Path, required=True, help='Local JSON naming a real SAT finding and source identity')
    parser.add_argument('--run-browser', action='store_true', help='Opt in to local Playwright execution')
    parser.add_argument('--output', type=Path, help='Create a report without overwriting an existing file')
    args = parser.parse_args(argv)
    try:
        report = assess(args.url, json.loads(args.fixture.read_text(encoding='utf-8')),
                        execute=args.run_browser)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    content = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.output:
        with args.output.open('x', encoding='utf-8') as out:
            out.write(content)
    else:
        sys.stdout.write(content)
    return 0 if (not args.run_browser or report['result'] == 'observed_not_fully_verified') else 1


if __name__ == '__main__':
    raise SystemExit(main())
