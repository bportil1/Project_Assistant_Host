"""Build a neutral signed information network from HSQA_DBN analysis artifacts.

The adapter belongs to PAH because it translates one provider's artifact layout
into a cross-module contract.  Neither HSQA_DBN nor pyPIQUE need to import one
another for this handoff.
"""
from __future__ import annotations

import csv
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping

from pah.contracts import ArtifactRef


SCHEMA_ID = "pah.information-network"
SCHEMA_VERSION = "1"


def _read_json(path: Path) -> Mapping[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(f"Expected a JSON object in {path}")
    return payload


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _read_matrix(path: Path) -> list[list[float]]:
    rows: list[list[float]] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            rows.append([float(value) for value in row])
    return rows


def _finite(value: float | None) -> float | None:
    if value is None:
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _alignment(value: float | None) -> str:
    if value is None or value == 0.0:
        return "neutral"
    return "reinforcing" if value > 0.0 else "opposing"


def _direction(value: float) -> str:
    if value == 0.0:
        return "neutral"
    return "reinforcing" if value > 0.0 else "opposing"


def _feature_node_id(feature_id: str) -> str:
    return f"feature:{feature_id}"


def _latent_node_id(layer: int, index: int) -> str:
    return f"latent:{layer}:{index}"


def _domain_node_id(scope: str) -> str:
    return f"domain:{scope}"


def _node_for_layer(
    layer: int,
    index: int,
    *,
    features: list[Mapping[str, Any]],
    scope_layer: int | None,
    scopes: Mapping[int, str],
) -> str:
    if layer == 0 and 0 <= index < len(features):
        return _feature_node_id(str(features[index].get("id") or features[index].get("label") or f"Feature {index}"))
    if scope_layer is not None and layer == scope_layer and index in scopes:
        return _domain_node_id(scopes[index])
    return _latent_node_id(layer, index)


def _matrix_value(matrix: list[list[float]], i: int, j: int) -> float | None:
    if i >= len(matrix) or j >= len(matrix[i]):
        return None
    return _finite(matrix[i][j])


def build_information_network(
    analysis_artifact: ArtifactRef,
    *,
    output_path: str | Path,
) -> ArtifactRef:
    """Translate one valid HSQA representation-analysis artifact to a neutral graph."""
    errors: list[str] = []
    output_path = Path(output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if analysis_artifact.kind != "representation_analysis":
        errors.append(f"expected representation_analysis, got {analysis_artifact.kind!r}")
    if analysis_artifact.schema_id != "hsqa_dbn.representation_analysis" or analysis_artifact.schema_version != "1":
        errors.append(
            "expected hsqa_dbn.representation_analysis@1, got "
            f"{analysis_artifact.schema_id}@{analysis_artifact.schema_version}"
        )
    if analysis_artifact.validation_state == "invalid":
        errors.extend(analysis_artifact.validation_errors or ("source representation analysis is invalid",))

    source_path = Path(str(analysis_artifact.location or "")).expanduser()
    analysis: Mapping[str, Any] = {}
    if not source_path.is_file():
        errors.append(f"representation-analysis manifest does not exist: {source_path}")
    else:
        try:
            analysis = _read_json(source_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"could not read representation-analysis manifest: {exc}")

    artifacts = analysis.get("artifacts") if isinstance(analysis, Mapping) else {}
    artifacts = artifacts if isinstance(artifacts, Mapping) else {}
    raw_vis = artifacts.get("visualizer_data")
    vis_dir = Path(str(raw_vis)).expanduser().resolve() if raw_vis else None
    raw_dependency = artifacts.get("visible_dependency")
    dependency_dir = Path(str(raw_dependency)).expanduser().resolve() if raw_dependency else None

    dataset_metadata: Mapping[str, Any] = {}
    features: list[Mapping[str, Any]] = []
    if vis_dir is None or not vis_dir.is_dir():
        errors.append("HSQA analysis does not expose a valid visualizer_data directory")
    else:
        metadata_path = vis_dir / "dataset_metadata.json"
        try:
            dataset_metadata = _read_json(metadata_path)
            raw_features = dataset_metadata.get("features") or []
            if isinstance(raw_features, list):
                features = [item for item in raw_features if isinstance(item, Mapping)]
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"could not read HSQA dataset metadata: {exc}")
    if not features:
        errors.append("HSQA information network does not contain ordered input-feature metadata")

    scopes: dict[int, str] = {}
    node_rows: list[dict[str, str]] = []
    if vis_dir is not None and vis_dir.is_dir():
        try:
            node_rows = _read_csv(vis_dir / "nodes.csv")
        except OSError as exc:
            errors.append(f"could not read HSQA network nodes: {exc}")
        scope_path = vis_dir / "scope_index.csv"
        if scope_path.is_file():
            try:
                for row in _read_csv(scope_path):
                    scopes[int(row["idx"])] = str(row["scope"])
            except (OSError, KeyError, ValueError) as exc:
                errors.append(f"could not read HSQA scope index: {exc}")

    raw_layers: list[int] = []
    for row in node_rows:
        try:
            raw_layers.append(int(row["raw_layer"]))
        except (KeyError, TypeError, ValueError):
            continue
    scope_layer = max(raw_layers) if scopes and raw_layers else None

    nodes: dict[str, dict[str, Any]] = {}
    for index, feature in enumerate(features):
        feature_id = str(feature.get("id") or feature.get("label") or f"Feature {index}")
        nodes[_feature_node_id(feature_id)] = {
            "id": _feature_node_id(feature_id),
            "kind": "feature",
            "label": str(feature.get("label") or feature_id),
            "feature_id": feature_id,
            "index": index,
            "layer": 0,
            "groups": [str(value) for value in (feature.get("groups") or [])],
        }
    for row in node_rows:
        try:
            layer = int(row["raw_layer"])
            index = int(row["node_idx"])
        except (KeyError, TypeError, ValueError):
            continue
        node_id = _node_for_layer(layer, index, features=features, scope_layer=scope_layer, scopes=scopes)
        if node_id in nodes:
            continue
        if scope_layer is not None and layer == scope_layer and index in scopes:
            kind = "domain"
            label = scopes[index]
        else:
            kind = "latent"
            label = f"Latent L{layer}:{index}"
        nodes[node_id] = {
            "id": node_id,
            "kind": kind,
            "label": label,
            "index": index,
            "layer": layer,
        }
    for index, scope in scopes.items():
        node_id = _domain_node_id(scope)
        nodes.setdefault(node_id, {
            "id": node_id,
            "kind": "domain",
            "label": scope,
            "index": index,
            "layer": scope_layer,
        })

    edges: list[dict[str, Any]] = []
    signed_edge_count = 0
    if vis_dir is not None and vis_dir.is_dir():
        for filename in ("edges_pos.csv", "edges_neg.csv"):
            path = vis_dir / filename
            if not path.is_file():
                continue
            try:
                rows = _read_csv(path)
            except OSError as exc:
                errors.append(f"could not read {filename}: {exc}")
                continue
            for row in rows:
                try:
                    src_layer = int(row["src_layer"])
                    src_idx = int(row["src_idx"])
                    tgt_layer = int(row["tgt_layer"])
                    tgt_idx = int(row["tgt_idx"])
                    weight = float(row["weight"])
                except (KeyError, TypeError, ValueError):
                    continue
                # Scope edges are semantic propagation rather than direct PMI.
                if scope_layer is not None and tgt_layer == scope_layer:
                    continue
                source = _node_for_layer(src_layer, src_idx, features=features, scope_layer=scope_layer, scopes=scopes)
                target = _node_for_layer(tgt_layer, tgt_idx, features=features, scope_layer=scope_layer, scopes=scopes)
                edges.append({
                    "source": source,
                    "target": target,
                    "relationship": "signed_information",
                    "metric": "normalized_pmi",
                    "signed_score": weight,
                    "magnitude": abs(weight),
                    "direction": _direction(weight),
                    "source_layer": src_layer,
                    "target_layer": tgt_layer,
                })
                signed_edge_count += 1

        for filename in ("contributions_pos.csv", "contributions_neg.csv"):
            path = vis_dir / filename
            if not path.is_file():
                continue
            try:
                rows = _read_csv(path)
            except OSError as exc:
                errors.append(f"could not read {filename}: {exc}")
                continue
            for row in rows:
                try:
                    layer = int(row["layer"])
                    index = int(row["node"])
                    scope = str(row["scope"])
                    value = float(row["val"])
                except (KeyError, TypeError, ValueError):
                    continue
                source = _node_for_layer(layer, index, features=features, scope_layer=None, scopes={})
                target = _domain_node_id(scope)
                nodes.setdefault(target, {"id": target, "kind": "domain", "label": scope})
                edges.append({
                    "source": source,
                    "target": target,
                    "relationship": "semantic_projection",
                    "contribution": value,
                    "magnitude": abs(value),
                    "direction": _direction(value),
                    "source_layer": layer,
                })

    if signed_edge_count == 0:
        errors.append("HSQA visualizer data does not contain signed feature/latent information edges")

    correlation_available = False
    dependency_edge_count = 0
    if dependency_dir is not None and dependency_dir.is_dir() and features:
        matrix_paths = {
            "pearson": dependency_dir / "pearson_visible_visible.csv",
            "spearman": dependency_dir / "spearman_visible_visible.csv",
            "mutual_information": dependency_dir / "mi_visible_visible.csv",
        }
        if all(path.is_file() for path in matrix_paths.values()):
            try:
                pearson = _read_matrix(matrix_paths["pearson"])
                spearman = _read_matrix(matrix_paths["spearman"])
                mutual_information = _read_matrix(matrix_paths["mutual_information"])
                correlation_available = True
                for i in range(len(features)):
                    for j in range(i + 1, len(features)):
                        p = _matrix_value(pearson, i, j)
                        s = _matrix_value(spearman, i, j)
                        mi = _matrix_value(mutual_information, i, j)
                        if p is None and s is None and mi is None:
                            continue
                        source_id = str(features[i].get("id") or features[i].get("label") or f"Feature {i}")
                        target_id = str(features[j].get("id") or features[j].get("label") or f"Feature {j}")
                        edges.append({
                            "source": _feature_node_id(source_id),
                            "target": _feature_node_id(target_id),
                            "relationship": "feature_dependency",
                            "mutual_information": mi,
                            "pearson": p,
                            "spearman": s,
                            "correlation_sign": _alignment(p),
                        })
                        dependency_edge_count += 1
            except (OSError, ValueError) as exc:
                errors.append(f"could not read HSQA visible dependency matrices: {exc}")

    payload = {
        "schema": SCHEMA_ID,
        "schema_version": 1,
        "source_analysis": {
            "artifact_id": analysis_artifact.artifact_id,
            "schema_id": analysis_artifact.schema_id,
            "schema_version": analysis_artifact.schema_version,
            "location": analysis_artifact.location,
        },
        "dataset": {
            "dataset_name": dataset_metadata.get("dataset_name"),
            "domain": dataset_metadata.get("domain"),
            "semantic_adapter": dataset_metadata.get("semantic_adapter"),
        },
        "nodes": list(nodes.values()),
        "edges": edges,
        "metadata": {
            "signed_information_metric": "normalized_pmi",
            "correlation_available": correlation_available,
            "feature_dependency_edge_count": dependency_edge_count,
            "signed_information_edge_count": signed_edge_count,
            "semantic_projection_available": bool(scopes),
            "notes": [
                "Mutual information is non-negative; signed feature/latent topology is stored separately as normalized PMI.",
                "Pearson/Spearman signs describe feature alignment and must not be interpreted as negative mutual information.",
            ],
        },
        "provenance": {
            "representation_analysis_artifact_id": analysis_artifact.artifact_id,
            "representation_artifact_ids": list(analysis_artifact.parent_artifact_ids),
        },
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return ArtifactRef(
        artifact_id="pah-information-network-current",
        kind="information_network",
        producer_module="pah",
        location=str(output_path),
        schema_id=SCHEMA_ID,
        schema_version=SCHEMA_VERSION,
        media_type="application/vnd.pah.information-network+json",
        producer_version=None,
        project_id=analysis_artifact.project_id,
        capabilities=("information_network", "mutual_information_analysis", "signed_dependency_analysis"),
        parent_artifact_ids=(analysis_artifact.artifact_id,),
        validation_state="invalid" if errors else "valid",
        validation_errors=tuple(errors),
        metadata={
            "runtime_managed": True,
            "correlation_available": correlation_available,
            "feature_dependency_edge_count": dependency_edge_count,
            "signed_information_edge_count": signed_edge_count,
        },
        provenance={
            "source": "PAH Code Analysis Lab HSQA_DBN information-network adapter",
            "representation_analysis_artifact_id": analysis_artifact.artifact_id,
        },
    )
