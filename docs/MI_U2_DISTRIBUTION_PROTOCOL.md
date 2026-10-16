# MI-U2 — Valid reference-distribution update protocol (Option B)

MI-U2 estimates **empirical event probabilities over explicit project-level reference data**. It consumes the *unchanged* MF-5 concluded MI ZIP/folder and a fingerprinted MI-U1 evidence contract. It **does not** re-train the learned RBM, reestimate its latent probabilities, recompute PMI, information attribution, PF or TQI, or make causal claims. Those are separate later sprints and require further model support. The concluded model is read-only.

## Local CLI

```sh
python -m pique_py.mi_distribution_update CONCLUDED_MI.zip MI_U1_CONTRACT.json REFERENCE_DATASET.json MI_U2_PROTOCOL.json --output MI_U2_ESTIMATE.json
```

Without `--output`, prints JSON to stdout; with `--output`, the path must not already exist. For `declared_distributional_scenario`, add `--scenario-dataset SECOND_COHORT.json`. No network or PAH dependency is used. Python API: `estimate_mi_u2_distribution(conclusion_path=..., contract=..., reference_dataset=..., protocol=..., scenario_dataset=None)`.

## Reference dataset schema

`pypique.mi_update.reference_dataset@1`, canonical JSON SHA256 (computed using `pique_py.research_models.canonical_sha256(data)`) must equal the MI-U1 `reference_population.snapshot_sha256` and its row count, ID, unit and origin must match. The expected shape is:

```json
{
  "schema": "pypique.mi_update.reference_dataset", "schema_version": 1,
  "population_id": "benchmark-ref-v1", "sampling_unit": "project",
  "data_origin": "benchmark_reference",
  "rows": [
    {"project_id": "repo-1", "base_weight": 1,
     "features": {
        "CWE-79": {"observed": true, "value": 3},
        "CWE-89": {"observed": false, "value": null}
     }
    }
  ]
}
```

This is a **shape illustration**, not a viable reference cohort. Every project supplies every mapped feature's observed flag and original *count or native value*, using the **exact recorded backing-node ID** from MI-U1. `observed=false` must have `value=null`; missing data are never treated as zero. All mapped features must be present/observed to enter the common complete-case estimation cohort; exclusions are reported. Each project ID must be unique; optional `base_weight` must be strictly positive. The reported support reflects complete cases after masking and conditioning. A target project by itself is not an empirical reference population.

## Protocol and three explicitly distinguished methods

At minimum, create this JSON:

```json
{
  "schema": "pypique.mi_update.estimation_protocol", "schema_version": 1,
  "min_complete_cases": 5, "min_effective_sample_size": 5
}
```

Both thresholds default to 5; accepted values must be at least 2. These are **minimal software guards, not guarantees of statistical precision**. All probabilities use the same cohort and same normalized weights; marginal probabilities are directly consistent with the reported 2x2 event joint tables.

- **`reference_conditioning`**: Uses the MI-U1 conditioning variables and their **baseline/hypothetical observed event states** to select two supported subpopulations of the existing reference cohort. For a count-to-presence change, this can simply compare projects with versus without that CWE event; it is *not* evidence that modifying the target project changed population rates. The event states must actually differ and each selected subpopulation must have adequate support.
- **`reference_reweighting`**: Starts with the complete-case reference cohort. Requires a **separately justified, explicit population-level target** `"target_event_prevalences": {"CWE-79": 0.2}` for one or more actually modified mapped features. This target is **not derived automatically from a hypothetical single-project count**. Uses positive-weight iterative proportional fitting (raking) with optional `max_iterations` (default 500, ceiling 5000) and `tolerance` (default `1e-8`). If either event state is unavailable, constraints do not converge, or effective sample support falls below the declared threshold, the update fails. The baseline remains the observed weighted reference distribution.
- **`declared_distributional_scenario`**: Requires a separately supplied project cohort with a different population ID/data-origin, and rejects using the identical dataset as a new scenario. This compares observed declared cohorts; it does not represent an intervention or a generated population shift. Use `--scenario-dataset` and no `target_event_prevalences`.

The same MI-U1 transform defines each project's binary *event indicator*: `presence_threshold` on nonnegative integer counts or `identity` with a finite half-open numeric interval. This is an empirical **event-probability** estimator, not a general continuous Gaussian/Student-t density estimator. Family declarations from U1 remain declarations; this sprint does not load or execute a learned RBM checkpoint.

## Result, traceability and limitations

`pypique.mi_update.distribution_estimate@1` includes source hashes, model topology/backing fingerprints, the MI-U1 contract hash, the estimator-protocol hash, sample counts, excluded masked rows, per-side effective sample size, event marginals `event_true`/`event_false`, and all mapped-feature pairwise joint cells `00`/`01`/`10`/`11`. A top-level `result_sha256` fingerprints the result. Zero empirical probabilities remain **exact zeros**; PMI log-domain smoothing and uncertainty are deferred to MI-U3/MI-U7 and cannot be silently assumed here.

Reweighting may have a low effective sample size even with many original rows. Successful calculation establishes *numerical event estimates conditional on the supplied data and assumptions*, not external validity, causal identification, calibrated learned-model posteriors or a new quality score. Latent relationships from the concluded model are preserved, not reestimated; these event tables cannot by themselves support updated latent PMI/PF values. The result explicitly sets all such future fields to `null`.

## Failure modes and resource guards

Rejects fingerprint mismatches (including changed reference content), invalid events or project IDs, missing-as-zero, incompatible model family or version, empty conditioning arms, unsupported reweighting targets, insufficient complete cases/effective sample size, impossible/unconverged constraints and incompatible independent cohorts. Currently limited to **256 mapped features and 100,000 project rows** because output includes all pairwise 2×2 tables. Result fingerprints ensure reproducibility, not authenticity or privacy of the originating data. Users must supply data rights and representative-cohort assumptions independently.
