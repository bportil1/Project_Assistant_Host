# MI-U3 — Signed event PMI and information recalculation (Option B)

MI-U3 consumes the immutable concluded MI model (via MF-5 verification), its MI-U1 evidence/event contract and the **complete, fingerprinted** MI-U2 empirical joint/marginal estimate. It validates provenance and every binary pair table before producing *new, separate* information records. The finalized signed-information topology and learned probabilistic backing are not changed, and this is **not** an RBM posterior inference/retraining service.

## CLI and Python API

```sh
python -m pique_py.mi_information_update CONCLUDED_MI.zip MI_U1_CONTRACT.json MI_U2_ESTIMATE.json MI_U3_POLICY.json --output MI_U3_RESULT.json
```

Without `--output`, prints JSON; an existing destination cannot be overwritten. Python API: `recalculate_mi_u3_information(conclusion_path=..., contract=..., distribution_estimate=..., policy=...)`.

Minimum policy:

```json
{"schema":"pypique.mi_update.information_policy","schema_version":1,
 "zero_probability_policy":"undefined","min_effective_cell_mass":5}
```

Optionally set `zero_probability_policy` to `uniform_joint_mixture` and `uniform_mixture_strength` to an explicit float strictly between 0 and 1 (e.g. 0.02). That separately reports sensitivity to convex joint mixing: `p_regularized(x,y) = (1-lambda)*p_raw(x,y) + lambda/4`, with **marginals derived from the same regularized joint**. This is an explicitly labeled regularization sensitivity analysis, not a posterior, pseudocount prior, trained RBM update or change to original MI-U2 frequencies. No smoothing is applied by default.

## Definition and units

For a binary event pair `(A,B)` and each state combination `ab` in `00`, `01`, `10`, `11`, with MI-U2's shared complete-case weighted cohort:

- **Raw signed pointwise mutual information**: `PMI(a,b) = ln[P(A=a,B=b)/(P(A=a)P(B=b))]`, in natural-log nats. PMI can be positive or negative and is **not** mutual information itself. For exact zero joint mass, its value and normalized value are `null` with status `undefined_zero_joint`; zero cells contribute exactly zero to mutual information. A deterministic joint with probability one has PMI = 0 and normalized PMI = 0 by limit.
- **Normalized pointwise PMI (NPMI)**: `PMI(a,b)/(-ln(P(A=a,B=b)))` for nonzero, nondeterministic joint mass. This is the specifically defined event-level NPMI, bounded to [-1,1]. It is **not automatically the same quantity** as existing HSQA signed network-edge weights or any model-specific normalized joint index.
- **Mutual information**: `MI(A;B) = sum_ab P(A=a,B=b) * PMI(a,b)` over states with positive joint mass. It is nonnegative, in nats, and never signed by a correlation coefficient.

Outputs retain the original event marginals, source pairing, support metadata, signed per-state PMI and NPMI, unsigned mutual information, and optional regularized counterparts. Delta records compare corresponding baseline and scenario events *only when both PMIs are defined*; otherwise the signed delta is `null`. A change in information is associative, not evidence of intervention effects.

`standardized_pmi`, `normalized_joint_index_score`, updated learned RBM weights, latent/PF attribution and PF/TQI are explicitly **not calculated**. This avoids fabricating an HSQA normalization from empirically defined binary events. MI-U4 must establish the validated mapping to the recorded latent information network before updated PF attribution is possible.

## Integrity, zeros and uncertainty

Rejects altered MI-U2 digests; mismatched MI-U1/model identities; invalid MI-U2 mode/status; inconsistent, missing, duplicate, reversed or out-of-bounds joint tables; inconsistent marginals; absent support; already smoothed input; and non-finite values. Source snapshots are fingerprinted, not authenticated: regenerating a digest for substituted data can defeat tamper-evidence, so source custody remains a caller responsibility. All files are read-only except an explicitly chosen new result path.

Reported `effective_cell_mass_proxy = MI-U2 effective_sample_size * P(cell)` is a **descriptive rarity check** (low if below configurable threshold). It is not the number of observed independent cell instances and must not be used as a calibrated confidence interval. An MI-U2 aggregate does not retain project-level sampling/bootstrap information, so confidence/credible intervals are `null` and deferred to MI-U7. Conditioning and prevalence-reweighting assumptions remain those declared and checked in MI-U1/MI-U2. No automatic single-project-to-population conversion or causal claim is made.
