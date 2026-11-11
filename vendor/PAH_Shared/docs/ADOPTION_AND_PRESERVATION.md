# Adoption plan and preservation gates

P5-02 deliberately creates no required runtime dependency for any existing
repository. Its only outputs are a local library and a versioned table-view
contract. Consumers remain fully functional until they individually opt in.

## Packaging and dependency direction

1. Package locally as an offline wheel (`pah-shared==0.1.0`) and pin exact
   versions per consumer; install into standalone module environments if needed.
2. Browser assets are copied or served from **local** files, not CDN URLs. A
   module may embed only the CSS/JS portion without importing Python.
3. PAH_Shared imports neither PAH nor any of its modules; the package never
   discovers projects, starts workers, or connects to databases.
4. All styling is opt-in via `.ps-table-frame` / `.ps-table`; it does not restyle
   existing module pages. Neutral cells resemble conventional spreadsheet
   tables rather than PAH-brand-specific widgets.
5. Keep the existing module renderer and exports available while comparison
   tests run. Retire only after equivalent user interactions and outputs pass.

## First adoption candidates (P5-03/P5-04)

- pyPIQUE: one results table serves as visual/behavior reference; use existing
  field values, filters and stable IDs, not a reimplementation of SAT semantics.
- HSQA_DBN: one analysis-stage comparison table (the Pairwise Summary), with
  full-precision column semantics and verified candidate ordering.
- ML_Lab (P5-04): the existing non-destructive matrix draft editor keeps its
  own edit/undo/provenance policy; shared code supplies presentation.
- Code Analyzer/PAH (P5-04): bounded read-only tables, retaining their native
  analysis operations, toolbars and legacy fallback.

## Preservation cases

- Stable typed values and original row/column IDs across export and display.
- Default structured-export scope = all **filtered and sorted** rows in
  visible-column order, not a single page or raw file dump.
- A `window` snapshot cannot be misrepresented as the complete dataset.
- No hidden columns in exported table view; filters on hidden columns work.
- No silent truncation of large table exports or precision loss from display.
- No source file/data editing from generic UI; domain owner validates and
  records derived revisions when edits are requested.
- Standalone module works offline with its own static-asset delivery.
- Existing module-specific exports remain accessible until pilot parity.

## Non-goals of this sprint

There is no shared SQLite, host-owned computation, inter-module data bridge,
universal scientific data model, runtime daemon, or general-purpose utility
package. Interactions such as graph navigation or matrix editing are planned,
not yet implemented.
