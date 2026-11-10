# UCA-11 — opt-in, read-only source-navigation acceptance

This increment adds a local Playwright probe for an **existing** eligible pyPIQUE
SAT finding. It sends no source material to external services, never launches a
SAT/AST analysis, changes no source file, and does not switch projects.

The host must already be running on a literal loopback HTTP address with an
installed Playwright Chromium. The active PAH workspace/repository must match
`workspace` and `repository` in a local JSON fixture:

```json
{
  "workspace": "<active workspace identifier>",
  "repository": "<active repository root>",
  "finding_id": "<unique existing eligible SAT finding id>",
  "relative_path": "src/example.py",
  "source_sha256": "<64 lowercase hex digits from scan-time evidence>",
  "start_line": 1
}
```

Run `python scripts/uca11_source_navigation.py --url http://127.0.0.1:5000/ --fixture /path/to/fixture.json --run-browser`.
Omit `--run-browser` to validate the fixture and URL without connecting to the host.
An optional `--output` creates a new JSON report and refuses to overwrite one.

The runner loads pyPIQUE findings via the existing read-only endpoint, selects
exactly one eligible matching option, and observes the PAH-verified navigation
event. It checks that only one editor element exists. It does **not** claim that
Ace cursor movement, editor-buffer hashing, source-analysis revision parity,
structural matches, stale-evidence rejection, or project-switch invalidation have
been proved by observing an event. These gates remain `unverified` pending
separate, representative hosted tests. Browser errors and missing test fixtures
fail or remain unverified; a passing contract probe is not release sign-off.

All pre-existing legacy and standalone workflows remain unchanged.
