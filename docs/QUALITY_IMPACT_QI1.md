# QI-1 — Code Analysis Lab: Quality Impact Analysis

The **fourth** Code Analysis Lab stage is a read-only inspector of one **finalized** Standard or MI-Informed PIQUE model. Stage 2 (`quality_modeling`) and the upstream representation workflow remain unchanged. The existing stage identifier (`mi_informed_analysis`) remains stable for historical PAH artifact/launch consumers, while the new user-facing surface is independent of an unfinalized MI experiment.

## Open a model

1. Conclude a model in the pyPIQUE **Model Finalization** tab (MF-3 or MF-4, MF-5 verified ZIP).
2. Open PAH → Code Analysis Lab → **4. Quality Impact Analysis**.
3. Enter the absolute local path to the concluded ZIP (or version directory). The host calls the **pyPIQUE-owned** `read_conclusion` verifier via the installed package or local `modules/pypique/src` checkout. There is no network fallback and no reimplementation of pyPIQUE integrity rules.
4. Optionally select a local SAT JSON findings file in the pyPIQUE `diagnostics` map format or canonical `findings` list format. Explicit CWE IDs (including numeric IDs in `cwe_id` or lists in `cwes`) and explicitly named Standard diagnostics are linked to their corresponding recorded nodes. Findings with no explicit matching node remain **unmatched** rather than being inferred from similar labels.
5. Inspect original recorded graph nodes and links, their metadata, and source-reported finding locations. For MI, switch between the **original signed information topology** and the **separate learned probabilistic backing**; they are never merged or treated as equivalent scores. Recorded acceptance values are historical finalization data, **not** a simulated outcome.

Selections are temporary and project-workspace-scoped, never written to PAH or module-private databases. SHA256 content integrity, version identity, and selected evidence SHA256 are rechecked on subsequent reads; a modified file invalidates the selection and requires explicit reselection. Source paths inside model provenance and finding locations are **display-only**; QI-1 never reads, edits, or traverses them.

## Limits and future steps

QI-1 does **not** simulate changed findings, calculate altered PF/TQI scores, or modify source. It does not certify that a finding is correct, or make causal claims. A SHA256 digest detects inconsistency but is not an author signature. QI-2 adds temporary reversible diagnostic scenarios; QI-3 adds actual concluded Standard evaluation; QI-4 compares those results; QI-5 defines the stable MI evidence/inference handoff. This stage intentionally preserves existing PIQUE/MI scoring, aggregation, and network semantics.

Routes: `GET /api/orchestration/code-analysis/quality-impact`, `POST .../select` with `{"path":"/local/model.zip","findings_path":"/local/findings.json"}`, and `POST .../clear`. The inspector never auto-discovers models across project directories or alters an existing pyPIQUE finalized version. A missing local pyPIQUE verifier is an explicit user-visible error, not a silently permissive alternate parser.
