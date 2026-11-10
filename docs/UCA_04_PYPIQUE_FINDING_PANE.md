# UCA-04 — Verified pyPIQUE finding pane

Adds a read-only SAT finding list in the UCA pyPIQUE pane. It calls the existing P5-18 producer-owned `/api/orchestration/code-analysis/source-evidence/findings` endpoint, then passes explicit ready locators to the existing `/api/orchestration/code-analysis/source-evidence/preview` endpoint for server-side SHA-256, project, path and line verification. Missing scan-time provenance remains non-navigable. Preview text uses `textContent` only; neither SAT execution nor MI computations are changed.

Scope changes clear selections and invalidate in-flight requests. The browser never mints a source fingerprint, infers semantic relationships, or opens source editors. This patch does not publish `pah.source-selection@1` navigation events: the UCA-01 contract requires authoritative workspace/project/repository IDs that the UCA-04 browser cannot safely infer. UCA-05/06 will bind and verify those before cross-pane dispatch. Existing Code Analysis Lab and pyPIQUE standalone views are unchanged.

Acceptance pending: actual hosted Flask/browser integration, project switching during an in-flight fetch, installed pyPIQUE import compatibility, and source-file revision checks in the deployed environment. These are separate from the offline JS tests.
