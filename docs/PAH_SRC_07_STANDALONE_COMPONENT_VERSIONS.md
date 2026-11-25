# SRC-07 — Standalone component version panel

The Component Versions & Dependencies panel now reflects **independently owned
repositories**, not PAH Git submodules. All repositories are resolved through
`GIT_COMPONENTS` sibling paths; no source is edited in `PAH/modules/`.

- A clean standalone checkout matching its cached remote-tracking branch is
  **Current**. Behind = **Update available**; ahead = **Ahead locally**;
  both ahead and behind = **Diverged**. Uncommitted changes = **Modified
  working tree**; missing remote-tracking data = **Remote status unknown**.
- **PAH pinned**, **Restore Pinned**, **Version commit message**, and
  **Record Component Versions** were removed from the UI. A standalone repository
  has no parent Git gitlink, so those controls were inapplicable and generated
  errors rather than useful operations. Legacy server endpoints remain for
  compatibility but cannot restore or record non-gitlinked standalone entries.
- **Refresh Local** never fetches. **Fetch Remote Status** and **Update** are
  explicit network operations triggered by the user; working-tree checks still
  gate updates. No `git push` is performed by the panel.
- Component editable reinstalls reuse PAH's prepared virtual environment via
  the existing `--no-build-isolation` command, consistent with setup/update.
- This change only updates PAH source, UI and tests, never module repositories
  or source/artifacts within PAH's retired `modules/` directory.

Run the focused tests with `python -m pytest -q tests/test_src07_standalone_component_versions.py tests/test_component_versions.py`.
