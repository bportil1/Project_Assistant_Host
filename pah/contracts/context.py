"""Host context passed to module adapters and lab orchestrators."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ModuleContext:
    """Explicit host state that a module adapter may choose to consume."""

    project_root: Path | None = None
    working_root: Path | None = None
    results_root: Path | None = None
    host: str = "127.0.0.1"
    ports: Mapping[str, int] = field(default_factory=dict)
    theme: Mapping[str, str] = field(default_factory=dict)
    runtime: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("project_root", "working_root", "results_root"):
            raw = getattr(self, name)
            if raw is not None:
                object.__setattr__(self, name, Path(raw).expanduser().resolve())
        host = str(self.host or "").strip()
        if not host:
            raise ValueError("host must not be empty")
        object.__setattr__(self, "host", host)
        ports = {str(key): int(value) for key, value in dict(self.ports or {}).items()}
        for name, port in ports.items():
            if port < 1 or port > 65535:
                raise ValueError(f"port {name!r} must be between 1 and 65535")
        object.__setattr__(self, "ports", ports)
        object.__setattr__(self, "theme", {str(k): str(v) for k, v in dict(self.theme or {}).items()})
        object.__setattr__(self, "runtime", dict(self.runtime or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": str(self.project_root) if self.project_root else None,
            "working_root": str(self.working_root) if self.working_root else None,
            "results_root": str(self.results_root) if self.results_root else None,
            "host": self.host,
            "ports": dict(self.ports),
            "theme": dict(self.theme),
            "runtime": dict(self.runtime),
        }
