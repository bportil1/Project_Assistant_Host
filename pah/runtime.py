"""Generic module runtime registration and discovery for PAH."""
from __future__ import annotations

from importlib import metadata
from typing import Any, Iterable, Mapping

from pah.contracts import ModuleContext, RuntimeLaunch, RuntimeStatus, coerce_runtime_launch, coerce_runtime_status


class RuntimeRegistryError(RuntimeError):
    pass


def _adapter_module_id(adapter: Any) -> str:
    if isinstance(adapter, Mapping):
        raw = adapter.get("module_id") or adapter.get("id")
    else:
        raw = getattr(adapter, "module_id", getattr(adapter, "id", None))
    module_id = str(raw or "").strip()
    if not module_id:
        raise RuntimeRegistryError("Runtime adapter must declare module_id")
    return module_id


def _adapter_method(adapter: Any, name: str):
    value = adapter.get(name) if isinstance(adapter, Mapping) else getattr(adapter, name, None)
    if not callable(value):
        raise RuntimeRegistryError(f"Runtime adapter for {_adapter_module_id(adapter)!r} does not implement {name}()")
    return value


class RuntimeRegistry:
    """Runtime adapters keyed by module identity, independent of scientific APIs."""

    def __init__(self, adapters: Iterable[Any] = ()):
        self._adapters: dict[str, Any] = {}
        self._discovery_errors: list[dict[str, str]] = []
        for adapter in adapters:
            self.register(adapter)

    def register(self, adapter: Any, *, replace: bool = False) -> Any:
        if callable(adapter) and not hasattr(adapter, "status") and not isinstance(adapter, Mapping):
            adapter = adapter()
        module_id = _adapter_module_id(adapter)
        if module_id in self._adapters and not replace:
            raise RuntimeRegistryError(f"Runtime adapter for {module_id!r} is already registered")
        self._adapters[module_id] = adapter
        return adapter

    def get(self, module_id: str) -> Any | None:
        return self._adapters.get(str(module_id))

    def module_ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))

    def status(self, module_id: str, context: ModuleContext | None = None) -> RuntimeStatus:
        module_id = str(module_id)
        adapter = self.get(module_id)
        if adapter is None:
            return RuntimeStatus(
                module_id=module_id,
                available=False,
                running=False,
                launchable=False,
                message="No runtime adapter is registered with PAH.",
            )
        result = _adapter_method(adapter, "status")(context=context)
        return coerce_runtime_status(result, module_id=module_id)

    def launch(self, module_id: str, context: ModuleContext | None = None, *, detached: bool = False) -> RuntimeLaunch:
        module_id = str(module_id)
        adapter = self.get(module_id)
        if adapter is None:
            raise RuntimeRegistryError(f"No runtime adapter is registered for {module_id!r}")
        result = _adapter_method(adapter, "launch")(context=context, detached=bool(detached))
        return coerce_runtime_launch(result, module_id=module_id)

    def shutdown(self, module_id: str, context: ModuleContext | None = None) -> None:
        adapter = self.get(str(module_id))
        if adapter is None:
            return
        method = adapter.get("shutdown") if isinstance(adapter, Mapping) else getattr(adapter, "shutdown", None)
        if callable(method):
            method(context=context)

    def shutdown_all(self, context: ModuleContext | None = None) -> None:
        for module_id in reversed(self.module_ids()):
            try:
                self.shutdown(module_id, context=context)
            except Exception:
                pass

    def discover_entry_points(self, *, group: str = "pah.runtimes") -> tuple[Any, ...]:
        discovered: list[Any] = []
        try:
            candidates = metadata.entry_points()
            candidates = candidates.select(group=group) if hasattr(candidates, "select") else candidates.get(group, ())
        except Exception as exc:  # pragma: no cover
            self._discovery_errors.append({"entry_point": group, "error": str(exc)})
            return ()
        for entry_point in candidates:
            try:
                adapter = entry_point.load()
                adapter = adapter() if callable(adapter) and not hasattr(adapter, "status") else adapter
                self.register(adapter, replace=True)
                discovered.append(adapter)
            except Exception as exc:
                self._discovery_errors.append({"entry_point": entry_point.name, "error": str(exc)})
        return tuple(discovered)

    def snapshot(self, context: ModuleContext | None = None) -> dict[str, Any]:
        return {
            "runtimes": [self.status(module_id, context=context).to_dict() for module_id in self.module_ids()],
            "discovery_errors": list(self._discovery_errors),
        }


class HostSurfaceRuntimeAdapter:
    """Bridge a PAH-owned full-tool surface into the generic runtime contract."""

    def __init__(self, module_id: str, surface: str, full_tools) -> None:
        self.module_id = str(module_id)
        self.surface = str(surface)
        self.full_tools = full_tools

    def status(self, *, context: ModuleContext | None = None) -> RuntimeStatus:
        info = self.full_tools.status().get("tools", {}).get(self.surface, {})
        return RuntimeStatus(
            module_id=self.module_id,
            available=True,
            running=bool(info.get("available")),
            launchable=True,
            url=info.get("url"),
            presentation="host_surface",
            message=info.get("error"),
            metadata={"surface": self.surface},
        )

    def launch(self, *, context: ModuleContext | None = None, detached: bool = False) -> RuntimeLaunch:
        info = self.full_tools.start(self.surface)
        if not info.get("available"):
            raise RuntimeRegistryError(info.get("error") or f"{self.module_id} runtime is unavailable")
        return RuntimeLaunch(
            module_id=self.module_id,
            launched=True,
            presentation="host_surface",
            surface=self.surface,
            url=info.get("url"),
            metadata={"detached": bool(detached)},
        )

    def shutdown(self, *, context: ModuleContext | None = None) -> None:
        self.full_tools.stop(self.surface)
