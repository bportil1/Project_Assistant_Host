# MI-03 — Generic independent module processes

## Ownership boundary

PAH now exposes a generic local OS-process supervisor through
`pah.module_processes.ModuleProcessLauncher` and through
`RuntimeRegistry.launch_process(module_id, argv, ...)` /
`RuntimeRegistry.stop_process(module_instance_id, ...)`.

The launcher does **not** know a module's datasets, model identifiers, papers,
source tree structure, or private persistence APIs. A trusted module adapter
must supply an executable and argv list. **Never expose that raw argv surface to
untrusted HTTP clients.** The older `RuntimeRegistry.launch()` method and hosted
surface adapters retain their behavior in MI-03; MI-04 will add instance routing
and MI-05 will migrate old hosted integrations.

## Instance contract

For every successful launch PAH assigns:

- A unique opaque module-instance ID (`host_instance_id:module_id:uuid`).
- An independent *OS process*, with its own process group on POSIX systems.
- A private working directory by default:
  `<state_dir>/runtime/<host_id>/modules/<uuid>/`.
- Private `logs/process.log`, `tmp/`, and `cache/` under that directory.
- A distinct, **best-effort** available local TCP port by default; use
  `requested_port=None` for non-server modules.
- Environment variables `PAH_MODULE_ID`, `PAH_MODULE_INSTANCE_ID`,
  `PAH_HOST_INSTANCE_ID`, `PAH_MODULE_RUNTIME_DIR`, `PAH_MODULE_LOG_DIR`,
  `PAH_MODULE_TMP_DIR`, `PAH_MODULE_CACHE_DIR`, `PAH_MODULE_HOST`, and (when
  assigned) `PAH_MODULE_PORT`. `PAH_WORKSPACE_ID` is supplied only if explicitly
  provided to the launcher. Standard `TMPDIR`, `TMP`, `TEMP` point to private
  scratch space.
- A process-owned registration in `InstanceRuntime.module_instances()`.

A module must read the assigned port and bind it promptly, rather than use a
hardcoded listener port, to realize independent network services. Port selection
checks other known live PAH hosts and running child records, but cannot eliminate
the OS-level bind race without the module accepting an inherited listener socket
or confirming its bound address. Those mechanisms require a public module
contract and are not claimed in MI-03. `cwd=` is available for programs that
require a particular startup directory; using it may reintroduce relative-path
output collisions, so modules should write volatile outputs to their assigned
runtime directory. Scientific project storage remains wholly module-owned.

## Lifecycle and failure behavior

`stop_process(id)` accepts only an instance started by **the same local launcher**.
It uses the retained process handle and a process group signal (POSIX), not an
arbitrary PID from a JSON registry. Stopping one child cannot signal siblings.
`stop_all()` is included in `RuntimeRegistry.shutdown_all()`, so PAH's existing
host shutdown path cleans up children it spawned. Unexpectedly exited child
registrations are reaped before `RuntimeRegistry.instances()` is read; logs are
preserved. This does not provide process reattachment after a PAH crash; PAH
crash/recovery policy remains future work.

Generic processes should remain in the foreground (not daemonize out of their
launched process group) for PAH to supervise them reliably. PAH does not
silently kill unrelated processes based on stale PID metadata.

## Validation

`tests/test_mi03_module_process_launcher.py` launches real Python subprocesses
locally (no module dependencies or remote calls). It verifies independent IDs,
PIDs, runtime paths, logs, ports, targeted stop, isolation across two PAH hosts,
reaping, and failure handling.

To test locally:

```sh
PYTHONPATH=. pytest -q tests/test_mi03_module_process_launcher.py tests/test_instance_runtime.py tests/test_runtime_registry.py
```
