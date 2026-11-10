# P5-00 — Local compatibility baseline runner

This is a **non-mutating**, standard-library launcher for curated, repository-owned
pytest suites from the five supplied Phase 4 snapshots. It does not install packages,
download anything, or call another module's private APIs. Its subprocesses run only
tests already present in each module checkout. Keep tests that require network
providers disabled until their behavior is explicitly reviewed.

The manifest `p5_00_suites.json` preserves each user-supplied archive's SHA-256,
and the exact selected baseline test paths used in Phase 4. An archive hash is
**provenance**, not a claim about the installed checkout. Test-file hashes in a
result report describe exactly what was executed in that local checkout.

Run the PAH baseline from the PAH repository root:

```bash
python tools/p5_00_compat.py --module pah --output /tmp/p5-00-pah.json
```

Run a pyPIQUE checkout, including the restored scenario regression chain:

```bash
python tools/p5_00_compat.py --module pypique --profile all \
  --repo pypique=../pyPIQUE --output /tmp/p5-00-pypique.json
```

Run all five only when all five checkouts are supplied:

```bash
python tools/p5_00_compat.py --all-modules --profile all \
  --repo pypique=../pyPIQUE --repo hsqa_dbn=../HSQA_DBN \
  --repo ml_lab=../ML_Lab --repo code_analyzer=../Code_Repository_Cataloguer \
  --output /tmp/p5-00-five.json
```

Use `--interpreter ml_lab=../ML_Lab/.venv/bin/python` (etc.) to select a
module-specific environment. Default is the Python interpreter running the
harness. Any missing repository, missing test, timed-out test, or failed test
is explicitly reported, never treated as a pass. Skip counts remain visible.

The PAH launcher regression now checks the intended direct-start `/` behavior
and separately preserves the `/launcher` route check. The pyPIQUE fix restores
missing local test fixture modules for MI-U1/U2 without changing scientific
implementations, inference semantics, or production routes.

## P5-00 boundaries

- This runner is a **test tool**, not a shared runtime dependency or PAH service.
- Other modules remain independently testable with normal `python -m pytest`.
- Optional Flask/Dash/browser tests can remain skipped; they have not been
  silently promoted to a passing UI claim.
- Do not retire routes, logic, artifacts, or migration rollback paths based
  only on this first compatibility baseline.
