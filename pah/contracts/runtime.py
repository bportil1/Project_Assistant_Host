"""Dependency-free runtime contracts for PAH module launch/status adapters."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimeStatus:
    module_id: str
    available: bool = False
    running: bool = False
    launchable: bool = False
    url: str | None = None
    presentation: str | None = None
    message: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "available": self.available,
            "running": self.running,
            "launchable": self.launchable,
            "url": self.url,
            "presentation": self.presentation,
            "message": self.message,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class RuntimeLaunch:
    module_id: str
    launched: bool = False
    presentation: str | None = None
    surface: str | None = None
    url: str | None = None
    message: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "launched": self.launched,
            "presentation": self.presentation,
            "surface": self.surface,
            "url": self.url,
            "message": self.message,
            "metadata": dict(self.metadata),
        }


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    raise TypeError("Runtime adapter result must be mapping-like")


def coerce_runtime_status(value: Any, *, module_id: str) -> RuntimeStatus:
    if isinstance(value, RuntimeStatus):
        return value
    payload = _mapping(value)
    return RuntimeStatus(
        module_id=str(payload.get("module_id") or module_id),
        available=bool(payload.get("available", False)),
        running=bool(payload.get("running", False)),
        launchable=bool(payload.get("launchable", payload.get("available", False))),
        url=str(payload.get("url")) if payload.get("url") else None,
        presentation=str(payload.get("presentation")) if payload.get("presentation") else None,
        message=str(payload.get("message")) if payload.get("message") else None,
        metadata=dict(payload.get("metadata") or {}),
    )


def coerce_runtime_launch(value: Any, *, module_id: str) -> RuntimeLaunch:
    if isinstance(value, RuntimeLaunch):
        return value
    payload = _mapping(value)
    return RuntimeLaunch(
        module_id=str(payload.get("module_id") or module_id),
        launched=bool(payload.get("launched", False)),
        presentation=str(payload.get("presentation")) if payload.get("presentation") else None,
        surface=str(payload.get("surface")) if payload.get("surface") else None,
        url=str(payload.get("url")) if payload.get("url") else None,
        message=str(payload.get("message")) if payload.get("message") else None,
        metadata=dict(payload.get("metadata") or {}),
    )
