# QI-4 — Comparisons, recorded path explanation, and deliberate export

Applies after QI-1, QI-2, and QI-3. Code Analysis Lab stage 4 remains separate
from stage 2. pyPIQUE concluded versions and SAT source evidence remain read-only.

## Comparison contract

- `pah.quality_impact_comparison@1` is attached to the verified stage-4 snapshot.
  Its reference is either the untouched observation/native baseline or an
  explicitly captured **in-memory** checkpoint of the *same* scenario/model/evidence.
- `observations`: reference, current scenario, and delta in **matched SAT finding
  count** units. Unobserved diagnostics are never filled with inferred zeroes.
- `native_values`: only when both states have a completed authentic Standard
  PIQUE forward result with matching model, evidence, and native-input mapping
  fingerprints. Includes diagnostics, measures, Product Factors, Quality
  Aspects, and TQI. Value deltas come from native pyPIQUE evaluators and are
  never computed by SAT count substitution.
- If the native mapping is missing, has changed, or lacks the declared count-to-
  native conversion, comparison retains observation counts and **omits native
  deltas**. An MI concluded model has no native Standard comparison in QI-4.
- `network_highlights` identifies the *recorded* directed edges reachable
  from edited observed input nodes. This is structural context, **not a causal
  effect** or evidence that each reachable value changed. Separately highlighted
  native changed nodes are grounded in two completed native evaluations.
  Probabilistic backing edges are never merged with signed MI edges.

## In-memory checkpoints and version lineage

1. Bind a verified finalized package and optional SAT findings as in QI-1;
   bind a complete native mapping as in QI-3 if numerical Standard results
   are needed.
2. Apply QI-2 hypothetical edits; click **Capture in-memory checkpoint** to
   preserve that revision's observed counts and any native result.
3. Choose another checkpoint or the baseline and click **Compare**.
   Undo/reset may be used at any time; checkpoints are not persisted.
4. Remove checkpoints explicitly. Up to 12 checkpoints per workspace/model/
   evidence session are retained. Changing the selected source or evidence
   invalidates and clears all checkpoints. Changing a native input mapping
   never authorizes a comparison of incompatible native values.

`POST /api/orchestration/code-analysis/quality-impact/comparison` takes
`{"action":"capture","label":"...","expected_revision":N}` or
`{"action":"select"|"remove","checkpoint_id":"...","expected_revision":N}`.
Use `checkpoint_id="baseline"` to return to the baseline. Revision checks
reject stale requests and workspace keys isolate sessions.

## Optional, explicit local JSON export

`POST /api/orchestration/code-analysis/quality-impact/export` with
`{"expected_revision":N}` returns a `pah.quality_impact_scenario_report@1`
containing concluded model and evidence fingerprints, scenario lineage/history,
original SAT observation comparisons, native results (only when available),
and graph context. The stage-4 **Export explicit JSON report** button generates
and downloads this report locally in the browser. Export performs no server-side
write, no automatic saving, no source-code patching, and no analyzer rerun.

This is a **hypothetical** scenario report. Native numerical differences do not
establish real source-code repair. Verifying a remediation requires isolated
code changes and actual analyzer/test re-execution in a later sprint.
