# MI-02 — Module instance identity and runtime output hygiene

PAH maintains two separate registries:

- `RuntimeRegistry` (`module_id` → adapter) discovers **module types**. There is
  only one adapter registration per type, regardless of how many processes run.
- `InstanceRuntime.module_instances()` (`module_instance_id` → registration)
  records **running module instances** inside one PAH host instance. Every
  entry records its module type, process ID when available, owning host, and
  opaque metadata. The on-disk `module-processes.json` uses schema version 2.

`InstanceRuntime.register_module_runtime(module_id, module_instance_id=...)`
records an already-launched instance. It does not launch a process. An explicit
module instance ID must be unique; an attempt to overwrite one is rejected.
`unregister_module_runtime(module_id, module_instance_id=...)` removes only the
specified registration. The historic form without an explicit ID operates on
the single stable `host_instance_id:module_id` slot, preserving the existing
host integrations. `module_processes()` and the snapshot's `child_processes`
provide a legacy, one-entry-per-module view; do not use this view to route
multi-instance requests. Use `module_instances()` instead.

`ModuleContext.for_module(..., module_instance_id=...)` can bind a specific
instance without changing a module's scientific project ID or the original
context. Without the explicit ID, it retains legacy behavior.

**Scope boundary:** MI-02 does not create independent child processes, allocate
child ports, implement child shutdown, or assert that existing module adapters
are reentrant. These are MI-03/MI-04 responsibilities. No module-specific
project logic is moved into PAH.

## Local generated outputs

The root `.gitignore` now ignores `/.pah/`, `/analysis/`, `/ml_lab_results/`, and
other explicitly named root-level runtime/output directories. The root anchors
are intentional: an `analysis/` source package inside `pah/` or a submodule is
not ignored. Do not broadly ignore all `analysis` or `*.sqlite3` files; some
scientific fixtures may be intentionally versioned.

Git ignores only **untracked** files. Files that were previously committed
remain tracked even after `.gitignore` is updated. To untrack the known
host-generated directories **without deleting local working data**, from the
PAH repository root run:

```sh
git rm -r --cached --ignore-unmatch -- .pah analysis
```

Review `git status --short` before committing. If any files under those paths
were intentionally versioned, move them to a source/fixture location before
untracking. Do not run `git clean` or `rm -rf` for this cleanup.
