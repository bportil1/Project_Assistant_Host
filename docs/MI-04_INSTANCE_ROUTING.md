# MI-04 — Explicit module-instance routing and immutable launch context

## Responsibility boundary

PAH remains an orchestrator, **not** a dataset, SQA model, or document-project
manager. MI-04 adds a generic instance directory and instance-ID-based stop
operation, and captures the context supplied by a trusted module launch adapter.
No domain-specific module code is imported, called, or modified.

## Runtime API

- `RuntimeRegistry.launch_process(module_id, argv, context=..., ...)` records the
  launch-time workspace identity and host project identity. An explicitly
  selected module instance ID is honored; a host-level legacy `host:module`
  context identity continues to generate fresh child instance IDs.
- `route_instance(id, module_id=None)` resolves exactly one instance registered
  with this host. If the module type is supplied, a mismatch raises an error;
  PAH never guesses a sibling or falls back to `module_id`.
- `instance_context(id)` returns a **copy** of the launch-time `ModuleContext`
  when the trusted caller supplied one. It does not read or rebind the current
  PAH workspace. For argv-only or older hosted launches, no invented full
  context is returned.
- `stop_process(id)` verifies PAH still owns a live child process handle, and
  only then terminates that exact child. A legacy type-level adapter record is
  not treated as authority to signal the recorded PID.
- `launch/status/shutdown/artifacts(module_id, context)` remain the compatibility
  surface for single-instance adapters but now reject a context explicitly
  addressed to a *different* module-instance ID.

## Local controller routes

- `GET /api/orchestration/instances`
- `GET /api/orchestration/instances/<module_instance_id>`
- `POST /api/orchestration/instances/<module_instance_id>/shutdown`

Only sanitized routing metadata (identity, owning host, original workspace,
process ID, endpoint **port hint**, log path, ownership and lifecycle) is
returned; the route does not expose arbitrary argv or environment variables.
The port hint is **not** proof the child HTTP listener is ready. MI-04 deliberately
adds no raw command-execution endpoint, reverse proxy, or generic scientific
operation API. Concrete adapter UI calls and legacy host migration remain MI-05;
instance selection UX remains MI-06.

Explicit instance shutdown is independent of PAH's active-workspace token;
requiring the *new* workspace token would make it impossible to stop an
already-open child from an earlier workspace. Local access to PAH's control
API still needs to be trusted and should not be exposed to untrusted networks.

## Remaining limitations

- Host workspace switching still rebinds **legacy hosted surfaces** in
  `pah/app.py` and `pah/full_tools.py`. MI-05 addresses those integrations.
- An OS process isolates volatile memory but cannot prevent a module from
  writing to a shared hardcoded path. PAH's assigned paths and published
  launch contract are the boundary, not a guarantee about module internals.
- No automatic process reattachment or listener readiness checks are included.

## Local tests

```sh
PYTHONPATH=. pytest -q tests/test_mi04_instance_routing.py tests/test_mi03_module_process_launcher.py tests/test_instance_runtime.py tests/test_runtime_registry.py tests/test_p5_01_context_contract.py
```
