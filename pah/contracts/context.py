"""Host context passed to module adapters and lab orchestrators."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class ModuleContext:
    """Explicit host state that a module adapter may choose to consume.

    ``project_root``/``working_root``/``results_root`` remain for compatibility
    with existing modules.  ``resources`` is the workspace-aware contract:
    modules can request logical roles such as ``documents`` or ``datasets``
    without assuming that every research resource shares one physical root.
    """

    project_root: Path | None = None
    working_root: Path | None = None
    results_root: Path | None = None
    workspace_id: str | None = None
    workspace_name: str | None = None
    # Explicit identities; these do not imply ownership of another module's DB.
    host_project_id: str | None = None
    module_id: str | None = None
    module_instance_id: str | None = None
    module_local_project_id: str | None = None
    context_token: str | None = None
    resources: Mapping[str, Path] = field(default_factory=dict)
    host: str = "127.0.0.1"
    ports: Mapping[str, int] = field(default_factory=dict)
    theme: Mapping[str, str] = field(default_factory=dict)
    runtime: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("project_root", "working_root", "results_root"):
            raw = getattr(self, name)
            if raw is not None:
                object.__setattr__(self, name, Path(raw).expanduser().resolve())
        normalized_resources = {
            str(name): Path(path).expanduser().resolve()
            for name, path in dict(self.resources or {}).items()
            if path is not None
        }
        object.__setattr__(self, "resources", normalized_resources)
        if self.workspace_id is not None:
            object.__setattr__(self, "workspace_id", str(self.workspace_id).strip() or None)
        if self.workspace_name is not None:
            object.__setattr__(self, "workspace_name", str(self.workspace_name).strip() or None)
        for name in ("host_project_id", "module_id", "module_instance_id",
                     "module_local_project_id", "context_token"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, str(value).strip() or None)
        # Host project identity is the canonical repository root for current
        # PAH artifacts. A logical workspace may have no repository resource.
        if self.host_project_id is None and self.project_root is not None:
            object.__setattr__(self, "host_project_id", str(self.project_root))
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

    def resource(self, role: str, default: Path | None = None) -> Path | None:
        return self.resources.get(str(role), default)

    def for_module(self, module_id: str, *, local_project_id: str | None = None) -> "ModuleContext":
        """Bind a module slot without inventing the module's own project id.

        ``module_instance_id`` identifies a module slot in this PAH instance,
        not a scientific training run or a particular child PID.
        """
        from dataclasses import replace

        module = str(module_id or "").strip()
        if not module:
            raise ValueError("module_id must not be empty")
        instance = str(self.runtime.get("instance_id") or "").strip()
        return replace(
            self,
            module_id=module,
            module_instance_id=f"{instance}:{module}" if instance else None,
            module_local_project_id=local_project_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_root": str(self.project_root) if self.project_root else None,
            "working_root": str(self.working_root) if self.working_root else None,
            "results_root": str(self.results_root) if self.results_root else None,
            "workspace_id": self.workspace_id,
            "workspace_name": self.workspace_name,
            "host_project_id": self.host_project_id,
            "module_id": self.module_id,
            "module_instance_id": self.module_instance_id,
            "module_local_project_id": self.module_local_project_id,
            "context_token": self.context_token,
            "resources": {name: str(path) for name, path in self.resources.items()},
            "host": self.host,
            "ports": dict(self.ports),
            "theme": dict(self.theme),
            "runtime": dict(self.runtime),
        }
