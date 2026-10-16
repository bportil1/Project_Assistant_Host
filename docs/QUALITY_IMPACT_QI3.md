# QI-3 — Native Standard PIQUE Forward Evaluation

QI-3 extends PAH Code Analysis Lab stage 4 **after** QI-1 and QI-2. It consumes the immutable MF-5 concluded Standard ZIP/directory through pyPIQUE's `load_standard_concluded_model` and evaluates the native `QualityModel` — diagnostic values, actual measure normalizers, transforms and utilities, configured PF/QA aggregation, and TQI. **No PAH-native approximation of PIQUE evaluation is used.** Historical MF-5 acceptance remains separate from scenario evaluation. This does not alter model parameters, source code, findings, or the workspace database.

## Why an explicit bridge is necessary

QI-2 observations are **counts of matching SAT records**. PIQUE's native `DiagnosticEvaluator` sums the severities of findings, not simply the count of records. Furthermore, finalized model node values intentionally contain no target runtime values. A count cannot therefore be silently used as a model-native diagnostic, nor can absence of findings be assumed to be a zero.

Create a **local JSON mapping** supplying every Standard diagnostic's native baseline value and provenance. Bind it in stage 4 via **Bind verified native inputs**. It must match both the selected model manifest SHA256 and the current SAT evidence SHA256. For a diagnostic whose QI-2 count you want to change, optionally declare `native_units_per_finding`: an **explicit scenario assumption**, not a learned conversion. If a changed node has no declared conversion, baseline evaluation may be available, but scenario evaluation is blocked. Model or evidence changes invalidate the selection; mapping changes invalidate only the mapping, retaining QI-2 scenario edits.

```json
{
  "schema": "pah.standard_native_diagnostic_mapping",
  "schema_version": 1,
  "model_manifest_sha256": "<SHA256 from selected model>",
  "sat_evidence_sha256": "<SHA256 from selected SAT evidence>",
  "diagnostics": {
    "CWE-79": {
      "baseline_native_value": 2.0,
      "native_units_per_finding": 1.0,
      "provenance": "Documented native sum of unit-severity findings"
    },
    "CWE-89": {
      "baseline_native_value": 0.0,
      "provenance": "Verified native value from the selected analysis"
    }
  }
}
```

Replace IDs and native values with **all diagnostics in your concluded model**, even those not linked to observed SAT records. Verify values against the same evidence/model run; a hash match proves file identity, **not that the supplied numbers are scientifically valid**. Only assign zero if your diagnostic acquisition genuinely established zero. The `native_units_per_finding` number should be used only where a defensible conversion is documented. Revisions to the mapping require rebinding. No external files referenced within the mapping are opened.

## Native model calculation

Each evaluation loads a fresh independently verified native `QualityModel`. It injects explicitly supplied diagnostic values into those input nodes, asks the pyPIQUE evaluators to compute their actual graph values, and reports node values separately for diagnostics, measures, PFs, QAs and TQI. It reuses the concluded model's own normalization, value transformation, utility functions and aggregation strategies, including legacy idiosyncrasies. For a hypothetical count edit of a supported diagnostic, the native value is defined **only** by this declared mapping: `baseline_native_value + (hypothetical_count - observed_count) × native_units_per_finding`. Out-of-domain values or missing conversion factors block scenario results. No scenario values are written back to the concluded archive or evidence.

Result schema: `pah.standard_forward_evaluation@1`. `status` is one of `needs_mapping`, `ready`, `scenario_blocked`, `blocked`, or `not_applicable` (MI). When ready, the result contains separate `baseline` and `scenario` native node values and precise mapping/model/evidence/scenario fingerprints. QI-4 adds impact-oriented deltas and affected-path highlighting; QI-5 defines MI's distinct probabilistic inference contract.

## API

- `POST /api/orchestration/code-analysis/quality-impact/forward/inputs` with `{ "path": "/local/native_inputs.json" }` validates/binds inputs for this workspace without undoing QI-2 edits.
- `POST /api/orchestration/code-analysis/quality-impact/forward/clear` unbinds QI-3 inputs only.
- Existing GET snapshot, model selection, and QI-2 scenario action responses now include `forward_evaluation`. No new server-side persistent storage is introduced.
