# PAH_Shared local-source update contract

## Permanent install contract

- PAH, pyPIQUE, ML_Lab, HSQA_DBN, and Code Analyzer require `pah-shared>=0.4,<0.5`. The 0.3 vendored
  snapshot is **not** a valid substitute for the SU-02 graph-view contract.
- Normal `scripts/setup.sh` and `scripts/update.sh --no-pull` reinstall a
  compatible PAH_Shared **from an existing local checkout**, even when the
  installed version number is unchanged. This makes new static assets visible
  in PAH's `.venv`, rather than accepting an older wheel with the same version.
- The preferred path is `../PAH_Shared`, or set `PAH_SHARED_SOURCE` to an
  explicitly chosen checkout. The sibling source takes priority over optional
  older copies under `modules/`. A compatible installed wheel is a fallback only when there is
  no compatible local source; the graph viewer files must still be installed.
- The install is fully offline (`pip --no-index --no-deps --no-build-isolation`).
  The local build backend (`setuptools`) must already be in `.venv`.
- Setup fails with an actionable message when the checkout or installed
  distribution lacks `interactive_graph_view.mjs` or `.css`. It will not
  report a successful update when required graph assets are absent.

## Receiving a pushed PAH_Shared change

PAH does not silently follow the latest remote commits: a pushed change must
also be fetched into the checkout used by PAH. Explicitly run
`scripts/update.sh --latest-shared` to fast-forward a **clean, tracked**
PAH_Shared Git checkout (usually `../PAH_Shared`) and reinstall that exact
local source. This action refuses dirty, detached, or untracked remote states.

Use `scripts/update.sh --no-pull` for a completely offline reinstall from the
current local source state. `PAH_SHARED_SOURCE` overrides are never pulled by
PAH; update those repositories deliberately before running setup.

## Browser assets and process reload

After updating and restarting the PAH / ML_Lab processes, inspect the target
virtual environment with:

```bash
.venv/bin/python -c "import pah_shared,pathlib; s=pathlib.Path(pah_shared.__file__).parent/'static'; print(s/'interactive_graph_view.mjs', (s/'interactive_graph_view.mjs').is_file())"
```

The ML_Lab companion patch separately repairs the Feature Profiling
**Dependency matrix** contrast. PAH_Shared updates and the ML_Lab visual fix
are independent but are delivered together for this integration increment.
