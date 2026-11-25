# SU-02 — PAH_Shared interactive graph view (`pah-shared.graph-view@1`)

**Status:** Implemented opt-in renderer/controller in PAH_Shared 0.4.0 sources;
consumer migration is **not** performed by this patch. No semantic/scientific
calculation is performed in the shared module.

## Purpose and provenance

The implementation extracts and adapts camera, deterministic layered layout,
overview/drill-down, directional source tracing, zoom and pointer navigation
from pyPIQUE's `src/pique_py/static/model_explorer.js`. Keyboard-selectable
nodes/edges, inspector handoff and safe SVG text handling draw on
`src/pique_py/static/concluded_graph.js`. Only presentation mechanics move;
pyPIQUE's PIQUE/MI/latent meanings, trace rules, concluded-artifact verification,
scoring and scenario editing remain in pyPIQUE. Copyright and license notice:
`THIRD_PARTY_NOTICES_GRAPH.md`.

The existing `pah-shared.graph@1` (`graph_adapter.mjs`) and
`pah-shared.hierarchy@1` (`hierarchy_adapter.mjs`) are intentionally unchanged.
The new module is opt-in and packaged as static resources:

- `src/pah_shared/static/interactive_graph_view.mjs`
- `src/pah_shared/static/interactive_graph_view.css`

It works without PAH host, HTTP, third-party packages, network calls, browser
storage, scientific databases, or implicit disk writes.

## Input contract (minimal example)

```json
{
  "schema": "pah-shared.graph-view@1",
  "view_id": "original-structure",
  "source_revision": "sha256:verified-by-owner",
  "graph_role": "source_structure",
  "title": "Imported object",
  "nodes": [
    {"id": "parent", "label": "Root", "kind": "object", "group": "depth-0"},
    {"id": "child", "label": "Value", "kind": "scalar", "group": "depth-1"}
  ],
  "edges": [
    {"id": "source-edge-1", "source": "parent", "target": "child",
      "directed": true, "traceable": true, "kind": "source_child"}
  ],
  "display": {
    "layout": "layers",
    "coverage": {"scope": "exhaustive", "total_nodes": 2, "total_edges": 1}
  },
  "overlays": {"nodes": {}, "edges": {}}
}
```

`display.layout` may be `layers` (deterministic by *explicit display group*),
`circular` (pure visualization) or `recorded` (each node must supply finite
`position:{x,y}`). Neither layout makes scientific ancestry claims. Directed
and undirected display edges may coexist. Only `directed:true` plus
`traceable:true` participates in source tracing; the owner explicitly chooses
which recorded relationship types are eligible.

`source_revision` is opaque and **provided by a verifying owner** (e.g. ML_Lab
or pyPIQUE); PAH_Shared cannot authenticate it. `graph_role` is a declared view
role, not evidence that input is a source DAG, MI estimate, or Bayesian network.
The source object remains immutable; this is a detached presentation snapshot.

### Optional scientific metrics

Each node or edge may carry an owner-produced descriptor:

```json
"overlays": {
  "nodes": {
    "child": {
      "status": "measured",
      "metrics": [
        {"name":"entropy", "value":0.7, "unit":"bits",
         "estimator":"empirical-discrete", "support":20, "status":"measured"}
      ]
    }
  },
  "edges": {}
}
```

Metric availability is **not** inferred from a numeric value. Missing/unsupported
measurements use `value:null` with `status` `pending`, `unavailable`, or
`insufficient_support`. Zero is a legitimate measurement only when `status`
explicitly says `measured`. The owner owns denominators, units, estimands,
confidence and support interpretation; this viewer cannot compute uncertainty.

## Integration API

```js
import {mountInteractiveGraph, interactiveGraphRows} from './interactive_graph_view.mjs';

const viewer = mountInteractiveGraph(hostElement, verifiedView, {
  onSelect({view_id, source_revision, graph_role, kind, id}) {
    // The owner retrieves its corresponding inspector record and checks
    // source revision before displaying calculated/recorded detail.
  },
  onViewportChange(({camera, coverage}) => {
    // Optional display-only viewport and source-coverage status.
  }
});

viewer.fit();
viewer.zoom(1.2);
viewer.overview();  // display-only layer summary
viewer.context();   // returns to the original view
viewer.focusSources(true); // follows only producer-authorized directed edges
viewer.select('node', 'child', {recenter:true});  // linked table selection
const tableRows = interactiveGraphRows(verifiedView);
viewer.update(nextVerifiedView); // new revision clears selection
viewer.destroy();
```

`interactiveGraphRows()` exposes original IDs, graph revision, group/type,
edge direction, overlay status and *detached metric descriptors* to a host table
(e.g. PAH_Shared's existing table component). The renderer itself does not own
or create table markup, inspections, source links, graph reconstruction,
missing-data policy or model estimation.

Large inputs are validated up to 5,000 nodes and 15,000 edges. The DOM budget is
450 nodes / 850 edges per rendered graph. An oversized graph switches to an
explicitly labeled **collapsed group overview**. Clicking a group opens a page
of 12 recorded source nodes plus up to 72 explicitly connected neighbors. The
`coverage` getter and viewport event always distinguish displayed counts and
full source totals. `nextPage()`/`previousPage()` operate on group pages.
The renderer never silently discards source nodes from the input object.
For additional scale, the owner should explicitly supply a sampled/filtered
view with honest `coverage` totals and sampling seed. Browser-performance
acceptance remains for SU-03/04/11.

**Scope limits:** SU-02 does not replace pyPIQUE's graph viewer (SU-03), wire
ML_Lab's `StructuredObject` into this view (SU-04), compute branch variance,
MI, CMI or estimators (SU-05–07), propose pruning (SU-08–09), or replace either
module's scientific inspector. These operations require separate migrations.

## Acceptance and validation

- `node --test tests/test_graph_adapter.mjs tests/test_hierarchy_adapter.mjs tests/test_interactive_graph_view.mjs`
- `node --test tests/*.mjs` (PAH_Shared JS regressions)
- Independent Git patch apply and lint/whitespace checks.
- SU-03: opt-in pyPIQUE consumer adapter and side-by-side browser regression.
- SU-04: opt-in ML_Lab structured-object view and contextual navigation checks.
- SU-11: real dataset, actual pyPIQUE concluded graph, multi-workspace and
  PAH-hosted browser acceptance; cannot be assumed from headless Node tests.
