# UCA-09 — Language-aware read-only provider inspection

- The existing Python catalog and its Run Python Analysis action remain unchanged. The new **Inspect selected source** action explicitly requests one producer-owned Python/ATLAS navigation snapshot.
- Source must be a repository-relative file and the active project must have Code Analyzer enabled. The owner returns the source hash, nodes, diagnostics and capabilities. PAH does not transform structural candidates into verified semantic facts.
- Results are limited to 200 visible nodes (producer may return up to 5,000); diagnostics to 50 displayed messages. Selection sends a source-location request through UCA-06, whose existing server gate re-verifies current disk content.
- A changed project/repository invalidates in-flight responses and displayed selections. A changed file after inspection is not trusted for navigation without re-verification.
- No automatic analysis, dataset writes, parser replacement, or legacy retirement.
- Hosted/browser validation and installed provider importability are deferred integration acceptance checks.
