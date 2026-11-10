# UCA-07 — Language-provider foundation

This is an additive, **opt-in** Python API under `code_analyzer.language_providers`.
It neither replaces `build_catalog()` nor changes the public `CodeAnalyzer.catalog()` behavior, Python similarity, AST graph construction, source editing, or web routes.

## Boundaries

- `LanguageProviderRegistry`: explicit local registration, extension dispatch, and duplicate rejection. No plugin discovery/imports from arbitrary source projects.
- `ProviderDescriptor`: stable provider ID, language, suffixes, and **declared** capabilities. Unavailable capabilities must stay false rather than being inferred from node names.
- `LanguageAnalysis`: source-linked structural items and diagnostics plus the provider-owned full artifact. No shared assumption that all languages have Python classes/functions, imports, or similarity semantics.
- `PythonLanguageProvider`: calls the existing `index_python_file` and keeps its `ModuleEntry` as a dictionary under `provider_artifact`. This is not a second Python parser or catalog.

The ATLAS provider belongs in UCA-08 and must preserve the CPS parser's structural/provisional confidence levels and versioned original artifacts, without claiming verified IEEE 716 semantics.

`default_registry().analyze("path/to/file.py", repository_root)` is an optional caller API. It reads existing files and returns an in-memory result; it does not write a database or alter project files. The filesystem guards reject ordinary symlink paths, but the registry is not a hostile-filesystem, descriptor-safe evidence verifier. Use P5-18 source verification before trusting a selection from an untrusted or mutable tree. Similarly, this API does not supply a scan-time source revision guarantee.

## Compatibility and later migration

UCA-08 can register ATLAS independently; UCA-09 may project provider output into UI. Existing Python indexing remains authoritative until a separately validated migration decision. No legacy retirement is authorized here.
