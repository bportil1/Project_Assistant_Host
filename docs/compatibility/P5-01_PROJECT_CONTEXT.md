# P5-01 — PAH project, module-instance, and hosted-context contract

**Scope:** PAH-only additive change. Scientific engines, independent module
launchers, job semantics, artifact schemas, database ownership, and the JSON
workspace catalog are unchanged. P5-00 is the required patch baseline.

## Identities and ownership

| Identity | Source | Meaning | Persistence |
| --- | --- | --- | --- |
| `workspace_id` | `WorkspaceManager` | Logical PAH research workspace selected by this process | Workspace catalog (JSON); selected per instance |
| `host_project_id` | Canonical repository resource path | Existing PAH artifact/project scope identity; `null` when no repository is bound | Derived; never an implicit module-local database ID |
| `instance_id` | `InstanceRuntime` | Independently launched PAH host instance | Instance-local runtime metadata |
| `module_id` | Module manifest/adapter | Scientific module or host-surface identity | Module registry |
| `module_instance_id` | `<host instance_id>:<module_id>` | Module **slot** in this host instance, not a run or child PID | Host runtime record |
| `module_local_project_id` | Optional explicit adapter input | Module-owned experiment/project identity when known | Module-owned; **never inferred** from a PAH path |
| `context_token` | `WorkspaceContextGuard` | Ephemeral optimistic concurrency token for one active context selection | In-memory only; changes when active scope changes |

`ModuleContext.for_module(module_id, local_project_id=...)` returns an
immutable module-bound context. It does not alter the caller's base context.
Older adapters can continue consuming `project_root`, `workspace_id`,
`resources`, `ports`, and `runtime["instance_id"]`. New fields are additive.

PAH never opens or writes a submodule's private SQLite database as a result of
this contract. `project_root` and resource roles remain canonical paths.

## Change detection and stale requests

The host captures its active workspace ID, canonical repository root, resource
bindings, and enabled-module profile. A change in any of these rotates the
context token and increments an instance-local revision. A modification to an
**inactive** workspace leaves the active token unchanged.

`GET /api/orchestration/context` returns the active selection. The module
profile at `GET /api/orchestration/modules` also includes `context_token`,
`context_revision`, and `host_project_id` for the browser to carry forward.

Mutating `/api/orchestration/*` requests may send an
`X-PAH-Context-Token` header. If the token is stale, PAH returns **409** with
a refresh message **before** entering the route. The PAH browser supplies
this header automatically on all orchestration mutations. Legacy clients
without this header remain supported (and do not obtain stale-selection
protection); they should opt in when they gain a persistent selection view.

The token is **not authentication**, a secret authorization capability, or a
cross-process distributed lock. It only prevents accidental use of a stale
selection from the same PAH instance. PAH's existing validation and project
containment checks remain necessary. This sprint does not solve concurrent
long-running execution races; later artifact/job sprints own those contracts.

## Project switching and hosted modules

- PAH still uses `WorkspaceManager` to bind roots and enabled modules.
- PAH-owned hosted Code Analyzer/Document/Reference surfaces keep their
  existing launch modes and workspace rebinding behavior.
- Registered scientific adapters receive `ModuleContext` with explicit
  host scope, module ID, and module slot ID at launch/status/artifact discovery.
- `InstanceRuntime` records that scope in launched module metadata for
  diagnostics and future stale-instance reconciliation.
- There is no automatic shutdown, migration, or state replacement in a
  scientific module simply because PAH switched projects.
- Parent/child artifacts, job observations, and SQLite caches are addressed
  in P5-05/P5-06 and individual producer migrations, not this patch.

## Regression and rollback

Tests cover logical workspaces sharing a physical root, differing repository
roots, resource/profile changes, two independent host instances, module slot
identity, optional module-local IDs, and stale launch rejection. Flask route
coverage is optional when Flask is not installed; it must not be reported as
browser-tested when skipped.

Rollback: revert P5-01 files/hunks; no data or database schema changes are
needed. If a consuming browser is older, omission of the optional token
header preserves existing behavior.
