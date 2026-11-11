/** PAH_Shared v0.1.0: offline table snapshot semantics and minimal read-only grid.
 * No host imports, CDN, network requests, scientific computation, file writes,
 * or independent storage. Exports and editing are intentionally later sprints.
 */
export const TABLE_CONTRACT_VERSION = '1.0';
export class TableContractError extends Error { constructor(message) { super(message); this.name = 'TableContractError'; } }
const kinds = new Set(['text', 'number', 'integer', 'boolean']);
const ops = new Set(['eq', 'ne', 'contains', 'gt', 'gte', 'lt', 'lte', 'is_null', 'not_null']);
const own = (o, k) => Object.prototype.hasOwnProperty.call(o, k);
const object = (value, where) => {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new TableContractError(`${where} must be an object`);
  }
  return value;
};
const id = (value, where) => {
  if (typeof value !== 'string' || !value.trim() || value.length > 256 || value.includes('\0')) {
    throw new TableContractError(`${where} must be a non-empty string of at most 256 characters`);
  }
  return value;
};
const nonneg = (v, where) => {
  if (!Number.isSafeInteger(v) || v < 0) throw new TableContractError(`${where} must be a nonnegative integer`);
  return v;
};
const cell = (value, kind, where) => {
  if (value === null) return;
  const ok = kind === 'text' ? typeof value === 'string'
    : kind === 'boolean' ? typeof value === 'boolean'
    : kind === 'integer' ? Number.isSafeInteger(value)
    : typeof value === 'number' && Number.isFinite(value);
  if (!ok) throw new TableContractError(`${where} must be ${kind} or null`);
};
const clone = (v) => structuredClone(v);
/** Validate and return a private, default-complete v1 snapshot. */
export function validateSnapshot(input) {
  object(input, 'snapshot');
  const s = clone(input);
  if (s.schema_version !== '1.0') throw new TableContractError('Unsupported table schema_version (expected 1.0)');
  s.data_scope ??= 'complete';
  if (!['complete', 'window'].includes(s.data_scope)) throw new TableContractError('data_scope must be complete or window');
  object(s.source, 'source');
  for (const key of ['owner', 'artifact_id', 'revision']) id(s.source[key], `source.${key}`);
  if (!Array.isArray(s.columns) || !s.columns.length) throw new TableContractError('columns must be a non-empty list');
  const ids = new Set(); const colKinds = new Map();
  for (const [index, c] of s.columns.entries()) {
    object(c, `columns[${index}]`);
    id(c.id, `columns[${index}].id`);
    if (ids.has(c.id)) throw new TableContractError(`Duplicate column ID: ${c.id}`);
    ids.add(c.id); id(c.title, `columns[${index}].title`);
    c.kind ??= 'text'; c.visible ??= true;
    if (!kinds.has(c.kind) || typeof c.visible !== 'boolean') throw new TableContractError('Invalid column kind or visibility');
    colKinds.set(c.id, c.kind);
  }
  if (!s.columns.some(c => c.visible)) throw new TableContractError('At least one column must remain visible');
  if (!Array.isArray(s.rows)) throw new TableContractError('rows must be a list');
  const rowIds = new Set();
  for (const [index, r] of s.rows.entries()) {
    object(r, `rows[${index}]`); id(r.id, `rows[${index}].id`);
    if (rowIds.has(r.id)) throw new TableContractError(`Duplicate row ID: ${r.id}`);
    rowIds.add(r.id); object(r.values, `rows[${index}].values`);
    if (r.display_values !== undefined) {
      object(r.display_values, `rows[${index}].display_values`);
      for (const [key, value] of Object.entries(r.display_values)) {
        if (!ids.has(key) || typeof value !== 'string') throw new TableContractError('display_values require known columns and text');
      }
    }
    for (const [key, value] of Object.entries(r.values)) {
      if (!ids.has(key)) throw new TableContractError(`Unknown value column: ${key}`);
      cell(value, colKinds.get(key), `row[${r.id}].${key}`);
    }
  }
  s.view ??= {}; object(s.view, 'view'); const v = s.view;
  v.search ??= ''; v.filters ??= []; v.sort ??= []; v.page ??= {};
  if (typeof v.search !== 'string') throw new TableContractError('view.search must be text');
  if (!Array.isArray(v.filters)) throw new TableContractError('view.filters must be a list');
  for (const f of v.filters) {
    object(f, 'filter');
    if (!ids.has(f.column_id) || !ops.has(f.op)) throw new TableContractError('Invalid filter column or operator');
    if (!['is_null', 'not_null'].includes(f.op)) {
      if (!own(f, 'value')) throw new TableContractError('Filter missing value');
      if (f.op === 'contains') {
        if (typeof f.value !== 'string') throw new TableContractError('contains requires a text value');
      } else if (f.value !== null) cell(f.value, colKinds.get(f.column_id), 'filter.value');
      if (['gt', 'gte', 'lt', 'lte'].includes(f.op) && f.value === null) throw new TableContractError('Ordered comparison requires non-null value');
    }
  }
  if (!Array.isArray(v.sort)) throw new TableContractError('view.sort must be a list');
  const seenSorts = new Set();
  for (const item of v.sort) {
    object(item, 'sort item');
    if (!ids.has(item.column_id) || !['asc', 'desc'].includes(item.direction) || seenSorts.has(item.column_id)) {
      throw new TableContractError('Invalid or duplicate sort column/direction');
    }
    seenSorts.add(item.column_id);
  }
  object(v.page, 'view.page');
  v.page.index ??= 0; v.page.size ??= 50;
  nonneg(v.page.index, 'page.index');
  if (!Number.isSafeInteger(v.page.size) || v.page.size < 1 || v.page.size > 1000) {
    throw new TableContractError('page.size must be an integer from 1 to 1000');
  }
  s.capabilities ??= {}; object(s.capabilities, 'capabilities');
  for (const key of ['edit', 'select', 'export']) {
    s.capabilities[key] ??= false;
    if (typeof s.capabilities[key] !== 'boolean') throw new TableContractError(`capabilities.${key} must be boolean`);
  }
  if (s.data_scope === 'window') {
    object(s.window, 'window');
    nonneg(s.window.offset, 'window.offset'); nonneg(s.window.total_filtered_rows, 'window.total_filtered_rows');
    if (s.window.offset !== v.page.index * v.page.size || s.rows.length > v.page.size ||
        s.window.offset + s.rows.length > s.window.total_filtered_rows) {
      throw new TableContractError('Window metadata is inconsistent with supplied rows/page');
    }
  } else if (own(s, 'window')) throw new TableContractError('Complete snapshots must not declare window metadata');
  return s;
}
const display = (value) => value === null || value === undefined ? '' : typeof value === 'boolean' ? String(value) : String(value);
function match(row, s) {
  const search = s.view.search.toLowerCase();
  if (search && !s.columns.some(c => c.visible && display(row.values[c.id]).toLowerCase().includes(search))) return false;
  for (const f of s.view.filters) {
    const a = row.values[f.column_id] ?? null, b = f.value, op = f.op;
    const ok = op === 'is_null' ? a === null : op === 'not_null' ? a !== null
      : op === 'contains' ? display(a).toLowerCase().includes(b.toLowerCase())
      : op === 'eq' ? a === b : op === 'ne' ? a !== b
      : a === null ? false
      : op === 'gt' ? a > b : op === 'gte' ? a >= b : op === 'lt' ? a < b : a <= b;
    if (!ok) return false;
  }
  return true;
}
function compare(a, b, sorts) {
  for (const item of sorts) {
    let x = a.values[item.column_id] ?? null, y = b.values[item.column_id] ?? null;
    if (x === null && y === null) continue;
    if (x === null) return 1; // Nulls last, in either direction.
    if (y === null) return -1;
    if (typeof x === 'string') { x = x.toLowerCase(); y = y.toLowerCase(); }
    const cmp = x > y ? 1 : x < y ? -1 : 0;
    if (cmp) return item.direction === 'desc' ? -cmp : cmp;
  }
  return 0;
}
/** Canonical view used by future exporters and the minimal renderer.
 * The all_matching scope rejects server windows, never silently truncates.
 */
export function selectView(input, { scope = 'current_page' } = {}) {
  const s = validateSnapshot(input);
  if (!['current_page', 'all_matching'].includes(scope)) throw new TableContractError('scope must be current_page or all_matching');
  if (s.data_scope === 'window' && scope === 'all_matching') {
    throw new TableContractError('Cannot export all matching rows from a server window; query the owner');
  }
  let selected, total;
  if (s.data_scope === 'complete') {
    selected = s.rows.filter(r => match(r, s));
    if (s.view.sort.length) selected = selected.map((r, idx) => ({ r, idx }))
      .sort((a, b) => compare(a.r, b.r, s.view.sort) || a.idx - b.idx).map(x => x.r);
    total = selected.length;
    if (scope === 'current_page') {
      const { index, size } = s.view.page;
      selected = selected.slice(index * size, (index + 1) * size);
    }
  } else {
    selected = s.rows;
    total = s.window.total_filtered_rows;
  }
  const columns = s.columns.filter(c => c.visible).map(({ id, title, kind }) => ({ id, title, kind }));
  return {
    schema_version: '1.0', scope, data_scope: s.data_scope, source: s.source,
    columns,
    rows: selected.map(row => ({ id: row.id, values: Object.fromEntries(columns.map(c => [c.id, row.values[c.id] ?? null])),
      ...(row.display_values ? {display_values: Object.fromEntries(columns.filter(c => Object.hasOwn(row.display_values, c.id)).map(c => [c.id, row.display_values[c.id]]))} : {}) })),
    total_filtered_rows: total, page: s.view.page,
    view: { search: s.view.search, filters: s.view.filters, sort: s.view.sort },
  };
}
/** Optional minimal, read-only baseline DOM table; call only in a browser.
 * Uses textContent exclusively for dataset values (no HTML injection).
 * Does not create an editor; edit permissions and persistence are module-owned.
 */
export function renderReadOnlyTable(container, snapshot, { label = 'Data table' } = {}) {
  if (!container || typeof container.replaceChildren !== 'function') throw new TypeError('A DOM container is required');
  const data = selectView(snapshot);
  const table = document.createElement('table');
  table.className = 'ps-table';
  table.setAttribute('aria-label', label);
  const head = document.createElement('thead');
  const headerRow = document.createElement('tr');
  for (const col of data.columns) {
    const th = document.createElement('th'); th.scope = 'col'; th.textContent = col.title; headerRow.appendChild(th);
  }
  head.appendChild(headerRow); table.appendChild(head);
  const body = document.createElement('tbody');
  for (const row of data.rows) {
    const tr = document.createElement('tr'); tr.dataset.rowId = row.id;
    for (const col of data.columns) {
      const td = document.createElement('td');
      const value = row.values[col.id];
      td.textContent = display(value);
      if (value === null) td.setAttribute('aria-label', 'Missing value');
      if (col.kind === 'integer' || col.kind === 'number') td.classList.add('ps-table__numeric');
      tr.appendChild(td);
    }
    body.appendChild(tr);
  }
  table.appendChild(body);
  const frame = document.createElement('div'); frame.className = 'ps-table-frame'; frame.appendChild(table);
  container.replaceChildren(frame);
  return data;
}
