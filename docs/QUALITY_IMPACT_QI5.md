# QI-5 — Stable MI evidence / inference handoff

This stage prepares an **unexecuted** and reproducibly fingerprinted request for a separately owned MI distribution-reestimation provider. It does **not** attempt posterior-only fixed-PMI updates, model inference, retraining, probabilistic estimates, changes in signed PMI, new Product Factor information shares, or TQI calculations. A changed diagnostic count alone is not evidence of a new population distribution. The MI-U program must supply and validate the distribution-update procedure and the resulting statistics.

## Verified sources and schema

1. In Code Analysis Lab stage 4, select an MF-5 verified **MI-Informed PIQUE** conclusion and optional SAT JSON evidence. The latter is **required for this handoff**; only explicitly linked feature/CWE nodes with actually observed SAT records can be edited.
2. Create a local JSON document as shown below. Every digest is obtained from the *selected stage-4 snapshot*, not from an unverified path. The `backing_model_sha256` and `signed_network_sha256` match the bytes of the named verified MF-5 conclusion package members. The artifact's signed network and learned backing remain independent.
3. Declare a target inference provider's identity, version, capability, and owner. This is **not** confirmation of installed/connected/authenticated provider capabilities. The host does not fetch, execute, or search for a provider. Provider identity and claimed capability must eventually be verified by the actual inference owner, not assumed by PAH.
4. Bind the mapping using **Bind MI provider mapping** or `POST /api/orchestration/code-analysis/quality-impact/mi/adapter` with `{"path":"/absolute/mi_adapter.json"}`. The mapping is stored only in this workspace's memory; its local file is checked for modification on each snapshot. Binding never resets an existing QI-2 hypothetical scenario.
5. Make hypothetical edits and explicitly **Export unexecuted MI request**, or call `POST .../mi/prepare` with `{"expected_revision":N}`. It fails closed for stale revisions or any changed feature lacking a mapping. The returned `request` has schema `pah.mi_inference_request@1` and a deterministic SHA256 of its canonical JSON content (excluding `request_sha256`). No server file is written.

Sample **mapping** (substitute identifiers and digests from the actual verified network):

```json
{
  "schema": "pah.mi_inference_adapter", "schema_version": 1,
  "model_manifest_sha256": "<64-character hex>",
  "sat_evidence_sha256": "<64-character hex>",
  "signed_network_sha256": "<64-character hex>",
  "backing_model_sha256": "<64-character hex>",
  "provider": {
    "id": "hsqa_dbn", "version": "provider-defined-version",
    "capability": "mi.distribution_reestimation@1",
    "owner": "separate HSQA inference implementation"
  },
  "protocol": {
    "mode": "distribution_reestimation",
    "reference_population": "Explicitly identified research reference population",
    "conditioning_context": "Provider must specify a supported conditioning/reweighting procedure",
    "assumptions": "Hypothetical SAT counts only; estimator validity to be checked by provider"
  },
  "feature_mappings": [{
    "source_node_id": "feature:CWE-1", "backing_node_id": "CWE-1",
    "transformation": {
      "kind": "provider_defined", "source_unit": "matched_sat_finding_count",
      "target_unit": "provider-declared-event-unit",
      "target_event": "Explicit CWE-1 presence event or native feature definition",
      "provenance": "Operator-declared transformation; not applied or calibrated by PAH"
    }
  }]
}
```

A transformation is **descriptive metadata** awaiting independent provider implementation. PAH does not convert observed count changes into model-compatible feature values, even when mappings specify event names. A request contains baseline/hypothetical observed counts and deltas, declared source/target semantics, provider identity, model/network/backing fingerprints, selected evidence SHA256, scenario ID/revision and audit trail, and a documented list of limitations. The `estimation` object is explicitly unexecuted and contains null results.

## Failure and lifecycle controls

- Changed conclusion or SAT evidence invalidates the selected model and clears the scenario and adapter. Changed adapter bytes invalidate **only the adapter**, preserving the QI-2 scenario state. Rebinding requires explicit selection.
- The adapter refuses unsupported family, mismatched hashes, unknown source/backing nodes, duplicated mappings, ambiguous counts, unsupported fixed-PMI Mode A, missing event definitions, and invalid provider identity/capability. An unmapped edited node prevents request preparation.
- Requests are not cached or sent to a service; they are reconstructed from the latest verified selection on explicit request. No module-private database, source code, SAT evidence or concluded model is modified.
- `POST .../mi/clear` drops the mapping without changing the scenario. `GET .../quality-impact` includes `mi_handoff` status, never inferred results. QI-4 comparisons remain observation-only for MI.

## Deferred provider result acceptance

A provider must later define distribution/support semantics, feature/event transforms, estimators, provenance, numerical uncertainty and **separately verified** response schema before PAH accepts results. MI-U1–MI-U7 will implement and test this boundary. QI-5 deliberately neither accepts unverifiable numeric responses nor presents provider-declared estimates as authoritative changes to a learned model. The presence of `request_sha256` is an integrity/lineage convenience, **not** a cryptographic signature or scientific validation.
