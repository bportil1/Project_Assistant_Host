# MI-U1 — Evidence, event and population contract (Option B only)

This sprint defines the **inputs and interpretation of a possible future updated distribution**. It does not implement an inference estimator, reweight a cohort, resample data, recompute joints/marginals or PMI, train/retrain an RBM, change Product Factors/TQI, or provide an interactive graph. Those belong to MI-U2–MI-U5 and IG-1–IG-5 respectively. No alteration to Standard or current MI model computations is made.

## The verified references

Call `pique_py.mi_update_contract.build_mi_u1_contract(conclusion_path=..., specification=..., pah_request=...)` or:

```sh
python -m pique_py.mi_update_contract /absolute/concluded_mi.zip /absolute/mi_u1_spec.json --output /absolute/mi_u1_validated.json
```

`--output` is optional: without it the contract is printed to stdout. An existing output file is never overwritten. This does not require PAH; the optional `--pah-request` reads a QI-5 `pah.mi_inference_request@1` that must match the concluded model and mapped changed counts exactly. This is local file validation; no provider is invoked.

The `specification` JSON (schema `pypique.mi_update.evidence_spec`, schema_version 1) must provide:

- `model.version_id`, `model.manifest_sha256`, `model.archive_sha256`: taken from the *verified* MF-5 concluded MI ZIP/folder. The output binds the original signed topology and learned backing file hashes independently. These identify integrity, not authorship.
- `model_compatibility.rbm_family` (one of `bernoulli`, `gaussian`, `student_t`) and `latent_depth` (positive integer). These must agree with available learned metadata/latent indices. If the backing artifact omits the family or layer indices, the reported compatibility is **operator-declared / unverified**, not inferred from a UI label. Optional checkpoint SHA256 is a declaration, not proof the checkpoint was loaded.
- `reference_population`: distinct cohort `id`, reference dataset `snapshot_sha256`, positive `sample_count`, `sampling_unit: "project"`, `sampling_frame`, `cohort_rule` and `data_origin`. A target project's findings alone cannot be labeled the training/reference population. A supplied hash or sample count is metadata, *not* proof of data availability, actual sample support or overlap.
- `distribution.mode`: **`reference_conditioning`, `reference_reweighting`, or `declared_distributional_scenario`**. Supply explicit `conditioning_variables` (backing feature IDs; may be empty except for reference conditioning), `target_population`, `estimand` and `assumptions`. Fixed-reference-PMI posterior-only Mode A is rejected. The semantics of these three modes are declarations for MI-U2 protocol selection; no estimator is activated by choosing one.
- `features`: explicitly mapped `diagnostic_node_id` from the signed topology, `measure_id` from the information model, and the equivalent observable `backing_node_id`; `source_unit` (`matched_sat_finding_count` or `native_value`), `transform`, `event`, `missingness`, and both `baseline`/`hypothetical` values. Duplicate target bindings and ambiguous CWE identities are rejected.

**Supported event definitions in U1:** Bernoulli count input may use `{ "kind": "presence_threshold", "threshold": 1 }` with `{ "kind": "binary_presence", "positive_state": 1, "negative_state": 0 }`. Continuous native input can use `{ "kind": "identity" }` with `{ "kind": "numeric_interval", "lower": 0, "upper": 1, "unit": "normalized_feature" }`. A numeric interval describes an *event* for later probability estimation; U1 computes no event probability. Other transforms/families need explicit future versioning, not guessed mappings.

Missingness is always `{ "policy": "mask_and_exclude", "mask_field": "observed" }`. Baseline and hypothetical values have objects `{ "observed": true, "value": 5 }`, or `{ "observed": false, "value": null }`. Missing is not zero; it cannot be silently imputed into a vulnerability absence. A contract contains original *and* hypothetical values for comparison; neither is an intervention/cause claim.

## Minimal example shape

This is an **illustrative form only**, not a runnable sample without matching a concluded model and its hashes/feature names:

```json
{
  "schema": "pypique.mi_update.evidence_spec", "schema_version": 1,
  "model": {"version_id": "<concluded-version>", "manifest_sha256": "<sha256>", "archive_sha256": "<sha256>"},
  "model_compatibility": {"rbm_family": "bernoulli", "latent_depth": 1},
  "reference_population": {
    "id": "benchmark-v1", "snapshot_sha256": "<sha256>", "sample_count": 527,
    "sampling_unit": "project", "sampling_frame": "defined benchmark cohort",
    "cohort_rule": "explicit project inclusion rule", "data_origin": "benchmark_reference"
  },
  "distribution": {
    "mode": "reference_conditioning", "conditioning_variables": ["CWE-79"],
    "estimand": "reference population under declared conditioning events",
    "target_population": "benchmark-compatible projects",
    "assumptions": "overlap and sufficient conditioning support must be verified"
  },
  "features": [{
    "diagnostic_node_id": "feature:CWE-79", "measure_id": "CWE-79", "backing_node_id": "CWE-79",
    "source_unit": "matched_sat_finding_count", "transform": {"kind": "presence_threshold", "threshold": 1},
    "event": {"kind": "binary_presence", "positive_state": 1, "negative_state": 0},
    "missingness": {"policy": "mask_and_exclude", "mask_field": "observed"},
    "baseline": {"observed": true, "value": 4}, "hypothetical": {"observed": true, "value": 0}
  }]
}
```

## Acceptance / scientific limits

The returned immutable-value contract is `pypique.mi_update.evidence_contract@1` with a reproducible `contract_sha256`. It sets `execution.status = contract_only_not_executed` and all updated probability, PMI, and score slots to **null**. `identifiability.status = not_established` even for valid declared cohorts: U2 must inspect real reference samples, missingness, support/overlap, checkpoint and estimator assumptions before any updated distribution is identifiable. The model's learned weights and prior signed edges are **not** changed by these U1 declarations. Do not interpret a changed project count as newly learned population PMI, a causal intervention, or a guaranteed PF/TQI improvement.

No PAH, source-code analysis, SAT run, external service or repository connector is required to use U1 locally. Planned Phase 4 is a later standalone **interactive concluded-model graph**; integration with source code and PAH is separate future work.
