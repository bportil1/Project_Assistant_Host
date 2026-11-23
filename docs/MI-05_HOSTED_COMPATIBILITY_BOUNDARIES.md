# PAH-MI-05 — Hosted compatibility boundary cleanup

## Ownership

- PAH Core discovers module types, launches and observes runtime processes, routes by instance ID, and owns **only host-managed scratch paths**.
- Workbench owns its project list and persistent project data. The PAH `documents` resource remains a **suggested** root for PAH's quick document/file bridges; it does not replace Workbench's internal projects.
- Code Analyzer owns its analysis. A legacy hosted Code Analyzer is now pinned to the workspace selected when it was started. Switching PAH's active workspace does **not** silently restart or redirect it. Its event callback is ignored while PAH is selecting a different repository, so it cannot invalidate or overwrite current-host analysis state. To bind a different repository, stop and start the hosted surface explicitly.
- Reference Manager owns its library once the hosted app starts. The fallback compatibility shim still seeds a legacy configuration file; a future public runtime contract should replace that shim. Host selection does not overwrite a running Reference Manager's config behind its back.
- Discovered module `pah.runtimes` adapters take precedence over PAH's `HostSurfaceRuntimeAdapter` fallbacks.

## Compatibility and limits

- The three existing in-process WSGI-hosted surfaces are **legacy single-instance bridges**, not the new MI-03 multi-process architecture. This patch deliberately does not claim they support concurrent module processes.
- `pah/hosted_compat.py` is a quarantine layer for legacy module-specific imports; the orchestration manager does not implement their internal project semantics.
- The legacy Reference Manager config hook and Code Analyzer `create_app(workspace, on_analysis=...)` remain compatibility shims until each module advertises a public, process-safe entry point. Do not remove them without a working module-side launch interface.
- The UI multi-instance chooser and routing are MI-06 work. Job/artifact scoping is MI-07.
- The old `documents.bound_workspace` status now returns `null`; `documents.suggested_document_root` distinguishes PAH's resource choice from Workbench's actual projects.
- `analysis.bound_workspace` reports the **actual started** root, `analysis.selected_workspace` reports PAH's current choice, and `analysis.selection_differs` exposes divergence.

## Local acceptance checks

1. The Workbench New Project action remains visible and its app/engine are not altered by PAH.
2. Switching PAH's active research workspace while a hosted analyzer is running does not restart it or change `bound_workspace`.
3. Closing/reopening the analyzer explicitly binds the newly selected root.
4. Installed `pah.runtimes` adapters are not replaced by hardcoded hosted-surface fallbacks.
5. Existing hosted UI endpoints and Research Search integration remain available in compatibility mode.
