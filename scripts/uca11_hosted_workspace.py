#!/usr/bin/env python3
"""Opt-in loopback-only UCA hosted workspace smoke checks.

Requires an already running local PAH host and a locally installed Playwright Chromium
browser. Never installs, downloads, changes project data or executes analysis jobs.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

SCHEMA = 'pah.uca.hosted-workspace-acceptance@1'
PANES = ('editor', 'pypique', 'analyzer')
BROWSER_GATES = (
    'verified_sat_to_editor', 'editor_to_sat', 'analyzer_to_editor',
    'project_switching', 'python_atlas_provider_execution',
    'job_artifact_provenance', 'unsaved_buffer_round_trip',
    'scientific_parity', 'legacy_standalone', 'source_edit_recovery',
)


def validate_loopback_url(url: str) -> str:
    """Only literal numeric loopback hosts; no URLs with credentials or query tokens."""
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        if (parsed.scheme != 'http' or not host or parsed.username is not None
                or parsed.password is not None or parsed.query or parsed.fragment
                or parsed.path not in ('', '/') or parsed.port is None
                or not ipaddress.ip_address(host).is_loopback):
            raise ValueError('Only http://127.0.0.1:PORT/ or http://[::1]:PORT/ is allowed')
    except (ValueError, TypeError) as exc:
        raise ValueError('A numeric loopback HTTP URL with explicit port is required') from exc
    return url


def combinations():
    return tuple(tuple(p for i, p in enumerate(PANES) if mask & (1 << i))
                 for mask in range(1, 1 << len(PANES)))


def initial_report():
    return {'schema': SCHEMA, 'result': 'not_run', 'checks': {},
            'gates': {name: 'unverified' for name in BROWSER_GATES},
            'note': 'Pane checks alone never establish source, scientific, or legacy parity'}


def _exercise(page):
    checks = {}
    page.goto('/', wait_until='domcontentloaded', timeout=12000)
    page.locator('[data-mode="uca"]').click()
    root = page.locator('#ucaMode')
    root.wait_for(state='visible', timeout=5000)
    checks['uca_mode'] = 'passed'
    toggles = {name: page.locator(f'[data-uca-toggle="{name}"]') for name in PANES}
    panes = {name: page.locator(f'[data-uca-pane="{name}"]') for name in PANES}
    reset = page.locator('#ucaReset')
    editor = page.locator('#editor')
    checks['editor_unique'] = 'passed' if editor.count() == 1 else 'failed'
    for combo in combinations():
        reset.click()
        for name in PANES:
            if name not in combo:
                toggles[name].uncheck()
        if not all(panes[name].is_visible() == (name in combo) for name in PANES):
            checks['pane_' + '_'.join(combo)] = 'failed'
        else:
            checks['pane_' + '_'.join(combo)] = 'passed'
        if 'editor' in combo and editor.count() == 1:
            if not page.locator('#ucaEditorMount #editor').count():
                checks['editor_docking_' + '_'.join(combo)] = 'failed'
            else:
                checks['editor_docking_' + '_'.join(combo)] = 'passed'
    reset.click()
    # The former Workspace navigation button is intentionally absent; its
    # original explorer and Ace editor are now docked into Unified Analysis.
    checks['file_explorer_docked'] = ('passed' if page.locator('#ucaExplorerDock #projectPane').count() == 1
                                      else 'failed')
    explorer = page.locator('#ucaExplorerToggle')
    explorer.click()
    checks['file_explorer_toggle'] = ('passed' if page.locator('#ucaExplorerDock #projectPane').count() == 0
                                     else 'failed')
    explorer.click()
    grip = page.locator('[data-uca-grip="editor-pypique"]')
    if grip.count() and grip.is_visible():
        before = float(panes['editor'].evaluate('(el) => el.style.flexGrow'))
        grip.press('ArrowRight')
        after = float(panes['editor'].evaluate('(el) => el.style.flexGrow'))
        checks['resizable_width'] = 'passed' if after > before else 'failed'
    else:
        checks['resizable_width'] = 'failed'
    for name in PANES:
        reset.click()
        detach = page.locator(f'[data-uca-detach="{name}"]')
        try:
            with page.expect_popup(timeout=6000) as opened:
                detach.click()
            popup = opened.value
            popup.locator('#ucaMode').wait_for(state='visible', timeout=9000)
            checks[f'detach_{name}'] = ('passed' if not panes[name].is_visible()
                and popup.locator(f'[data-uca-pane="{name}"]').is_visible() else 'failed')
            popup.close()
            panes[name].wait_for(state='visible', timeout=4500)
            checks[f'reattach_{name}'] = 'passed'
        except Exception:
            checks[f'detach_{name}'] = 'failed'
            checks[f'reattach_{name}'] = 'failed'
            # A popup can be blocked in the actual installed browser; record
            # failure rather than silently treating the UI as accepted.
            break
    # Hiding the Editor pane must return the *same* Ace DOM, not clone it.
    reset.click()
    toggles['editor'].uncheck()
    checks['editor_restore'] = ('passed' if page.locator('#workspaceMode > .main-pane #editor').count() == 1
                                and editor.count() == 1 else 'failed')
    toggles['editor'].check()
    checks['editor_redock'] = ('passed' if page.locator('#ucaEditorMount #editor').count() == 1
                               and editor.count() == 1 else 'failed')
    return checks


def run_browser(url: str):
    from playwright.sync_api import sync_playwright
    parsed = urlsplit(url)
    allowed = (parsed.hostname, parsed.port)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            context = browser.new_context(base_url=url, accept_downloads=False, service_workers='block')
            def guard(route):
                target = urlsplit(route.request.url)
                try:
                    safe = (target.scheme == 'http' and (target.hostname, target.port) == allowed
                            and not target.username and not target.password)
                except ValueError:
                    safe = False
                if safe:
                    route.continue_()
                else:
                    route.abort()
            context.route('**/*', guard)
            page = context.new_page()
            return _exercise(page)
        finally:
            browser.close()


def assess(url: str, *, execute: bool = False):
    validate_loopback_url(url)
    report = initial_report()
    if not execute:
        return report
    try:
        report['checks'] = run_browser(url)
    except (ImportError, OSError) as exc:
        report['result'] = 'unverified'
        report['reason'] = type(exc).__name__
        return report
    except Exception as exc:
        # A missing local browser or inaccessible host is not a passing test.
        report['result'] = 'unverified'
        report['reason'] = type(exc).__name__
        return report
    report['result'] = ('smoke_passed' if report['checks'] and
                        all(x == 'passed' for x in report['checks'].values()) else 'failed')
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True, help='Numeric loopback URL of an already running PAH host')
    parser.add_argument('--run-browser', action='store_true', help='Explicitly exercise local Chromium; default is validation only')
    parser.add_argument('--output', type=Path, help='Create a new report; never overwrite')
    args = parser.parse_args(argv)
    try:
        result = assess(args.url, execute=args.run_browser)
    except ValueError as exc:
        parser.error(str(exc))
    content = json.dumps(result, indent=2, sort_keys=True) + '\n'
    if args.output:
        with args.output.open('x', encoding='utf-8') as dest:
            dest.write(content)
    else:
        sys.stdout.write(content)
    return 0 if result['result'] == 'smoke_passed' or not args.run_browser else 1


if __name__ == '__main__':
    raise SystemExit(main())
