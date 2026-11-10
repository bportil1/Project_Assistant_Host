# UCA-10: producer-owned job and artifact handoff (increment 1)

This is a **read-only contract and reconciliation utility**, not a new job
scheduler, persistence layer, publication API, or PAH-owned scientific result.

- An `AnalysisHandoff` identifies the active project/repository, the producer,
  an exact source SHA-256, and an explicit producer job and/or artifact ID.
- A producer `JobReader` remains the only source of job state. Absence of a
  reader or job is `unavailable`, never implicitly successful.
- A producer `ArtifactRef` remains the only source of artifact metadata. Its
  declared project/owner/ID must match and its provenance must explicitly
  include the matching source hash before the handoff can be marked
  `producer_validated`. Unknown validation is never upgraded to valid.
- An observed job is **not** proof of project/source association when the job
  record lacks those fields. Likewise, a source-matching artifact is not proof
  of numerical parity, freshness of an editor buffer, or authorization to edit.
- The module performs no filesystem writes, API requests, SQLite queries,
  job starts, cancellation, or scientific calculations.

Next UCA-10 increments can connect the adapter to the existing PAH job monitor
and artifact reference index using explicit producer APIs and workspace scope.
Hosted tests and the resulting handoff UI remain unverified.
