# PAH-MI-07 — instance-bound job and artifact references

**Scope:** PAH orchestration only. No module database, scientific data, or
module execution lifecycle is managed or inspected by these changes.

## Jobs

- Existing `JobMonitorAggregator.attach(reader)` and `/api/jobs/<owner>/...`
  remain valid for legacy module-name readers, including `WorkspaceJobReader`.
- `attach(reader, module_instance_id=opaque_id)` creates a PAH-only source alias
  so sibling module instances can both advertise jobs with the same producer
  module name. Snapshot/source/observation identities are keyed by this exact
  ID. The producer's registry remains unchanged. Output requests are routed
  to the exact attached reader and never search sibling sources.
- A runtime adapter may optionally publish `instance_job_readers() -> Mapping`
  of `module_instance_id` to read-only readers. Only IDs resolvable through
  PAH's own runtime registry are attached. Readers removed from that optional
  mapping are detached; other sources are not affected. No automatic process
  scanning, IPC inference, private database access, or job lifecycle control.
- A module that does not publish instance-aware telemetry is **not** assumed
  to have completed jobs. The legacy workspace snapshot monitor still works
  but may aggregate several producers under a module-level owner; it cannot
  prove individual instance ownership retroactively.

## Artifact publications

- Producer-authored artifact references remain immutable under the P5-05
  schema; the existing `host:module` identifier continues to work.
- A nonlegacy `module_instance_id` is accepted **only if** PAH has registered
  it under the same host instance, module type, workspace, and host project.
  PAH reads its own launch registry, not the module's underlying dataset/model.
- Status updates require the originating module-instance ID. Omitting it is
  compatible only with legacy `host:module` references; a sibling cannot
  mark another instance's artifact stale or withdrawn.
- The disposable SQLite reference index gains a nullable instance-ID column
  and optional `module_instance_id` filter for precise discovery. Existing
  index files are upgraded in place; the producer-authored JSON registry
  remains authoritative. Legacy artifacts have a null instance ID.

## Explicit handoffs

- `pah.uca-analysis-handoff@1` accepts an **optional** `module_instance_id`.
  When present, both the job source and a published artifact must belong to
  that exact instance. If a modern-instance artifact is submitted without
  this field, inspection refuses to infer its owner.
- Source SHA-256 is still producer-reported evidence; no host checksum is
  computed and job observation alone does not certify an artifact's contents.

## Limitations / next work

- **No automatic telemetry bridge** for already-running independent processes.
  A module or its public adapter must explicitly publish an instance-aware
  reader. MI-08 should verify browser flows with real installed adapters.
- Publication remains tied to the *currently selected* PAH workspace/context
  token. A background instance cannot publish to an inactive workspace via
  this HTTP API yet; a separate narrowly scoped capability contract is needed
  before permitting asynchronous cross-workspace writes.
- This patch does not authorize external file reads, move artifact bytes, or
  change the scientific meaning of jobs, models, or datasets.
