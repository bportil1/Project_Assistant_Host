# PAH local editable installation contract (offline or online)

The PAH lifecycle installs the PAH host and all managed Python packages from
**standalone sibling source repositories**, never from `Project_Assistant_Host/modules/`.

The installed virtual environment is also the Python build environment. Its
`pip`, `setuptools>=68`, and `wheel` are prepared by setup before editable
installs. PAH_Shared already uses `--no-index --no-deps --no-build-isolation`
for its separate, strict local bootstrap. For other managed editable sources,
PAH uses `pip install --no-build-isolation -e <standalone-source>`.

This prevents PEP 517 build isolation from launching a temporary pip process
which requires downloading the declared build backend even when a suitable
backend already exists in PAH's virtual environment. It does **not** disable
install-time dependency resolution or relax PAH_Shared requirements. With
`PIP_NO_INDEX=1`, any genuinely missing runtime dependency or build backend
must be satisfied locally before setup can complete. Setup reports that failure
instead of accessing network indexes or falling back to PAH's embedded modules.

This policy also applies to the optional developer test-extra installation.
Existing jobs, module data, and embedded Git worktrees are not modified.

Run from the host repository:

```sh
PIP_NO_INDEX=1 ./scripts/setup.sh --skip-assets --skip-system-tools
```

Verify:

```sh
.venv/bin/python -m pip check
.venv/bin/python -c 'import pah_shared, pathlib; p=pathlib.Path(pah_shared.__file__).parent/"static"/"interactive_graph_view.mjs"; print(p, p.is_file())'
```
