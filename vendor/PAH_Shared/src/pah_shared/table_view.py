"""Versioned, engine-independent table view contract (v1.0).

This package does NOT own datasets, edit them, page a database or export tables.
A *complete* snapshot can be locally filtered/sorted; a *window* represents a
single page already filtered and sorted by its owning module.  Conflating the
two is forbidden, particularly for later export integrations.
"""

from __future__ import annotations

from copy import deepcopy
from functools import cmp_to_key
from math import isfinite
from typing import Any, Mapping


class TableContractError(ValueError):
    """A table view violates the shared semantic contract."""


_ALLOWED_KINDS = {"text", "number", "integer", "boolean"}
_OPS = {"eq", "ne", "contains", "gt", "gte", "lt", "lte", "is_null", "not_null"}
_MAX_PAGE_SIZE = 1000


def _required_id(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 256 or "\x00" in value:
        raise TableContractError(f"{where} must be a non-empty string of at most 256 characters")
    return value


def _object(value: Any, where: str) -> dict:
    if not isinstance(value, dict):
        raise TableContractError(f"{where} must be an object")
    return value


def _nonneg_int(value: Any, where: str) -> int:
    if type(value) is not int or value < 0:
        raise TableContractError(f"{where} must be a nonnegative integer")
    return value


def _cell(value: Any, kind: str, where: str) -> None:
    if value is None:
        return
    allowed = (
        isinstance(value, str) if kind == "text" else
        type(value) is bool if kind == "boolean" else
        (type(value) is int and abs(value) <= (2**53 - 1)) if kind == "integer" else
        (type(value) in (int, float) and isfinite(value) and (type(value) is not int or abs(value) <= (2**53 - 1)))
    )
    if not allowed:
        raise TableContractError(f"{where} must be {kind} or null")


def validate_snapshot(snapshot: Mapping[str, Any]) -> dict:
    """Validate and return a deep-copied, default-complete v1 snapshot.

    Stable IDs, types, ordering, page limits and source ownership are enforced;
    server-window snapshots are explicitly distinguished from complete data.
    """
    s = deepcopy(_object(snapshot, "snapshot"))
    if s.get("schema_version") != "1.0":
        raise TableContractError("Unsupported table schema_version (expected 1.0)")
    scope = s.get("data_scope", "complete")
    if scope not in ("complete", "window"):
        raise TableContractError("data_scope must be complete or window")
    s["data_scope"] = scope
    source = _object(s.get("source"), "source")
    for k in ("owner", "artifact_id", "revision"):
        _required_id(source.get(k), f"source.{k}")
    if not isinstance(s.get("columns"), list) or not s["columns"]:
        raise TableContractError("columns must be a non-empty list")
    col_ids: set[str] = set()
    kinds: dict[str, str] = {}
    for idx, col in enumerate(s["columns"]):
        col = _object(col, f"columns[{idx}]")
        cid = _required_id(col.get("id"), f"columns[{idx}].id")
        if cid in col_ids:
            raise TableContractError(f"Duplicate column ID: {cid}")
        col_ids.add(cid)
        _required_id(col.get("title"), f"columns[{idx}].title")
        kind = col.get("kind", "text")
        if kind not in _ALLOWED_KINDS:
            raise TableContractError(f"Unsupported column kind: {kind}")
        if type(col.get("visible", True)) is not bool:
            raise TableContractError("column.visible must be boolean")
        col["kind"] = kind
        col["visible"] = col.get("visible", True)
        kinds[cid] = kind
    if not any(col["visible"] for col in s["columns"]):
        raise TableContractError("At least one column must remain visible")
    if not isinstance(s.get("rows"), list):
        raise TableContractError("rows must be a list")
    row_ids: set[str] = set()
    for idx, row in enumerate(s["rows"]):
        row = _object(row, f"rows[{idx}]")
        rid = _required_id(row.get("id"), f"rows[{idx}].id")
        if rid in row_ids:
            raise TableContractError(f"Duplicate row ID: {rid}")
        row_ids.add(rid)
        values = _object(row.get("values"), f"rows[{idx}].values")
        if "display_values" in row:
            display_values = _object(row["display_values"], f"rows[{idx}].display_values")
            if any(key not in col_ids or not isinstance(value, str) for key, value in display_values.items()):
                raise TableContractError("display_values require known columns and text")
        for key, value in values.items():
            if key not in col_ids:
                raise TableContractError(f"Unknown value column: {key}")
            _cell(value, kinds[key], f"row[{rid}].{key}")
    v = _object(s.get("view", {}), "view")
    search = v.get("search", "")
    if not isinstance(search, str):
        raise TableContractError("view.search must be text")
    v["search"] = search
    filters = v.get("filters", [])
    if not isinstance(filters, list):
        raise TableContractError("view.filters must be a list")
    for f in filters:
        _object(f, "filter")
        column_id = f.get("column_id")
        op = f.get("op")
        if column_id not in col_ids or op not in _OPS:
            raise TableContractError("Invalid filter column or operator")
        if op not in ("is_null", "not_null"):
            if "value" not in f:
                raise TableContractError("Filter missing value")
            if op == "contains":
                if not isinstance(f["value"], str):
                    raise TableContractError("contains requires a text value")
            elif f["value"] is not None:
                _cell(f["value"], kinds[column_id], "filter.value")
            if op in ("gt", "gte", "lt", "lte") and f["value"] is None:
                raise TableContractError("Ordered comparison requires non-null value")
    v["filters"] = filters
    sort = v.get("sort", [])
    if not isinstance(sort, list):
        raise TableContractError("view.sort must be a list")
    sort_ids: set[str] = set()
    for item in sort:
        _object(item, "sort item")
        cid = item.get("column_id")
        if cid not in col_ids or item.get("direction") not in ("asc", "desc") or cid in sort_ids:
            raise TableContractError("Invalid or duplicate sort column/direction")
        sort_ids.add(cid)
    v["sort"] = sort
    page = _object(v.get("page", {}), "view.page")
    index = _nonneg_int(page.get("index", 0), "page.index")
    size = page.get("size", 50)
    if type(size) is not int or not (1 <= size <= _MAX_PAGE_SIZE):
        raise TableContractError("page.size must be an integer from 1 to 1000")
    v["page"] = {"index": index, "size": size}
    s["view"] = v
    cap = _object(s.get("capabilities", {}), "capabilities")
    for key in ("edit", "select", "export"):
        if type(cap.get(key, False)) is not bool:
            raise TableContractError(f"capabilities.{key} must be boolean")
        cap[key] = cap.get(key, False)
    s["capabilities"] = cap
    if scope == "window":
        window = _object(s.get("window"), "window")
        offset = _nonneg_int(window.get("offset"), "window.offset")
        total = _nonneg_int(window.get("total_filtered_rows"), "window.total_filtered_rows")
        if offset != index * size or len(s["rows"]) > size or offset + len(s["rows"]) > total:
            raise TableContractError("Window metadata is inconsistent with supplied rows/page")
        s["window"] = {"offset": offset, "total_filtered_rows": total}
    elif "window" in s:
        raise TableContractError("Complete snapshots must not declare window metadata")
    return s


def _text(value: Any) -> str:
    if value is None:
        return ""
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _match(row: dict, snapshot: dict) -> bool:
    values = row["values"]
    search = snapshot["view"]["search"].casefold()
    if search and not any(search in _text(values.get(c["id"])).casefold()
                          for c in snapshot["columns"] if c["visible"]):
        return False
    for f in snapshot["view"]["filters"]:
        actual, expected, op = values.get(f["column_id"]), f.get("value"), f["op"]
        if op == "is_null":
            matches = actual is None
        elif op == "not_null":
            matches = actual is not None
        elif op == "contains":
            matches = expected.casefold() in _text(actual).casefold()
        elif op == "eq":
            matches = actual == expected
        elif op == "ne":
            matches = actual != expected
        elif actual is None:
            matches = False
        elif op == "gt":
            matches = actual > expected
        elif op == "gte":
            matches = actual >= expected
        elif op == "lt":
            matches = actual < expected
        else:
            matches = actual <= expected
        if not matches:
            return False
    return True


def _compare(a: dict, b: dict, sorts: list[dict]) -> int:
    for item in sorts:
        cid = item["column_id"]
        left, right = a["values"].get(cid), b["values"].get(cid)
        if left is None and right is None:
            continue
        if left is None:
            return 1  # Missing values always last, including descending.
        if right is None:
            return -1
        if isinstance(left, str):
            left, right = left.casefold(), right.casefold()
        result = (left > right) - (left < right)
        if result:
            return -result if item["direction"] == "desc" else result
    return 0  # Python stable sort retains original row order.


def select_view(snapshot: Mapping[str, Any], *, scope: str = "current_page") -> dict:
    """Return a display snapshot; never silently promote a partial window to all rows.

    `all_matching` means all filtered+sorted rows and visible columns, across
    pages; `current_page` means just the page supplied or selected.  Raw/source
    exports and data persistence intentionally belong to the producing module.
    """
    s = validate_snapshot(snapshot)
    if scope not in ("current_page", "all_matching"):
        raise TableContractError("scope must be current_page or all_matching")
    if s["data_scope"] == "window" and scope == "all_matching":
        raise TableContractError("Cannot export all matching rows from a server window; query the owner")
    if s["data_scope"] == "complete":
        matched = [r for r in s["rows"] if _match(r, s)]
        if s["view"]["sort"]:
            matched.sort(key=cmp_to_key(lambda a, b: _compare(a, b, s["view"]["sort"])))
        total = len(matched)
        if scope == "current_page":
            p = s["view"]["page"]
            matched = matched[p["index"] * p["size"]: (p["index"] + 1) * p["size"]]
    else:
        matched = s["rows"]  # Owner already applied search, filters, and sort.
        total = s["window"]["total_filtered_rows"]
    visible = [c for c in s["columns"] if c["visible"]]
    return {
        "schema_version": "1.0",
        "scope": scope,
        "data_scope": s["data_scope"],
        "source": s["source"],
        "columns": [{"id": c["id"], "title": c["title"], "kind": c["kind"]} for c in visible],
        "rows": [{"id": r["id"], "values": {c["id"]: r["values"].get(c["id"]) for c in visible},
                  **({"display_values": {c["id"]: r["display_values"][c["id"]]
                     for c in visible if c["id"] in r["display_values"]}}
                     if "display_values" in r else {})} for r in matched],
        "total_filtered_rows": total,
        "page": s["view"]["page"],
        "view": {"search": s["view"]["search"], "filters": s["view"]["filters"], "sort": s["view"]["sort"]},
    }
