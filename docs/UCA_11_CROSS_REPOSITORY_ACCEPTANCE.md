# UCA-11 — Four-repository offline integration acceptance

This increment extends the PAH-only UCA-11 baseline with a standalone read-only
check of **PAH, pyPIQUE, Code Analyzer, and the original CPS Analysis Lab**.

The contract inventory checks the PAH pane and navigation interfaces, pyPIQUE
finding evidence projection, Code Analyzer Python/ATLAS provider and source
navigation, and the standalone CPS parser baseline. A successful static inventory
is **not** evidence of running integration, parser semantic equivalence, or
browser correctness.

From PAH, supply explicit local checkout paths:

```bash
python scripts/uca11_cross_repository.py --pah . \
  --pypique ../pyPIQUE --code-analyzer ../Code_Repository_Cataloguer \
  --cps ../CPS-Analysis-Lab
```

Append `--run-selected-tests` to execute a bounded set of existing module-local
pytest tests. This uses the current Python environment; it installs nothing.
Failed or missing dependencies count as incomplete rather than passing. No test
output or source content is copied into the JSON report. Use `--output` to write
an exclusively-created report file; no existing report will be overwritten.

The original CPS parser and Code Analyzer's ATLAS copy remain separately owned
until explicit behavior/parity tests verify their compatibility. The runner does
not edit files, scan repositories, start SAT jobs, or initiate HTTP requests.

Still requires installed-system testing: all seven pane arrangements, editor
buffer/save preservation, verified bidirectional navigation, project switching,
Python and ATLAS source analysis, artifact/job provenance, scientific numerical
parity, and original standalone workflows. **No legacy retirement is authorized.**
