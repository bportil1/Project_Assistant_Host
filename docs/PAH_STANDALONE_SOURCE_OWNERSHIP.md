# Standalone source ownership for PAH setup/update

PAH's `modules/` Git submodule worktrees are **legacy snapshots**, not edit or
installation sources. They are intentionally neither initialized nor reset by
`scripts/setup.sh` and `scripts/update.sh`, even when `--skip-submodules` is omitted.
Changes left in those worktrees are **not erased** by this patch. Before separately
reconciling their contents, compare them to their true standalone source owners.

PAH resolves local Python packages from *adjacent* checkouts:

| Component | Standalone checkout |
|---|---|
| Code Analyzer | `../Code_Repository_Cataloguer` |
| pyPIQUE | `../pyPIQUE` |
| ML_Lab | `../ML_Lab` |
| HSQA_DBN | `../HSQA_DBN` |
| Document Workbench | `../Research_Document_Workbench` |
| Reference Manager | `../Research_Paper_Repository_Manager` |
| Research Search | `../Research_Paper_Repository_Manager/modules/paper_searcher` (source-owner nested component) |
| PAH_Shared | `../PAH_Shared` |

Missing required source repositories (including PAH_Shared) fail preflight before pip installation. An installed wheel with a matching version is **not** a substitute for the standalone source checkout.
PAH resolves PAH_Shared version constraints from the real standalone sources,
not from out-of-date embedded module metadata. `--latest-modules` is an explicit,
opt-in update of *standalone* repos; normal setup/update never advances them.

PAH previously tracked provider stubs at `code_analyzer/language_providers`.
Those were duplicates of the standalone Code Analyzer implementation and could
form a misleading importable namespace package. They have been removed from
the host. The public `code_analyzer` package must come from the installed
Code_Repository_Cataloguer distribution, never from PAH's root.

Do not run `git reset`, `git clean`, or `git submodule update` as a recovery
procedure. If the legacy embedded worktrees contain edits, inventory and save
them before deciding how to apply any unique changes to standalone repositories.
