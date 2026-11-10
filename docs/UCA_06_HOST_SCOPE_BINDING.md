# UCA-06 — Host scope binding increment

This is an additive follow-up to the verified pyPIQUE-to-editor navigation foundation.

- The active PAH workspace profile defines both workspace and project IDs for now; the selected repository resource is given a deterministic `repo-<SHA256-of-normalized-root>` ID. This is **repository identity**, not a source-content hash.
- `/api/uca/navigation/scope` is a read-only, no-store identity endpoint. No server-side navigation event is published or authorized by it. The P5-18 preview route remains the source authorization gate.
- Browser dispatch fetches this scope **after** the verified evidence response, requires it to match the selected UI workspace/repository, and rejects stale requests after a scope change. Event consumers retain independent file-revision checks.
- No editor-originated or Code Analyzer-originated selection is presented as verified until its source-revision provenance is demonstrable. Code Analyzer's line overlaps remain candidates.
- Does not replace UCA-01's Python coordinator. Server dispatch integration, bidirectional navigation, browser acceptance and independent project IDs are still future work.
