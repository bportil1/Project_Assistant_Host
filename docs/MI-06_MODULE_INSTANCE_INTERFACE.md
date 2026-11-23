# PAH-MI-06 — Generic module-instance UI

PAH can now list and manage instances started by its process supervisor. The top-bar **Instances** dialog lists IDs, original workspace bindings, process IDs, local ports, and independent shutdown controls. Instances that do not have a PAH-owned child process are read-only. A UI **Open window** action exists only when a process adapter explicitly declares a browser UI path.

## Optional module runtime adapter contract

A trusted installed `pah.runtimes` adapter may add:

```python
# On the adapter itself (server-side only)
def process_launch_spec(self, *, context):
    return {
        "command": ["/absolute/path/to/executable", "--listen-from-env"],
        "cwd": "/existing/working/directory",  # optional
        "env": {},                           # optional string-string overrides
        "requested_port": 0,                 # optional: 0 allocates; None = headless
        "ui_path": "/",                      # optional, omit for headless processes
    }
```

`command` comes **only from the trusted adapter**; the browser API `POST /api/orchestration/modules/<module_id>/instances` accepts **no arguments**. For each launch, the host assigns a unique instance ID, temporary/cache/log directory, and port when requested. The adapter's executable must respect `PAH_MODULE_INSTANCE_ID`, `PAH_MODULE_RUNTIME_DIR`, and `PAH_MODULE_PORT` as appropriate. An advertised `ui_path` must be a local absolute path and is exposed on loopback only.

Existing `launch()` and `status()` remain unchanged and must not be repurposed. A module without `process_launch_spec` cannot be launched independently through MI-06; its legacy UI remains available and is clearly labeled. No submodule project logic is moved into PAH.

**Limitations:** This patch does not retrofit module entry points, establish HTTP readiness, verify submodule data isolation, attach scientific jobs, or promise to restore children following a PAH crash. The process-level feature is available when module adapters opt in. Module compatibility reviews follow MI-08.

## Local test plan

- Launch two opt-in dummy module processes and verify distinct IDs, PIDs, workspace contexts, and runtime paths.
- Stop the first and assert the second stays registered and alive.
- Verify non-opt-in modules cannot be launched via the new endpoint.
- Verify HTTP callers cannot supply command, port, paths, or environment values.
- Verify unexpected/unknown instance IDs do not redirect to another instance.
- Verify legacy slots are listed but cannot be stopped through process-only controls.
