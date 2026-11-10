# UCA-10 increment 3: explicit producer-issued handoff

The unified workspace can inspect a producer-supplied `pah.uca-analysis-handoff@1` JSON
object. This is intentionally **manual**, not an inferred association from a
completed job or filename. PAH checks active project/repository identity,
reads the already-attached producer JobReader, and looks up only existing
registered ArtifactRef IDs. It never publishes, edits or opens artifact content.

Results keep job `observed` separate from artifact `producer_validated`.
No artifact ID, no registry entry, absent source hash, mismatch, or unknown
validation state can be upgraded by the UI. When a producer issues no handoff,
there is nothing to verify. Changing workspace clears the display.

A `producer_validated` descriptor means the producer's current registry
record claims valid state and matches the supplied source hash; this is
not a cryptographic attestation of scientific equivalence or of immutable
artifact bytes. Actual live publisher-to-UI transport and browser acceptance
remain open; no legacy path is retired.
