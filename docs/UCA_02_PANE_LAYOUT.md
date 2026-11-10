# UCA-02 — Configurable pane layout

**Scope:** PAH user-interface layout shell only. UCA-01 source-selection Python contract is unchanged. No module is embedded or mounted by this patch; UCA-03–06 will attach existing editor, pyPIQUE and Code Analyzer clients.

- New **Unified Analysis** mode contains three independent selectable pane slots.
- Each slot has an adjustable relative width (15–70) and at least one slot stays visible. Narrow screens stack panes to preserve usability.
- Layout preferences are optional browser-local data scoped to both selected research workspace and current repository path; storage failure is nonfatal. No layout values are sent to the server.
- Switching active workspace/repository resets or restores the matching view state. The existing Workspace editor, Code Analysis Lab, module routes, jobs and standalone module interfaces are untouched.
- No arbitrary iframe URLs are accepted; panes display clear future integration placeholders.
- Rendering or closing a slot never launches, cancels, or recomputes scientific jobs.

## Outstanding acceptance

- UCA-03 mounts the source editor without duplicate editable buffers.
- UCA-04/05 connect pyPIQUE and Code Analyzer and verify module authorization.
- UCA-06 binds selections from the UCA-01 scoped event coordinator.
- Hosted browser acceptance (including project switching, keyboard, resizing and layout persistence) remains unverified until exercised in PAH.
- No legacy implementation is eligible for retirement.
