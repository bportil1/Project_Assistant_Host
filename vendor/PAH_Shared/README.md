# PAH_Shared — local PAH setup fallback

This is the original PAH_Shared **0.3.0** source snapshot, reconstructed from the
PAH_Shared 0.1.0 source and the P5-03/P5-04 development patches. It is bundled
for offline installation on older PAH systems where no separate PAH_Shared
checkout is available. It is not a replacement for the standalone project.

`./scripts/setup.sh` prefers an installed compatible distribution or an
existing local standalone checkout; this copy is only the last fallback.
Do not change its declared version without updating the actual source.

---

# PAH_Shared

**P5-02 — Offline scientific interface foundation (v0.1.0).**

PAH_Shared is a separately versioned, standalone presentation library shared by
PAH, pyPIQUE, HSQA_DBN, ML_Lab, and Code Analyzer. It has **no dependency on PAH**,
scientific engines, databases, networks, Flask, Dash, or a running server.

> **Scope:** P5-02 establishes the local package, neutral read-only table baseline,
> and a cross-language **table view-model contract**. It does **not** migrate a
> consumer, render a full matrix editor, or implement CSV/PNG/SVG/TeX exports.
> Those are P5-03 (exports/pilot), P5-04 (editable matrix adoption) and P5-17
> (plots/graphs/hierarchy adapters). No existing module behavior is changed.

## Package contents

- `pah_shared.table_view` — Python validation and view selection, stdlib only.
- `pah_shared/static/table_view.mjs` — matching browser/Node API plus a minimal,
  accessible, read-only DOM table renderer. Zero external requests or JS build.
- `pah_shared/static/table.css` — neutral scientific styling, no PAH branding,
  global reset, dependencies, or app layout assumptions.
- `docs/TABLE_VIEW_CONTRACT_V1.md` — normative semantics including the critical
  distinction between a **complete snapshot** and a **server page window**.
- `docs/ADOPTION_AND_PRESERVATION.md` — optional/pinned adoption, fallbacks and
  the future export and edit boundaries.
- `tests/` — Python and Node contract tests, with one shared fixture.

## Local development and validation

From this repository (with local Python and Node installed):

```sh
PYTHONPATH=src python -m pytest -q tests/test_table_view.py
node tests/test_table_view.mjs
python tools/check_parity.py
```

To build an offline wheel using locally installed setuptools, without network
access:

```sh
python -m pip wheel --no-index --no-deps --no-build-isolation -w dist .
```

The wheel carries the `.mjs` and `.css` files for offline embedding. You can
copy the bundled assets into a module's own served static directory or serve
them from an explicitly registered **local** static route; PAH_Shared itself
must not open ports, assume a shared process, or load CDNs. Consumers can pin
`pah-shared==0.1.0` and retain their native UI fallback during adoption.

## Small API example

```python
from pah_shared import select_view

snapshot = {
    "schema_version": "1.0",
    "data_scope": "complete",
    "source": {"owner": "my_module", "artifact_id": "run-42/results", "revision": "1"},
    "columns": [
        {"id": "name", "title": "Name", "kind": "text"},
        {"id": "score", "title": "Score", "kind": "number"},
    ],
    "rows": [{"id": "a", "values": {"name": "Test", "score": 0.125}}],
    "view": {"page": {"index": 0, "size": 50}},
}

page = select_view(snapshot, scope="current_page")
all_displayed_data = select_view(snapshot, scope="all_matching")
```

Equivalent browser API:

```js
import { selectView, renderReadOnlyTable } from './table_view.mjs';
const page = selectView(snapshot, {scope: 'current_page'});
renderReadOnlyTable(document.getElementById('results'), snapshot);
```

See `examples/table.html` for a no-CDN example. Run a **local-only** HTTP
server from this repository to view it in a browser:

```sh
python -m http.server 8765 --bind 127.0.0.1
```

Open `http://127.0.0.1:8765/examples/table.html`.

## Ownership and privacy

PAH_Shared does **not** mutate datasets, determine metric semantics, execute
scientific operations, write SQLite, send requests, or bridge sibling modules.
The owning module provides the data and independently validates any future
requested edits or export queries. No source code or datasets are transmitted
outside the local environment. The source bundle makes no licensing decision
for the user's private repositories.

## P5-03 — one table implementation in multiple frameworks

`table_component.mjs` is the **only interactive table engine**. It owns the
visible grid, sorting, search, column filtering, pagination, and CSV/TeX/SVG/PNG
exports. `table_exports.mjs` uses the same validated view as the displayed grid.
No host-specific table sorting or export code should be introduced.

- Dash consumers supply a complete JSON snapshot through `data-pah-shared-table`
  on an `html.Div`; the shared `autoMountTables()` handles reinserted callback
  output. Dash remains the page/layout framework, **not** the table engine.
- Flask/browser consumers supply the **same** JSON snapshot contract (via
  `data-pah-shared-table` and `autoMountTables()`, or call `mountTable` directly).
  They do not maintain a second visible or hidden table implementation.
- Consumers serve the four assets from the pinned local `pah-shared` wheel.
  No internet/CDN, independent runtime service, or PAH host process is required.
- CSV/TeX/SVG/PNG default to all filtered/sorted rows, not the current page.
  A server-window snapshot refuses all-matching export; the owning module
  must supply a complete snapshot or implement its own authorized full query.
- PNG uses a local browser canvas to rasterize the shared SVG export; it
  requires browser integration testing. Images reject impossible dimensions
  rather than silently cropping/truncating rows.

The shared component is initially read-only; editable matrices are a later
migration with explicit module-owned authorization and persistence.

## P5-04 — editable matrix contract (v0.3)

The standalone `matrix_editor.mjs` now provides **the** editable rectangular
scientific matrix experience: direct cell editing, keyboard navigation,
selection, clipboard, undo/redo, paging and controlled draft save. It shares
the minimal presentation vocabulary of `table_component.mjs`, but editable
matrices intentionally use stable source coordinates rather than user-sorted
rows. The consuming module supplies `loadPage`, `saveDraft`, `onSaved` and
`validateCell` callbacks. No PAH runtime or ML_Lab dependency is imported by
PAH_Shared, and only the consuming module authorizes data writes.

The shared read-only table additionally supports optional cell-activation
callbacks (e.g. source navigation). This is presentation only: callbacks cannot
modify module state without the consumer explicitly implementing that action.
