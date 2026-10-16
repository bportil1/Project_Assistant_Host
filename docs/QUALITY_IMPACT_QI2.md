# QI-2 — Reversible Diagnostic Evidence Scenarios

QI-2 extends QI-1's **fourth** Code Analysis Lab stage. It operates only on one verified concluded model and **explicitly matched** local SAT findings. PAH retains hypothetical edits **in memory**, isolated by workspace and concluded-model/evidence lineage. It does not write to concluded archives, SAT JSON, source repositories, PAH artifacts, or module-private databases.

## Scenario semantics (important)

For an explicitly mapped Standard **diagnostic** or MI **CWE/feature** node, QI-2 computes the *observed number of matching SAT records* in the selected evidence JSON. The unit is `matched_sat_finding_count`, and each baseline records the diagnostic/CWE identifiers, directly configured measure connections (when any), evidence path, evidence SHA256, concluded manifest SHA256, version ID, and family. This is **not necessarily the model-native diagnostic value**. A node with no matched SAT finding has an **unknown observation**, not a verified zero: it is not offered for editing. QI-2 never converts findings counts into a normalized measure, activation, posterior, score, or quality indicator. MI/PMI is not reestimated here. Existing PIQUE/MI semantics are unchanged.

## How to use

1. Select a concluded Standard/MI model and matching SAT findings JSON in **4. Quality Impact Analysis**. The model/evidence viewer from QI-1 remains available; stage 2 is unaffected.
2. Pick an explicitly source-linked input node from the scenario selector (or select it on the primary graph), enter a **nonnegative integer** hypothetical SAT count, then choose **Set hypothetical count**.
3. The temporary table shows `baseline`, `hypothetical`, `Δ`, unit, exact identifiers, and evidence hash. The audit trail records every set/undo/reset with a monotonic revision and scenario identifier. **Undo last change** restores the preceding value; **Reset scenario** discards all hypothetical changes. Load a different model/evidence pair or clear the selection to discard this scenario.
4. Neither Standard quality values nor MI information shares are recalculated in QI-2. QI-3 will define the authentic Standard forward evaluation; later MI distribution reestimation has a separate explicit evidence/inference contract.

## API

The preexisting `GET /api/orchestration/code-analysis/quality-impact` and model `/select` responses now also carry an optional `scenario` (`pah.quality_impact_diagnostic_scenario@1`) and `scenarios_enabled` flag. The original network, probability backing, and acceptance payloads are unchanged.

`POST /api/orchestration/code-analysis/quality-impact/scenario` accepts:

```json
{"action":"set", "node_id":"CWE-79", "value":4, "expected_revision":0}
```

or `{"action":"undo","expected_revision":1}` or `{"action":"reset","expected_revision":2}`. The revision guards against stale browser edits. Errors return HTTP 409 with the reason; model and evidence integrity are verified again before any change. A modified original source invalidates the selection *and* its temporary scenario. No endpoint persists scenarios or allows edits to backing/latent/PF/TQI nodes.

In-memory scenarios disappear on process restart. This is deliberate; QI-4 may later add **explicit** export, clearly labeling hypothetical data rather than modifying original evidence. Verification uses the same pyPIQUE-owned concluded-model reader as QI-1.
