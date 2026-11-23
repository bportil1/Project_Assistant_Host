"""Generic module runtime registration and discovery for PAH."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from importlib import metadata
from typing import Any, Iterable, Mapping

from pah.contracts import ModuleContext, RuntimeLaunch, RuntimeStatus, coerce_runtime_launch, coerce_runtime_status
from pah.module_processes import ModuleProcessLauncher


class RuntimeRegistryError(RuntimeError):
    pass


class ModuleInstanceNotFound(RuntimeRegistryError):
    """The requested opaque instance ID is not registered with this host."""


class ModuleInstanceConflict(RuntimeRegistryError):
    """An instance belongs to a different module or is not PAH-owned."""


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

    def __init__(self, adapters: Iterable[Any] = (), *, instance_runtime: Any | None = None):
        self._adapters: dict[str, Any] = {}
        self._discovery_errors: list[dict[str, str]] = []
        self._instance_runtime = instance_runtime
        self.process_launcher = ModuleProcessLauncher(instance_runtime) if instance_runtime is not None else None
        # Captured at process launch: never replaced by the mutable host selection.
        self._bound_process_contexts: dict[str, ModuleContext] = {}
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

    def _require_legacy_scope(self, module_id: str, context: ModuleContext | None) -> None:
        """Never route an explicitly selected child into a type-level adapter."""
        if context is None or context.module_instance_id is None or self._instance_runtime is None:
            return
        legacy_id = self._instance_runtime._default_module_instance_id(module_id)
        if context.module_instance_id != legacy_id:
            raise ModuleInstanceConflict(
                f"Instance {context.module_instance_id!r} requires instance-ID routing; "
                "the legacy module-type adapter cannot operate on it"
            )
        if context.module_id is not None and context.module_id != module_id:
            raise ModuleInstanceConflict("Module context and requested module type disagree")

    def status(self, module_id: str, context: ModuleContext | None = None) -> RuntimeStatus:
        module_id = str(module_id)
        self._require_legacy_scope(module_id, context)
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
        self._require_legacy_scope(module_id, context)
        adapter = self.get(module_id)
        if adapter is None:
            raise RuntimeRegistryError(f"No runtime adapter is registered for {module_id!r}")
        result = _adapter_method(adapter, "launch")(context=context, detached=bool(detached))
        launch = coerce_runtime_launch(result, module_id=module_id)
        if self._instance_runtime is not None and launch.launched:
            raw_pid = dict(launch.metadata or {}).get("pid")
            try:
                child_pid = int(raw_pid) if raw_pid is not None else None
            except (TypeError, ValueError):
                child_pid = None
            self._instance_runtime.register_module_runtime(
                module_id,
                pid=child_pid,
                metadata={
                    "presentation": launch.presentation,
                    "surface": launch.surface,
                    "url": launch.url,
                    **dict(launch.metadata or {}),
                    # Host scope is recorded independently of optional adapter
                    # metadata, so a later project switch can identify the
                    # original binding without reading a module-private DB.
                    "workspace_id": context.workspace_id if context else None,
                    "host_project_id": context.host_project_id if context else None,
                    "module_instance_id": context.module_instance_id if context else None,
                    "module_local_project_id": context.module_local_project_id if context else None,
                },
            )
        return launch

    def can_launch_instance(self, module_id: str) -> bool:
        """Does a trusted module adapter declare its own independent process spec?"""
        adapter = self.get(module_id)
        if adapter is None:
            return False
        method = adapter.get("process_launch_spec") if isinstance(adapter, Mapping) else getattr(adapter, "process_launch_spec", None)
        return callable(method) and self.process_launcher is not None

    def launch_instance(self, module_id: str, *, context: ModuleContext) -> dict[str, Any]:
        """Launch via a module-owned recipe; browser callers never provide argv/env.

        The module owns its project/data semantics. The host only creates a new
        process, assigns runtime resources, and captures the original context.
        """
        if not self.can_launch_instance(module_id):
            raise RuntimeRegistryError(
                f"{module_id!r} has no independent process launch contract; "
                "its legacy launch still uses the module-type route"
            )
        adapter = self.get(module_id)
        method = adapter.get("process_launch_spec") if isinstance(adapter, Mapping) else adapter.process_launch_spec
        spec = method(context=context)
        if not isinstance(spec, Mapping):
            raise RuntimeRegistryError("process_launch_spec must return a mapping")
        allowed = {"command", "cwd", "env", "requested_port", "ui_path"}
        if set(spec) - allowed or "command" not in spec:
            raise RuntimeRegistryError("process_launch_spec must contain command and only documented launch keys")
        options = {key: spec[key] for key in allowed - {"command"} if key in spec}
        from .module_processes import ModuleProcessError
        try:
            return self.launch_process(module_id, spec["command"], context=context, **options)
        except (ModuleProcessError, TypeError, ValueError) as exc:
            raise RuntimeRegistryError(f"Could not launch independent {module_id!r} instance: {exc}") from exc

    def launch_process(
        self, module_id: str, command, *, context: ModuleContext | None = None, **kwargs
    ) -> dict[str, Any]:
        """Spawn a trusted argv with a fixed, opaque host-context binding.

        The adapter owns what a workspace means. PAH only records its identity;
        it must never substitute the currently selected workspace afterwards.
        """
        if self.process_launcher is None:
            raise RuntimeRegistryError("A host InstanceRuntime is required to launch child processes")
        module = str(module_id)
        if context is not None:
            if context.module_id is not None and context.module_id != module:
                raise ModuleInstanceConflict("Module context and requested module type disagree")
            if "workspace_id" in kwargs and kwargs["workspace_id"] != context.workspace_id:
                raise ModuleInstanceConflict("Explicit workspace differs from the launch context")
            if "host_project_id" in kwargs and kwargs["host_project_id"] != context.host_project_id:
                raise ModuleInstanceConflict("Explicit host project differs from the launch context")
            kwargs.setdefault("workspace_id", context.workspace_id)
            kwargs.setdefault("host_project_id", context.host_project_id)
            default_id = self._instance_runtime._default_module_instance_id(module)
            selected = context.module_instance_id
            if selected and selected != default_id:
                if kwargs.get("module_instance_id", selected) != selected:
                    raise ModuleInstanceConflict("Explicit module instance differs from the launch context")
                kwargs.setdefault("module_instance_id", selected)
        record = self.process_launcher.launch(module, command, **kwargs)
        if context is not None:
            identity = record["module_instance_id"]
            bound = replace(deepcopy(context), module_id=module, module_instance_id=identity)
            self._bound_process_contexts[identity] = bound
        return record

    def _reap_processes(self) -> None:
        if self.process_launcher is not None:
            for identity in self.process_launcher.reap_exited():
                self._bound_process_contexts.pop(identity, None)

    def route_instance(self, module_instance_id: str, *, module_id: str | None = None) -> dict[str, Any]:
        """Resolve exactly one local instance; never fall back to module type."""
        self._reap_processes()
        if self._instance_runtime is None:
            raise ModuleInstanceNotFound("This PAH host has no instance runtime")
        identity = str(module_instance_id or "").strip()
        record = self._instance_runtime.module_instances().get(identity)
        if record is None:
            raise ModuleInstanceNotFound(f"Module instance {identity!r} is not registered with this host")
        if module_id is not None and record["module_id"] != str(module_id):
            raise ModuleInstanceConflict(
                f"Module instance {identity!r} belongs to {record['module_id']!r}, not {module_id!r}"
            )
        if record.get("owner_instance_id") != self._instance_runtime.instance_id:
            raise ModuleInstanceConflict("Module instance belongs to a different PAH host")
        meta = record.get("metadata") or {}
        managed = self.process_launcher is not None and self.process_launcher.owns(identity)
        return {
            "module_id": record["module_id"],
            "module_instance_id": identity,
            "owner_instance_id": record["owner_instance_id"],
            "pid": record.get("pid"),
            "workspace_id": meta.get("workspace_id"),
            "host_project_id": meta.get("host_project_id"),
            "presentation": meta.get("presentation"),
            "host": meta.get("host"),
            "port": meta.get("port"),
            "url": meta.get("url"),
            "runtime_dir": meta.get("runtime_dir"),
            "log_file": meta.get("log_file"),
            "managed_process": bool(managed),
            "lifecycle": "running" if managed else (meta.get("lifecycle") or "legacy"),
        }

    def instance_context(self, module_instance_id: str) -> ModuleContext:
        """Return the original immutable launch context, not the current host context.

        Available for processes launched with an explicit ModuleContext. We do
        not invent a context for older type-level adapters or argv-only launches.
        """
        self.route_instance(module_instance_id)
        identity = str(module_instance_id)
        if identity not in self._bound_process_contexts:
            raise ModuleInstanceConflict(f"Module instance {identity!r} has no captured launch context")
        return deepcopy(self._bound_process_contexts[identity])

    def stop_process(self, module_instance_id: str, **kwargs) -> bool:
        """Stop exactly one owned child, never a legacy type-level adapter."""
        route = self.route_instance(module_instance_id)
        if not route["managed_process"]:
            raise ModuleInstanceConflict(
                "This instance is not a PAH-owned child; use the legacy module-type shutdown route"
            )
        assert self.process_launcher is not None
        stopped = self.process_launcher.stop(module_instance_id, **kwargs)
        self._bound_process_contexts.pop(str(module_instance_id), None)
        return stopped

    def instances(self, module_id: str | None = None) -> dict[str, dict[str, Any]]:
        """Read-only live registration view; adapters remain keyed by type.

        This reports instance identities already registered with the host. It
        does not imply that a given adapter supports multiple child processes;
        that capability is introduced by the process launcher in MI-03.
        """
        if self._instance_runtime is None:
            return {}
        self._reap_processes()
        return self._instance_runtime.module_instances(module_id)

    def artifacts(self, module_id: str, context: ModuleContext | None = None) -> tuple[Any, ...] | None:
        """Return artifacts advertised by a runtime adapter, if it supports discovery.

        ``None`` means the adapter does not implement artifact discovery.  An empty
        tuple means it does implement discovery and currently has no artifacts.
        Domain modules return dependency-free mappings; PAH coerces those mappings
        into its artifact contract at the host boundary.
        """
        self._require_legacy_scope(str(module_id), context)
        adapter = self.get(str(module_id))
        if adapter is None:
            return None
        method = adapter.get("artifacts") if isinstance(adapter, Mapping) else getattr(adapter, "artifacts", None)
        if not callable(method):
            return None
        result = method(context=context)
        if result is None:
            return ()
        if isinstance(result, Mapping):
            result = result.get("artifacts", ())
        return tuple(result or ())

    def shutdown(self, module_id: str, context: ModuleContext | None = None) -> None:
        self._require_legacy_scope(str(module_id), context)
        adapter = self.get(str(module_id))
        if adapter is None:
            return
        method = adapter.get("shutdown") if isinstance(adapter, Mapping) else getattr(adapter, "shutdown", None)
        if callable(method):
            method(context=context)
        if self._instance_runtime is not None:
            self._instance_runtime.unregister_module_runtime(str(module_id))

    def shutdown_all(self, context: ModuleContext | None = None) -> None:
        try:
            for module_id in reversed(self.module_ids()):
                try:
                    self.shutdown(module_id, context=context)
                except Exception:
                    pass
        finally:
            # Generic child instances are not owned by legacy adapter slots.
            if self.process_launcher is not None:
                self.process_launcher.stop_all()
            self._bound_process_contexts.clear()

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


def register_host_surface_fallbacks(registry: "RuntimeRegistry", full_tools: Any) -> tuple[str, ...]:
    """Register hosted compatibility adapters only when no module adapter exists.

    Installed submodules' `pah.runtimes` entry points are authoritative. The
    iframe host is a temporary fallback, not a reason to replace them.
    """
    added: list[str] = []
    for module_id, surface in (
        ("code_analyzer", "analysis"),
        ("tech_documents", "documents"),
        ("reference_manager", "references"),
    ):
        if registry.get(module_id) is None:
            registry.register(HostSurfaceRuntimeAdapter(module_id, surface, full_tools))
            added.append(module_id)
    return tuple(added)


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
