# PAH_Shared — local-first setup bootstrap

The PAH and pyPIQUE distributions can require `pah-shared>=0.3,<0.4`, even
on machines that never checked out PAH_Shared separately. Previously,
`./scripts/setup.sh` installed the PAH host before PAH_Shared, causing pip to
search a package index and abort with `No matching distribution found`.

`./scripts/setup.sh` and `./scripts/update.sh` now use the existing PAH `.venv`
when it exists and the shared lifecycle installer bootstraps PAH_Shared
**before** installing either PAH or pyPIQUE. The bootstrap checks declared
versions and searches, in order:

1. A compatible `pah-shared` already installed in PAH's `.venv`
2. `modules/pah_shared`, `modules/PAH_Shared`, and `PAH_Shared` inside PAH
3. A sibling `../PAH_Shared` checkout
4. The checked-in `vendor/PAH_Shared` 0.3.0 snapshot

To select another source, set `PAH_SHARED_SOURCE=/absolute/local/path`.
The bootstrap invokes pip with `--no-index --no-deps --no-build-isolation`,
so the **shared-package bootstrap itself** cannot fetch remote code and does
not require an independent repository. Setup may still use pip or Git for
other dependencies and modules exactly as before.

The vendor fallback is the actual 0.3.0 implementation reconstructed from
the project's PAH_Shared 0.1.0 source and P5-03/P5-04 patches; it includes the
table and matrix assets. It is **not** a stub package and is not a substitute
for standalone PAH_Shared development. Existing compatible standalone copies
are preferred. If host and pyPIQUE dependency declarations conflict, or a
future release needs 0.4+, setup must fail clearly rather than masquerade as
a compatible installation. Update the versioned vendor fallback alongside
any future PAH_Shared dependency migration.

## Verifying after setup

```bash
.venv/bin/python -m pip show pah-shared project-assistant-host
.venv/bin/python -m pip check
```
