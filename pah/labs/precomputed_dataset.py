"""Conservative precomputed tabular-data intake for Code Analysis Lab.

The importer intentionally does not clean or impute values.  It converts a
user-selected CSV/TSV matrix into PAH's neutral feature-dataset contract while
preserving row/column order and recording the source file fingerprint.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any


class PrecomputedDatasetError(ValueError):
    pass


_ID_NAMES = {
    "id", "sample", "sample_id", "sampleid", "name", "project", "project_id",
    "repository", "repository_id", "repo", "label", "dataset", "subject",
    "unnamed: 0", "unnamed_0", "index",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _delimiter(path: Path, sample: str) -> str:
    if path.suffix.lower() == ".tsv":
        return "\t"
    if path.suffix.lower() == ".csv":
        default = ","
    else:
        default = ","
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;|").delimiter
    except csv.Error:
        return default


def _numeric(value: str) -> float | int:
    text = str(value).strip()
    if text == "":
        raise PrecomputedDatasetError("blank numeric value")
    try:
        number = float(text)
    except ValueError as exc:
        raise PrecomputedDatasetError(f"not numeric: {text!r}") from exc
    if not math.isfinite(number):
        raise PrecomputedDatasetError(f"not finite: {text!r}")
    # Preserve count matrices as integers when possible while retaining general
    # numeric matrices without rounding.
    return int(number) if number.is_integer() else number


def _read_table(path: str | Path) -> tuple[Path, str, list[str], list[list[str]]]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise PrecomputedDatasetError(f"Dataset file does not exist: {source}")
    if source.suffix.lower() not in {".csv", ".tsv", ".txt"}:
        raise PrecomputedDatasetError("Precomputed input must be CSV, TSV, or delimited text")
    try:
        text = source.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise PrecomputedDatasetError("Dataset must currently be UTF-8/UTF-8-SIG encoded") from exc
    if not text.strip():
        raise PrecomputedDatasetError("Dataset file is empty")
    delimiter = _delimiter(source, text[:8192])
    reader = csv.reader(text.splitlines(), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        raise PrecomputedDatasetError("Dataset file contains no rows")
    header = [str(item).strip() for item in rows[0]]
    if not header or any(not item for item in header):
        raise PrecomputedDatasetError("Dataset requires a non-empty header for every column")
    duplicates = sorted({name for name in header if header.count(name) > 1})
    if duplicates:
        raise PrecomputedDatasetError(f"Duplicate column names are not allowed: {', '.join(duplicates)}")
    body = rows[1:]
    if not body:
        raise PrecomputedDatasetError("Dataset must contain at least one data row")
    for index, row in enumerate(body, start=2):
        if len(row) != len(header):
            raise PrecomputedDatasetError(
                f"Row {index} contains {len(row)} fields; expected {len(header)}"
            )
    return source, delimiter, header, body


def _suggest_id_column(header: list[str], rows: list[list[str]]) -> str | None:
    for name in header:
        if re.sub(r"\s+", "_", name.strip().lower()) in _ID_NAMES or name.strip().lower() in _ID_NAMES:
            return name
    if len(header) <= 1:
        return None
    first = [row[0].strip() for row in rows]
    first_numeric = True
    for value in first:
        try:
            _numeric(value)
        except PrecomputedDatasetError:
            first_numeric = False
            break
    if not first_numeric:
        # Only infer the first column as an identifier when the remaining columns
        # really are numeric.  Ambiguous tables stay explicit.
        try:
            for row in rows:
                for value in row[1:]:
                    _numeric(value)
        except PrecomputedDatasetError:
            return None
        return header[0]
    return None


def inspect_precomputed_table(path: str | Path, *, id_column: str | None = None) -> dict[str, Any]:
    source, delimiter, header, rows = _read_table(path)
    suggested = _suggest_id_column(header, rows)
    chosen = id_column if id_column not in {None, "", "__generated__"} else None
    if chosen is not None and chosen not in header:
        raise PrecomputedDatasetError(f"Unknown identifier column: {chosen!r}")
    effective_id = chosen if id_column not in {None, ""} else suggested
    if id_column == "__generated__":
        effective_id = None
    feature_columns = [name for name in header if name != effective_id]
    if not feature_columns:
        raise PrecomputedDatasetError("Dataset must contain at least one feature column")

    errors: list[str] = []
    column_indexes = {name: header.index(name) for name in feature_columns}
    for name in feature_columns:
        index = column_indexes[name]
        for row_number, row in enumerate(rows, start=2):
            try:
                _numeric(row[index])
            except PrecomputedDatasetError as exc:
                errors.append(f"{name} row {row_number}: {exc}")
                if len(errors) >= 20:
                    break
        if len(errors) >= 20:
            break

    id_values = []
    if effective_id is not None:
        id_index = header.index(effective_id)
        id_values = [row[id_index].strip() for row in rows]
        blanks = [index + 2 for index, value in enumerate(id_values) if not value]
        if blanks:
            errors.append(f"identifier column {effective_id!r} contains blank values")
        if len(set(id_values)) != len(id_values):
            errors.append(f"identifier column {effective_id!r} contains duplicate values")

    return {
        "source": str(source),
        "source_sha256": _sha256(source),
        "delimiter": "TAB" if delimiter == "\t" else delimiter,
        "columns": header,
        "row_count": len(rows),
        "column_count": len(header),
        "suggested_id_column": suggested,
        "effective_id_column": effective_id,
        "feature_columns": feature_columns,
        "feature_count": len(feature_columns),
        "valid": not errors,
        "errors": errors,
        "preview": [dict(zip(header, row)) for row in rows[:5]],
    }


def materialize_precomputed_feature_dataset(
    path: str | Path,
    *,
    output_root: str | Path,
    id_column: str | None = None,
    dataset_name: str | None = None,
) -> tuple[Path, dict[str, Any], dict[str, Any]]:
    source, delimiter, header, rows = _read_table(path)
    inspection = inspect_precomputed_table(source, id_column=id_column)
    if not inspection["valid"]:
        raise PrecomputedDatasetError("; ".join(inspection["errors"]))
    effective_id = inspection["effective_id_column"]
    feature_columns = list(inspection["feature_columns"])
    feature_indexes = [header.index(name) for name in feature_columns]

    if effective_id is None:
        sample_ids = [f"sample-{index + 1}" for index in range(len(rows))]
        sample_labels = list(sample_ids)
    else:
        id_index = header.index(effective_id)
        sample_ids = [row[id_index].strip() for row in rows]
        sample_labels = list(sample_ids)

    values = [[_numeric(row[index]) for index in feature_indexes] for row in rows]
    source_hash = inspection["source_sha256"]
    root = Path(output_root).expanduser().resolve() / source_hash[:16]
    root.mkdir(parents=True, exist_ok=True)
    analysis_target = root / "pypique_workspace"
    analysis_target.mkdir(parents=True, exist_ok=True)
    output = root / "feature_dataset.json"
    name = str(dataset_name or source.stem).strip() or source.stem
    payload = {
        "schema": "pah.feature-dataset.matrix",
        "schema_version": 1,
        "dataset_name": name,
        "source_type": "precomputed_csv" if delimiter == "," else "precomputed_delimited",
        "domain": "software_security" if all(str(item).upper().startswith("CWE-") for item in feature_columns) else "generic",
        "semantic_adapter": "cwe" if all(str(item).upper().startswith("CWE-") for item in feature_columns) else None,
        "sample_ids": sample_ids,
        "sample_labels": sample_labels,
        "feature_ids": feature_columns,
        "values": values,
        "metadata": {
            "source": str(source),
            "source_sha256": source_hash,
            "delimiter": "\\t" if delimiter == "\t" else delimiter,
            "id_column": effective_id,
            "row_count": len(rows),
            "feature_count": len(feature_columns),
            "analysis_bypassed": True,
            "transformations": [],
        },
    }
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    metadata = {
        "source_type": payload["source_type"],
        "source_path": str(source),
        "source_sha256": source_hash,
        "dataset_name": name,
        "rows": len(rows),
        "features": len(feature_columns),
        "id_column": effective_id,
        "analysis_target": str(analysis_target),
        "analysis_bypassed": True,
        "history_selectable": True,
    }
    return output, payload, metadata
