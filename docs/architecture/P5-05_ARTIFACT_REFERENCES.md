# P5-05 — Published artifact references and rebuildable lookup

## Purpose and authority

PAH mediates *references* to produced scientific and source-analysis artifacts.
It does not own the underlying data, model weights, source files, or producer
SQLite catalogs. Existing `ArtifactRegistry` JSON snapshots and PAH input
selections remain the authoritative host mediation record. A separate SQLite
file at `<instance runtime>/artifact-references.sqlite3` is a disposable
search index derived from that JSON registry, not a second writable catalog.

This patch adds a new **opt-in** publication contract. Existing
`/api/orchestration/artifacts` routes, provider `register_current()` logic,
legacy alias/history behavior, and JSON workspace preferences are retained.
No existing producer needs to migrate in this patch. In subsequent sprints,
producer adapters can publish references through this contract one at a time.

## Versioned contract

`POST /api/orchestration/artifact-references`

The request JSON must contain `schema = "pah.published-artifact-reference"`,
`schema_version = 1`, `revision` (positive integer), a fully scoped `context`,
and an existing `ArtifactRef`-shaped `artifact` object:

```json
{
  "schema": "pah.published-artifact-reference",
  "schema_version": 1,
  "revision": 1,
  "source_fingerprint": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "context": {
    "instance_id": "host-instance",
    "workspace_id": "research-a",
    "host_project_id": "/absolute/path/to/selected/repository",
    "module_id": "pypique",
    "module_instance_id": "host-instance:pypique",
    "module_local_project_id": "optional-module-run",
    "context_token": "token-from-current-orchestration-context"
  },
  "artifact": {
    "artifact_id": "pypique-evidence-run-1",
    "kind": "sat_result",
    "producer_module": "pypique",
    "project_id": "/absolute/path/to/selected/repository",
    "schema_id": "pypique.sat.evidence",
    "schema_version": "1",
    "validation_state": "valid",
    "capabilities": ["sat_evidence"],
    "location": "/path/owned/by/producer/evidence.json"
  }
}
```

Get the current identities and context token from
`GET /api/orchestration/context`. The project ID must match that *active*
selection exactly, and the module must be registered with PAH. A stale
workspace token or foreign module/project identity is rejected. Do not infer a
module-local project ID from a PAH workspace. The `ArtifactRef` schema remains
unchanged so existing adapters and consumers do not need a parallel DTO.

**Immutable identity:** Repeating an identical publication returns 200 and
preserves its recorded state. Publishing different data under an existing
`artifact_id` returns 409; use a new ID for a new version. Producer `metadata`
may not spoof PAH alias, snapshot, archive or publication-control fields.

**Source hashes are producer claims, not host verification.** PAH does not
open the indicated path, compute its contents, or treat the source fingerprint
as a permission to open the file. This is a loopback/local orchestration
contract, **not an authentication mechanism**. The context token guards
against stale selections; it is not a security credential. Future networked
producer publication requires a separate trusted producer-authentication
boundary.

## Producer-observed status

`POST /api/orchestration/artifact-references/<artifact_id>/status`

Send `{"module_id": "pypique", "context_token": "...", "state":
"stale", "reason": "input changed"}`. Allowed states are `active`, `stale`,
`missing`, and `withdrawn`. Only the originating module in the matching active
workspace/project can publish the observation. The reference remains in the
host registry and is not falsely deleted from history. A repeated publication
does not automatically reverse a reported stale/missing/withdrawn status.
This status is also **producer reported**, not PAH's filesystem inspection.
Older artifacts without a publication contract have state `unverified` in the
new index.

## Host-owned read-only index

`GET /api/orchestration/artifact-references`

Returns only references from the **currently selected PAH project**. Published
references are additionally restricted to their originating workspace; older
`ArtifactRef` entries without workspace metadata remain scoped by project ID.
No query parameter can override the active project. Supported filters are:

- `kind`, `producer_module`, `schema_id`, `capability`, `search`;
- `include_history=true`, `include_aliases=true` (default false);
- `limit` (1–100, default 50) and `offset` (0–100000, default 0).

Results contain reference identity and metadata, publication revision,
producer-reported status and a total count. **Results do not contain raw file
bytes, producer database rows, or downloadable filesystem URLs.** A caller
must use an authorized producer/module interface to resolve actual content.

The index is rebuilt from the JSON registry on startup and refreshed after
artifact-registry changes. Deleting the SQLite file and restarting PAH is a
safe rollback path; JSON artifacts/history and workspace configurations are
untouched. PAH does not migrate or inspect private pyPIQUE, HSQA_DBN, ML_Lab,
or Code Analyzer SQLite databases.

## Validation and scope

Tests cover schema/version rejection, immutable IDs, stale workspace/project
and producer mismatch, reserved metadata, foreign parent artifacts, paged
search, escaped SQL LIKE input, historical alias selection, index rebuild,
JSON round-trip, and explicit stale/withdrawn observations. Flask route tests
are optional and skipped if Flask is not installed locally.

**Not included:** producer-side publication migrations, remote artifact
download/resolution, automatic file-integrity rechecking, durable job states,
or centralized scientific result storage. These are separate contracts or
later sprints.
