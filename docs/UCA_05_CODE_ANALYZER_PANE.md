# UCA-05 — Code Analyzer pane integration

This optional pane consumes existing PAH `/api/analyzer/status`, `/api/analyzer/functions`,
`/api/analyzer/entity` and `/api/analyzer/dependencies` endpoints. The explicit Run
button uses the pre-existing `/api/analyzer/analyze` endpoint; opening this pane never
starts a job. The existing analyzer controller remains authoritative.

The listing is intentionally capped at 200 and is **not** represented as an exhaustive
result set. Stale state is displayed and never silently corrected; no source span is
verified or navigated in UCA-05. UCA-06 will bridge navigation through UCA-01's
revision-aware source-selection contract. This pane does not call source-edit APIs,
change saved settings, modify SQLite, or replace Code Analyzer's legacy UI.

## Acceptance and open gates
- Inspect current/unanalyzed/stale results from an existing workspace.
- Select an entity to retrieve its producer-owned metadata and dependency counts.
- Reject malformed responses; discard requests after workspace/repository changes.
- Verify existing Code Analyzer UI and standalone operation independently.
- Hosted browser integration, authorization in target deployment, exact source
  verification, and synchronized selection remain unverified at this stage.
