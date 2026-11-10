# P5-18 — Bounded pyPIQUE finding selection in PAH

This is an optional, read-only producer integration. **Load pyPIQUE findings** calls
`pique_py.source_evidence_locator.project_findings_evidence` with the active
workspace project ID and authorized repository root. Its canonical SAT findings
are read by the producer; PAH does not reinterpret finding content or synthesize
scan-time file fingerprints. The query is limited to 100 rows and fails closed if
pyPIQUE is disabled, unavailable, or exceeds the explicit bound.

A user selects an eligible finding to populate the existing source-evidence
panel and immediately run the existing server-side SHA-256 and source-line check.
Legacy records without verified source hashes remain disabled, and no editor
or source mutation is invoked. Data are never sent to remote services.

This is a producer-driven **selection UI**, not background event delivery from
the pyPIQUE browser, nor scan-time fingerprint enrichment. The P5-18 descriptor-
based path-open race hardening and hosted browser tests remain outstanding.
