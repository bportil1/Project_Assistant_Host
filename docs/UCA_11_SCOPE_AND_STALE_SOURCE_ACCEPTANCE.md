# UCA-11 — Workspace switching and stale-source acceptance

## Scope

This increment exercises the existing browser navigation controller offline using
controlled asynchronous responses. It does not create synthetic SAT results in a
live project, switch a user's live workspace, edit source, or trigger analysis.

Run:

```sh
node --test tests/uca11_scope_stale_acceptance.test.mjs
```

## Checked behavior

- Switching projects while the host scope is unresolved prevents the old source
  verification request and prevents subsequent pane navigation.
- A rejected source revision (e.g., changed source fingerprint) never publishes
  a navigation event.
- A verified editor-originated selection is delivered to other panes exactly
  once and is not echoed back to its producer.
- Changing repositories while source verification is pending invalidates the
  old response before any pane event is published.

A narrow controller fix stops an unnecessary verification request after the
host scope has already become stale. The server remains authoritative for
source fingerprint checks and authorization.

## Acceptance remaining

These tests **do not** verify a running Flask host, actual Ace cursor position,
real SAT finding provenance, a real project switch in the browser, or numerical
and legacy parity. Keep those gates pending for user-hosted UCA-11 verification.
