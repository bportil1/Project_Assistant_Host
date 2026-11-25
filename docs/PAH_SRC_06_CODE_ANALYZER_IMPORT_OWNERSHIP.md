# PAH SRC-06 — Code Analyzer import ownership and legacy namespace migration

PAH's Code Analyzer is installed from the **standalone** sibling
`../Code_Repository_Cataloguer` checkout. It must never be imported from a
`Project_Assistant_Host/code_analyzer` package or namespace.

## Root cause

Legacy PAH versions stored a partial `code_analyzer/language_providers` tree
inside the host repository. Deleting those files from Git leaves the directory
intact when the checkout also contains untracked source, caches, or scratch
files. Python can resolve that leftover directory as a namespace package. A
successful editable wheel installation does not repair that import-path
collision, so PAH's public Code Analyzer API check fails after pip succeeds.

## Permanent source contract

- `PAH/code_analyzer/` is ignored and no longer maintained by PAH.
- Normal `scripts/setup.sh` detects that path before installing the Code
  Analyzer component. If it is an untracked directory, setup **relocates the
  entire directory** to a unique, timestamped sibling directory under
  `../Project_Assistant_Host_legacy_import_recovery/`, preserving every file.
- Setup refuses to relocate **present** tracked PAH source, symlinks, non-directories, or
  nested Git checkouts. Git index entries already removed from the working
  tree by an unapplied-to-index patch do not block preservation of unrelated
  untracked files. It never deletes contents or edits PAH's `modules/`.
- The existing API check then verifies that the real `code_analyzer.CodeAnalyzer`
  and `code_analyzer.web.app.create_app` are importable from outside PAH root.
- Recovery files are intentionally retained for human review; PAH never deletes
  this recovery directory automatically.

## Operator acceptance

From the **standalone PAH root**:

```bash
PIP_NO_INDEX=1 ./scripts/setup.sh --skip-assets --skip-system-tools
.venv/bin/python -c 'import code_analyzer; print(code_analyzer.__file__)'
```

The reported path must resolve into the standalone Code Analyzer source or its
actual installed distribution, not into PAH's root or a namespace placeholder.
In case of refusal, inspect the recorded conflict; do not reset Git or delete
analysis results to bypass it.
