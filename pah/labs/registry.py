"""Module and lab registries for PAH's goal-oriented collections."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from typing import Any, Iterable

from pah.contracts import ModuleManifest, WorkflowManifest, coerce_module_manifest


class RegistryError(RuntimeError):
    pass


class ModuleRegistry:
    """Runtime catalog of module manifests, independent of implementation type."""

    def __init__(self, manifests: Iterable[ModuleManifest] = ()):
        self._modules: dict[str, ModuleManifest] = {}
        self._discovery_errors: list[dict[str, str]] = []
        for manifest in manifests:
            self.register(manifest)

    def register(self, manifest: ModuleManifest | Any, *, replace: bool = False) -> ModuleManifest:
        normalized = coerce_module_manifest(manifest)
        if normalized.module_id in self._modules and not replace:
            raise RegistryError(f"Module {normalized.module_id!r} is already registered")
        self._modules[normalized.module_id] = normalized
        return normalized

    def get(self, module_id: str) -> ModuleManifest | None:
        return self._modules.get(str(module_id))

    def all(self) -> tuple[ModuleManifest, ...]:
        return tuple(sorted(self._modules.values(), key=lambda item: item.display_name.lower()))

    def for_collection(self, collection_id: str) -> tuple[ModuleManifest, ...]:
        return tuple(item for item in self.all() if item.belongs_to(collection_id))

    def providers(self, capability: str, *, collection_id: str | None = None) -> tuple[ModuleManifest, ...]:
        modules = self.for_collection(collection_id) if collection_id else self.all()
        return tuple(item for item in modules if item.supports(capability))

    def subset(self, module_ids) -> "ModuleRegistry":
        """Return a registry view containing only the requested installed modules."""
        selected = {str(value) for value in (module_ids or ())}
        return ModuleRegistry(item for item in self.all() if item.module_id in selected)

    def discover_entry_points(self, *, group: str = "pah.modules") -> tuple[ModuleManifest, ...]:
        """Discover optional modules without hard-coded imports in PAH.

        A third-party/standalone module can expose a manifest through the
        ``pah.modules`` entry-point group. The object may use PAH's dataclass or
        a module-local manifest with equivalent fields.
        """

        discovered: list[ModuleManifest] = []
        try:
            candidates = metadata.entry_points()
            candidates = candidates.select(group=group) if hasattr(candidates, "select") else candidates.get(group, ())
        except Exception as exc:  # pragma: no cover - importlib metadata failure is platform-specific
            self._discovery_errors.append({"entry_point": group, "error": str(exc)})
            return ()
        for entry_point in candidates:
            try:
                manifest = self.register(entry_point.load(), replace=True)
                discovered.append(manifest)
            except Exception as exc:
                self._discovery_errors.append({"entry_point": entry_point.name, "error": str(exc)})
        return tuple(discovered)

    def snapshot(self) -> dict[str, Any]:
        return {
            "modules": [item.to_dict() for item in self.all()],
            "discovery_errors": list(self._discovery_errors),
        }


@dataclass(frozen=True)
class LabManifest:
    lab_id: str
    display_name: str
    description: str = ""
    workflows: tuple[WorkflowManifest, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "lab_id": self.lab_id,
            "display_name": self.display_name,
            "description": self.description,
            "workflows": [workflow.to_dict() for workflow in self.workflows],
        }


class LabRegistry:
    def __init__(self, labs: Iterable[LabManifest] = ()):
        self._labs: dict[str, LabManifest] = {}
        for lab in labs:
            self.register(lab)

    def register(self, lab: LabManifest, *, replace: bool = False) -> LabManifest:
        if lab.lab_id in self._labs and not replace:
            raise RegistryError(f"Lab {lab.lab_id!r} is already registered")
        self._labs[lab.lab_id] = lab
        return lab

    def get(self, lab_id: str) -> LabManifest | None:
        return self._labs.get(str(lab_id))

    def all(self) -> tuple[LabManifest, ...]:
        return tuple(sorted(self._labs.values(), key=lambda item: item.display_name.lower()))

    def snapshot(self, modules: ModuleRegistry) -> dict[str, Any]:
        return {
            "labs": [self.lab_snapshot(lab.lab_id, modules) for lab in self.all()],
        }

    def lab_snapshot(self, lab_id: str, modules: ModuleRegistry) -> dict[str, Any]:
        lab = self.get(lab_id)
        if lab is None:
            raise RegistryError(f"Unknown PAH lab {lab_id!r}")
        payload = lab.to_dict()
        payload["modules"] = [item.to_dict() for item in modules.for_collection(lab_id)]
        return payload


class LabOrchestrator:
    """Resolve workflow capabilities to modules without domain-specific glue."""

    def __init__(self, lab: LabManifest, modules: ModuleRegistry):
        self.lab = lab
        self.modules = modules

    def providers(self, capability: str) -> tuple[ModuleManifest, ...]:
        return self.modules.providers(capability, collection_id=self.lab.lab_id)

    def resolve_step(self, step) -> dict[str, Any]:
        if step.provider_module:
            provider = self.modules.get(step.provider_module)
            if provider is None or not provider.belongs_to(self.lab.lab_id):
                return {"state": "missing_provider", "provider": None}
            if not provider.supports(step.capability):
                return {"state": "missing_capability", "provider": provider.to_dict()}
            return {"state": "resolved", "provider": provider.to_dict()}
        providers = self.providers(step.capability)
        if not providers:
            return {"state": "missing_provider", "provider": None}
        if len(providers) > 1:
            return {"state": "ambiguous", "providers": [item.to_dict() for item in providers]}
        return {"state": "resolved", "provider": providers[0].to_dict()}

    def workflow_snapshot(self, workflow: WorkflowManifest) -> dict[str, Any]:
        return {
            **workflow.to_dict(),
            "resolution": [
                {"step_id": step.step_id, **self.resolve_step(step)}
                for step in workflow.steps
            ],
        }
