# Table View Contract — v1.0

**Status:** Implemented for validation and view selection in P5-02. Future
renderers/exports must consume the same view semantics. This is not a data
storage schema, experiment schema, or permission system.

## 1. Snapshot structure

```json
{
  "schema_version": "1.0",
  "data_scope": "complete",
  "source": {"owner": "HSQA_DBN", "artifact_id": "trial/results", "revision": "sha256:..."},
  "columns": [
    {"id": "candidate", "title": "Candidate", "kind": "text", "visible": true},
    {"id": "distance", "title": "Wasserstein", "kind": "number", "visible": true}
  ],
  "rows": [{"id": "trial-1", "values": {"candidate": "t1", "distance": 0.12}}],
  "view": {
    "search": "",
    "filters": [],
    "sort": [{"column_id": "distance", "direction": "asc"}],
    "page": {"index": 0, "size": 50}
  },
  "capabilities": {"edit": false, "select": true, "export": true}
}
```

- `schema_version`: exactly `1.0`; breaking changes require a new version.
- `source`: module-owned provenance **identity only**: `owner`, `artifact_id`,
  `revision`. Optional additional metadata may be attached by owners; it does
  **not** confer access to any other module's private storage.
- `columns`: stable, unique IDs and labels in **display order**; kinds:
  `text`, `integer`, `number`, `boolean`; `visible` defaults to true. At least
  one column must be visible.
- `rows`: stable, unique row IDs and cell values by column ID. Missing values
  are `null` (including omitted known cell keys). Values are scalar JSON data;
  finite numeric values only. Integers must be JS-safe (up to 2^53-1 in
  magnitude) to avoid inconsistent browser representations.
- `view.search`: case-insensitive substring query across **visible columns**.
- `view.filters`: intersection of predicates with `column_id`, `op`, and for
  value-bearing operations `value`. Operators: `eq`, `ne`, `contains`, `gt`,
  `gte`, `lt`, `lte`, `is_null`, `not_null`. Filters may use hidden columns.
  Values must respect the column's kind; `contains` uses a string operand.
- `view.sort`: stable, ordered list of `{column_id,direction}`. Types are
  compared within their own columns. Missing values always sort last, even for
  descending sort; ties preserve original row order. Cross-implementation
  locale-specific text collation is **not** guaranteed: owners should supply
  server-window results for demanding locale-aware/full-dataset sorting.
- `view.page`: zero-based `index`, `size` from 1 to 1000 (default 50).
- `capabilities`: descriptive `edit/select/export` flags (default false).
  Neither renderer nor validator decides authorizations. A module must
  re-authorize user actions itself.

## 2. Complete vs. server-window data

### `data_scope: "complete"`

The `rows` array contains **every unfiltered observation** of this snapshot.
The local selection operations apply `search`, `filters`, and `sort` and can
return either:

- `current_page`: the selected page only.
- `all_matching`: **all filtered, sorted rows with visible columns, across all
  pages**. This is the default data scope for a future "Export displayed
  table" command, rather than export only the visible viewport.

### `data_scope: "window"`

The owner already filtered and sorted its authoritative dataset and supplies
only a page. Snapshot `rows` are already the page; do not re-filter or re-sort.
Add metadata:

```json
"window": {"offset": 50, "total_filtered_rows": 382}
```

`offset` must equal `view.page.index * view.page.size`. Rows must fit inside
this window. `select_view(..., scope="all_matching")` and
`selectView(..., {scope:"all_matching"})` **fail** for window snapshots:
they cannot invent missing pages. A future exporter must call the owning
module's paginated query/export endpoint and verify the result scope.

### No silent truncation

For very large filtered results, a future exporter may reject the request,
ask the owner to generate an all-matching export, or make explicit page/chunk
exports. It must never label a single page or viewport image as "all rows".

## 3. Structured results and precision

`select_view` / `selectView` return a normalized object with:

- `columns`: visible columns in display order (`id`, `title`, `kind`).
- `rows`: stable IDs, visible values only, and `null` for missing values.
- `total_filtered_rows`, `scope`, `data_scope`, `source`, `page`, `view`.

Cell values are preserved as typed values and never rounded or overwritten by
display formatting. Decimal/formatting display controls and numeric export
policies belong to later sprints. For full precision or large integer arrays
beyond browser-safe numbers, the producing module should use its authoritative
binary/scientific format; do not cast them silently through JSON.

## 4. Security and edit boundary

The minimal DOM renderer uses `textContent` for all user-provided cell values.
It is read-only. Future edit operations are *requests* to the data owner;
validation, provenance, SQLite writes and derived data creation remain in the
owning module. A source identifier alone never authorizes a filesystem read.

## 5. P5-02 vs future work

| Capability | Sprint |
|---|---|
| Validate/normalize snapshots; select current-page/all-matching | **P5-02 implemented** |
| Neutral CSS and small read-only browser table | **P5-02 implemented** |
| CSV/TeX/image exports and first pyPIQUE/HSQA pilot integrations | P5-03 |
| Editable matrix UI and module-specific edit adapters | P5-04 |
| Plots, network/graph controls, hierarchy and general UI adapters | P5-17 |

The `all_matching` view is export-*ready* data, not yet a file-export tool.
