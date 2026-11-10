"""UCA-01: in-memory navigation contract, independent of Flask and scientific engines.

A selection is a *claim* about a source revision, not a filesystem authorization.
Consumers must verify source_sha256 against the source before displaying evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from threading import RLock
from typing import Any, Mapping
from uuid import uuid4
import re

SCHEMA = "pah.source-selection@1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_IDENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_ALLOWED_PRODUCERS = frozenset({"editor", "pypique", "code_analyzer"})
_MAX_LINE = 2**31 - 1


class SourceSelectionError(ValueError):
    """Invalid, unverified, or out-of-scope selection payload."""


def _identity(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _IDENT.fullmatch(value):
        raise SourceSelectionError(f"invalid {name}")
    return value


def _relative_path(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise SourceSelectionError("invalid source path")
    if "\\" in value or "\x00" in value or "%" in value or ":" in value:
        raise SourceSelectionError("unsafe source path")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise SourceSelectionError("unsafe source path")
    return path.as_posix()


def _position(value: Any, name: str) -> int:
    if type(value) is not int or not 1 <= value <= _MAX_LINE:
        raise SourceSelectionError(f"invalid {name}")
    return value


@dataclass(frozen=True)
class SourceSelection:
    workspace_id: str
    project_id: str
    repository_id: str
    relative_path: str
    source_sha256: str
    producer: str
    start_line: int
    end_line: int
    start_column: int | None = None
    end_column: int | None = None
    artifact_id: str | None = None
    semantic_node_id: str | None = None

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> "SourceSelection":
        if not isinstance(raw, Mapping):
            raise SourceSelectionError("selection must be a mapping")
        if raw.get("schema") != SCHEMA:
            raise SourceSelectionError("unsupported selection schema")
        keys = {"schema", "workspace_id", "project_id", "repository_id", "relative_path",
                "source_sha256", "producer", "start_line", "end_line", "start_column",
                "end_column", "artifact_id", "semantic_node_id"}
        if set(raw) - keys:
            raise SourceSelectionError("unexpected selection fields")
        producer = _identity(raw.get("producer"), "producer")
        if producer not in _ALLOWED_PRODUCERS:
            raise SourceSelectionError("unsupported producer")
        sha = raw.get("source_sha256")
        if not isinstance(sha, str) or not _SHA256.fullmatch(sha):
            raise SourceSelectionError("verified source SHA-256 required")
        start = _position(raw.get("start_line"), "start line")
        end = _position(raw.get("end_line"), "end line")
        if end < start:
            raise SourceSelectionError("invalid line range")
        sc = raw.get("start_column")
        ec = raw.get("end_column")
        if (sc is None) != (ec is None):
            raise SourceSelectionError("both source columns must be supplied")
        if sc is not None:
            sc = _position(sc, "start column")
            ec = _position(ec, "end column")
            if start == end and ec < sc:
                raise SourceSelectionError("invalid column range")
        return cls(
            workspace_id=_identity(raw.get("workspace_id"), "workspace ID"),
            project_id=_identity(raw.get("project_id"), "project ID"),
            repository_id=_identity(raw.get("repository_id"), "repository ID"),
            relative_path=_relative_path(raw.get("relative_path")),
            source_sha256=sha, producer=producer,
            start_line=start, end_line=end,
            start_column=sc, end_column=ec,
            artifact_id=(_identity(raw["artifact_id"], "artifact ID") if raw.get("artifact_id") is not None else None),
            semantic_node_id=(_identity(raw["semantic_node_id"], "semantic node ID") if raw.get("semantic_node_id") is not None else None),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, **self.__dict__}


@dataclass(frozen=True)
class NavigationEvent:
    event_id: str
    epoch: int
    sequence: int
    selection: SourceSelection

    def to_dict(self) -> dict[str, Any]:
        return {"event_id": self.event_id, "epoch": self.epoch,
                "sequence": self.sequence, "selection": self.selection.to_dict()}


class SourceSelectionCoordinator:
    """An in-process, workspace-scoped event source; no IO or callbacks.

    UI/adapter code must not re-publish received events. Consumers can reject a
    previously seen event_id; switching context invalidates the old epoch.
    """

    def __init__(self, workspace_id: str, project_id: str, repository_id: str):
        self._lock = RLock()
        self._scope = tuple(_identity(v, n) for v, n in zip(
            (workspace_id, project_id, repository_id),
            ("workspace ID", "project ID", "repository ID")))
        self._epoch = 0
        self._sequence = 0
        self._last: NavigationEvent | None = None

    def switch_scope(self, workspace_id: str, project_id: str, repository_id: str) -> int:
        new_scope = tuple(_identity(v, n) for v, n in zip(
            (workspace_id, project_id, repository_id),
            ("workspace ID", "project ID", "repository ID")))
        with self._lock:
            if new_scope != self._scope:
                self._scope = new_scope
                self._epoch += 1
                self._sequence = 0
                self._last = None
            return self._epoch

    def publish(self, selection: SourceSelection, *, expected_epoch: int) -> NavigationEvent:
        if not isinstance(selection, SourceSelection):
            raise SourceSelectionError("expected validated selection")
        with self._lock:
            if type(expected_epoch) is not int or expected_epoch != self._epoch:
                raise SourceSelectionError("stale navigation epoch")
            if (selection.workspace_id, selection.project_id, selection.repository_id) != self._scope:
                raise SourceSelectionError("selection outside active repository scope")
            self._sequence += 1
            event = NavigationEvent(str(uuid4()), self._epoch, self._sequence, selection)
            self._last = event
            return event

    def snapshot(self) -> tuple[int, NavigationEvent | None]:
        with self._lock:
            return self._epoch, self._last

    def accepts(self, event: NavigationEvent, *, consumer: str,
                last_event_id: str | None = None) -> bool:
        """Checks dispatch eligibility; does not authorize source access."""
        _identity(consumer, "consumer")
        with self._lock:
            return bool(
                self._last is not None
                and event == self._last
                and event.epoch == self._epoch
                and event.selection.producer != consumer
                and event.event_id != last_event_id
            )
