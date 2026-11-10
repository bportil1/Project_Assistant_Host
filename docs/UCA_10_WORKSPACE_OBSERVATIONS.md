# UCA-10: workspace producer observation (increment 2)

The Unified Analysis page now offers an **explicit** read-only refresh of PAH's
existing `/api/jobs` monitor feed, plus a shortcut to the existing job drawer.
No new scheduler, producer DB reader, artifact publication path, or job state is
introduced. The browser checks the authoritative `/api/uca/navigation/scope`
identity before and after job retrieval, rejecting a scope change in flight.

**A job observation is not source-specific provenance.** The job registry does
not require a verified `source_sha256` or `project_id` for each job; therefore
these rows are labeled *observed only*, even when succeeded. No artifact is
marked validated or linked by job name, timing, or successful completion.
Actual job-to-source and artifact-to-source verification remains governed by
`pah.contracts.uca_coordination.inspect_handoff` with explicit producer-issued
IDs and provenance, to be wired into the hosted interface after producer APIs
expose those identifiers. Missing readers/jobs remain unavailable.

Status refresh is manual. Changing workspaces clears the view. The original
job monitor and UCA pane behavior remain unchanged. Browser integration, live
producer jobs, and actual artifact handoff are not proven by unit tests.
