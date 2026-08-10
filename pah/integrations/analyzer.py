from __future__ import annotations

from dataclasses import asdict, is_dataclass
import importlib
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Any


class AnalyzerIntegrationError(RuntimeError):
    """Raised when PAH cannot use the optional CodeAnalyzer integration."""


class AnalyzerIntegration:
    """Narrow PAH adapter around ``code_analyzer.CodeAnalyzer``.

    PAH deliberately knows only the public ``CodeAnalyzer`` façade. The adapter
    owns workspace binding, explicit analysis lifecycle, serialization, and a
    few host-oriented convenience queries (entities for an open file,
    dependencies for an entity, and nearest neighbors from the global matrix).

    Importantly, binding a workspace does *not* analyze it. Analysis remains an
    explicit user action and is marked stale after source-tree mutations.
    """

    FUNCTION_TYPES = {"function", "method"}

    def __init__(self) -> None:
        self._lock = RLock()
        self._root: Path | None = None
        self._engine: Any | None = None
        self._catalog: Any | None = None
        self._generation = 0
        self._stale = False
        self._matrix_cache: dict[tuple[Any, ...], Any] = {}
        self._import_error: str | None = None
        self._analyzer_class: Any | None = None

    # ------------------------------------------------------------------
    # Optional-module discovery / lifecycle
    # ------------------------------------------------------------------
    def _load_class(self) -> Any | None:
        if self._analyzer_class is not None:
            return self._analyzer_class
        try:
            module = importlib.import_module("code_analyzer")
            analyzer_class = getattr(module, "CodeAnalyzer")
        except Exception as exc:  # optional dependency may be wholly absent
            self._import_error = f"{type(exc).__name__}: {exc}"
            return None
        self._analyzer_class = analyzer_class
        self._import_error = None
        return analyzer_class

    def bind(self, root: str | Path) -> None:
        resolved = Path(root).expanduser().resolve()
        with self._lock:
            if self._root == resolved:
                return
            self._root = resolved
            self._engine = None
            self._catalog = None
            self._generation = 0
            self._stale = False
            self._matrix_cache.clear()

    def clear(self) -> None:
        with self._lock:
            self._root = None
            self._engine = None
            self._catalog = None
            self._generation = 0
            self._stale = False
            self._matrix_cache.clear()

    def mark_stale(self) -> None:
        with self._lock:
            if self._catalog is not None:
                self._stale = True

    def status(self) -> dict[str, Any]:
        analyzer_class = self._load_class()
        with self._lock:
            return {
                "available": analyzer_class is not None,
                "import_error": self._import_error,
                "project_root": str(self._root) if self._root else None,
                "analyzed": self._catalog is not None,
                "stale": self._stale,
                "generation": self._generation,
                "summary": dict(self._catalog.summary) if self._catalog is not None else None,
            }

    def analyze(self) -> dict[str, Any]:
        analyzer_class = self._load_class()
        if analyzer_class is None:
            raise AnalyzerIntegrationError(
                "CodeAnalyzer is not installed in the PAH environment. "
                "Initialize modules/code_analyzer and run scripts/setup.sh."
                + (f" Import error: {self._import_error}" if self._import_error else "")
            )
        with self._lock:
            if self._root is None:
                raise AnalyzerIntegrationError("Open a PAH workspace before analyzing code.")

            # A new engine and a reload both pass through CodeAnalyzer's public
            # session API. No analyzer internals are imported here.
            if self._engine is None:
                self._engine = analyzer_class(self._root)
            else:
                self._engine.reload()
            self._catalog = self._engine.catalog(refresh=False)
            self._generation += 1
            self._stale = False
            self._matrix_cache.clear()
            return self.overview()

    def _require(self) -> tuple[Any, Any]:
        with self._lock:
            if self._engine is None or self._catalog is None:
                raise AnalyzerIntegrationError("Analyze the current project first.")
            return self._engine, self._catalog

    # ------------------------------------------------------------------
    # Serialization / basic queries
    # ------------------------------------------------------------------
    @staticmethod
    def _node_payload(node: Any) -> dict[str, Any]:
        metadata = dict(getattr(node, "metadata", {}) or {})
        return {
            "id": node.id,
            "node_type": node.node_type,
            "name": node.name,
            "qualified_name": node.qualified_name,
            "path": node.path,
            "parent_id": node.parent_id,
            "children": list(node.children),
            "metadata": metadata,
        }

    @staticmethod
    def _edge_payload(edge: Any) -> dict[str, Any]:
        if is_dataclass(edge):
            return asdict(edge)
        return {
            "source_id": edge.source_id,
            "target_id": edge.target_id,
            "relationship_type": edge.relationship_type,
            "source_level": edge.source_level,
            "target_level": edge.target_level,
            "evidence": dict(edge.evidence or {}),
            "metadata": dict(edge.metadata or {}),
        }

    @staticmethod
    def _normalized_relative(path: str) -> str:
        value = str(path or "").replace("\\", "/").strip("/")
        return PurePosixPath(value).as_posix() if value else ""

    def overview(self) -> dict[str, Any]:
        _, catalog = self._require()
        return {
            "project_name": catalog.project_name,
            "project_root": catalog.project_root,
            "summary": dict(catalog.summary),
            "warnings": list(catalog.warnings),
            "generation": self._generation,
            "stale": self._stale,
        }

    def functions(self) -> list[dict[str, Any]]:
        _, catalog = self._require()
        rows = [
            self._node_payload(node)
            for node in catalog.nodes.values()
            if node.node_type in self.FUNCTION_TYPES
        ]
        rows.sort(key=lambda row: (row.get("qualified_name") or row["name"], row["id"]))
        return rows

    def file_entities(self, path: str) -> dict[str, Any]:
        _, catalog = self._require()
        relative = self._normalized_relative(path)
        allowed = {"module", "class", "function", "method"}
        entities = [
            self._node_payload(node)
            for node in catalog.nodes.values()
            if self._normalized_relative(node.path or "") == relative and node.node_type in allowed
        ]

        def sort_key(row: dict[str, Any]) -> tuple[int, int, str]:
            order = {"module": 0, "class": 1, "function": 2, "method": 3}
            line = int((row.get("metadata") or {}).get("line_start") or 0)
            return (line, order.get(row["node_type"], 9), row["name"])

        entities.sort(key=sort_key)
        return {"path": relative, "entities": entities, "stale": self._stale}

    def entity(self, node_id: str) -> dict[str, Any]:
        engine, _ = self._require()
        try:
            node = engine.get_node(node_id)
        except KeyError as exc:
            raise AnalyzerIntegrationError(str(exc)) from exc
        return self._node_payload(node)

    def resolve_entity_marker(self, marker: dict[str, str]) -> dict[str, Any] | None:
        """Resolve a PAH document marker against the current explicit analysis.

        New markers carry the analyzer entity id. Older markers are resolved by
        source path + qualified name so existing PAH 0.3/0.4 documents remain
        useful after upgrading.
        """
        node_id = str(marker.get("id") or "").strip()
        if node_id:
            try:
                return self.entity(node_id)
            except AnalyzerIntegrationError:
                pass

        path = self._normalized_relative(str(marker.get("path") or ""))
        qualified = str(marker.get("entity") or "").strip()
        if not path or not qualified:
            return None
        try:
            rows = self.file_entities(path)["entities"]
        except AnalyzerIntegrationError:
            return None
        for row in rows:
            if str(row.get("qualified_name") or row.get("name") or "") == qualified:
                return row
        return None

    def dependencies(self, node_id: str) -> dict[str, Any]:
        _, catalog = self._require()
        if node_id not in catalog.nodes:
            raise AnalyzerIntegrationError(f"Unknown analyzer entity: {node_id}")

        outgoing: list[dict[str, Any]] = []
        incoming: list[dict[str, Any]] = []
        for edge in catalog.relationships:
            if edge.source_id == node_id:
                payload = self._edge_payload(edge)
                target = catalog.nodes.get(edge.target_id)
                payload["other"] = self._node_payload(target) if target else {"id": edge.target_id, "name": edge.target_id}
                outgoing.append(payload)
            if edge.target_id == node_id:
                payload = self._edge_payload(edge)
                source = catalog.nodes.get(edge.source_id)
                payload["other"] = self._node_payload(source) if source else {"id": edge.source_id, "name": edge.source_id}
                incoming.append(payload)

        key = lambda row: (row["relationship_type"], (row.get("other") or {}).get("qualified_name") or (row.get("other") or {}).get("name", ""))
        outgoing.sort(key=key)
        incoming.sort(key=key)
        return {"id": node_id, "outgoing": outgoing, "incoming": incoming, "stale": self._stale}

    # ------------------------------------------------------------------
    # Similarity / repository-level operations
    # ------------------------------------------------------------------
    @staticmethod
    def _config_key(
        *, context_depth: int, distance_decay: float, external_import_weight: float, ordering: str
    ) -> tuple[Any, ...]:
        return (
            int(context_depth),
            round(float(distance_decay), 12),
            round(float(external_import_weight), 12),
            str(ordering),
        )

    def _matrix(
        self,
        *,
        context_depth: int = 1,
        distance_decay: float = 0.5,
        external_import_weight: float = 0.20,
        ordering: str = "qualified_name",
    ) -> Any:
        engine, _ = self._require()
        key = self._config_key(
            context_depth=context_depth,
            distance_decay=distance_decay,
            external_import_weight=external_import_weight,
            ordering=ordering,
        )
        with self._lock:
            cached = self._matrix_cache.get(key)
        if cached is not None:
            return cached
        try:
            result = engine.similarity_matrix(
                context_depth=context_depth,
                distance_decay=distance_decay,
                external_import_weight=external_import_weight,
                ordering=ordering,
            )
        except (KeyError, ValueError) as exc:
            raise AnalyzerIntegrationError(str(exc)) from exc
        with self._lock:
            self._matrix_cache[key] = result
        return result

    def similar(
        self,
        node_id: str,
        *,
        limit: int = 8,
        context_depth: int = 1,
        distance_decay: float = 0.5,
        external_import_weight: float = 0.20,
    ) -> dict[str, Any]:
        _, catalog = self._require()
        node = catalog.nodes.get(node_id)
        if node is None or node.node_type not in self.FUNCTION_TYPES:
            raise AnalyzerIntegrationError("Similarity is available for functions and methods only.")
        result = self._matrix(
            context_depth=context_depth,
            distance_decay=distance_decay,
            external_import_weight=external_import_weight,
        )
        try:
            index = result.labels.index(node_id)
        except ValueError as exc:
            raise AnalyzerIntegrationError(f"Function is not present in the similarity graph: {node_id}") from exc

        rows: list[dict[str, Any]] = []
        for other_id, score in zip(result.labels, result.matrix[index]):
            if other_id == node_id:
                continue
            other = catalog.nodes.get(other_id)
            rows.append({
                "id": other_id,
                "score": float(score),
                "name": other.name if other else other_id,
                "qualified_name": (other.qualified_name if other else None) or (other.name if other else other_id),
                "path": other.path if other else None,
                "line_start": (other.metadata or {}).get("line_start") if other else None,
            })
        rows.sort(key=lambda row: (-row["score"], row["qualified_name"], row["id"]))
        return {
            "id": node_id,
            "neighbors": rows[: max(1, int(limit))],
            "summary": asdict(result.summary),
            "config": asdict(result.config),
            "stale": self._stale,
        }

    def compare(self, left_id: str, right_id: str, **config: Any) -> dict[str, Any]:
        engine, _ = self._require()
        try:
            result = engine.compare(left_id, right_id, **config)
        except (KeyError, ValueError) as exc:
            raise AnalyzerIntegrationError(str(exc)) from exc
        result["stale"] = self._stale
        return result

    def matrix(self, *, include_matrix: bool = False, **config: Any) -> dict[str, Any]:
        result = self._matrix(**config)
        payload = {
            "labels": list(result.labels),
            "summary": asdict(result.summary),
            "config": asdict(result.config),
            "stale": self._stale,
        }
        if include_matrix:
            payload["matrix"] = [list(row) for row in result.matrix]
        return payload

    def duplicates(self, **config: Any) -> dict[str, Any]:
        engine, _ = self._require()
        try:
            result = engine.duplicate_candidates(**config)
        except (KeyError, ValueError) as exc:
            raise AnalyzerIntegrationError(str(exc)) from exc
        result["stale"] = self._stale
        return result

    def clusters(self, **config: Any) -> dict[str, Any]:
        engine, _ = self._require()
        try:
            result = engine.clusters(**config)
        except ValueError as exc:
            raise AnalyzerIntegrationError(str(exc)) from exc
        result["stale"] = self._stale
        return result
