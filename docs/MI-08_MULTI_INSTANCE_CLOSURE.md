# PAH-MI-08 — Host instance-isolation closure and compatibility ledger

## Boundary enforced by this patch

- PAH's type adapter registry remains keyed by **module type**. It is not a map
  of running project sessions.
- The authoritative runtime map and job/artifact routes use distinct
  **module-instance IDs**. A modern child cannot register under the reserved
  legacy `host:module` slot.
- `InstanceRuntime.module_processes()` and snapshot `child_processes` now
  expose **only actual legacy** `host:module` registrations. A modern child is
  never silently presented to old clients as a single type-level instance.
  Use `module_instances()` or the instance-specific HTTP routes for children.
- A workspace change cannot alter a running child's captured workspace ID.
  Shutting down one owned subprocess does not terminate a sibling.
- The Instances UI only enables the New Instance action when the selected
  module is *both* enabled and advertises a supported independent process
  launch contract; the rule also holds after refresh/launch completion.
- Failed exec attempts remove their just-created empty scratch directories
  and do not leave a registry entry or child to be managed.

## Compatibility and tested behavior

- The existing type-level `launch`, `status`, `shutdown`, and `artifacts`
  contracts remain available for legacy integrations.
- The host still supplies only opaque IDs, separate process resources, and
  inter-module routing. Scientific data ownership remains with the submodule.
- Tests use dummy local children; they intentionally do not claim real-world
  ML_Lab, pyPIQUE, HSQA_DBN, Code Analyzer, or Workbench validation.
- Git modules are not modified. `.gitignore` improvements already delivered
  in MI-02 continue to exclude host-root generated `/analysis/` and `/.pah/`.

## Remaining limitations; do not treat these as completed

1. **Legacy embedded servers:** Workbench, Code Analyzer, and Reference Manager
   remain hosted through compatibility integrations until they expose and are
   validated against the generic independent-launch contract. MI-05 removes
   invasive ownership overrides, but does not automatically convert them.
2. **Module launch adapters:** The UI can launch multiple instances only for
   adapters implementing `process_launch_spec()`. Verify each independently;
   do not add module-specific project management to PAH.
3. **Child HTTP readiness and reserved ports:** Port selection is best-effort
   before bind, not a guaranteed held listener. A module must respect the port
   and report its readiness; generic health probing is future work.
4. **Crash recovery:** PAH only signals owned child-process handles. It does
   not claim to recover or kill children orphaned by a host crash.
5. **Background publications:** MI-07's publication HTTP API still requires
   the selected workspace context. Inactive-workspace background publication
   needs an explicitly authorized scope contract.
6. **Persistent shared data:** Different OS processes do not guarantee
   different document/database destinations unless the module honors scoped
   paths or safely coordinates shared storage.
7. **Full frontend/integration acceptance:** Run in the user's installed PAH
   environment with installed module packages and GUI to verify actual flows.

## Individual submodule review order (after MI-08)

The six external Git submodules declared in `.gitmodules` are:

1. `modules/ml_lab` — `ML_Lab`
2. `modules/pypique` — `pyPIQUE`
3. `modules/tech_documents` — `Research_Document_Workbench`
4. `modules/hsqa_dbn` — `HSQA_DBN`
5. `modules/code_analyzer` — `Code_Repository_Cataloguer`
6. `modules/reference_manager` — `Research_Paper_Repository_Manager`

`research_search` is a companion service integrated through Reference Manager,
not an additional external Git submodule in the supplied `.gitmodules`.

For **each** submodule, check only its published launch/status/stop contract,
configurable endpoint and writable runtime paths, telemetry/public artifacts,
process cleanup, and local `.gitignore` treatment of generated analysis,
caches, exports, and databases. Modify scientific logic only if a verified
contract incompatibility absolutely requires it; prefer adapter-only changes.
