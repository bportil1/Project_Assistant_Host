"""Small, dependency-free contracts for PAH modules.

These types describe *what* a module offers to the host. They intentionally do
not prescribe how a module is implemented: a module may own a web UI, expose a
headless Python API, provide a Flask adapter, or support several surfaces.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Mapping


def _clean_token(value: str, *, field_name: str) -> str:
    token = str(value or "").strip()
    if not token:
        raise ValueError(f"{field_name} must not be empty")
    return token


def _clean_tokens(values) -> tuple[str, ...]:
    result: list[str] = []
    for value in values or ():
        token = str(value or "").strip()
        if token and token not in result:
            result.append(token)
    return tuple(result)


@dataclass(frozen=True)
class ModuleManifest:
    """Host-facing identity and capability declaration for one PAH module."""

    module_id: str
    display_name: str
    version: str | None = None
    description: str = ""
    collections: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    interfaces: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "module_id", _clean_token(self.module_id, field_name="module_id"))
        object.__setattr__(self, "display_name", _clean_token(self.display_name, field_name="display_name"))
        object.__setattr__(self, "version", str(self.version).strip() if self.version not in {None, ""} else None)
        object.__setattr__(self, "description", str(self.description or "").strip())
        object.__setattr__(self, "collections", _clean_tokens(self.collections))
        object.__setattr__(self, "capabilities", _clean_tokens(self.capabilities))
        object.__setattr__(self, "interfaces", _clean_tokens(self.interfaces))
        object.__setattr__(self, "metadata", dict(self.metadata or {}))

    def supports(self, capability: str) -> bool:
        return str(capability) in self.capabilities

    def has_interface(self, interface: str) -> bool:
        return str(interface) in self.interfaces

    def belongs_to(self, collection: str) -> bool:
        return str(collection) in self.collections

    def to_dict(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "display_name": self.display_name,
            "version": self.version,
            "description": self.description,
            "collections": list(self.collections),
            "capabilities": list(self.capabilities),
            "interfaces": list(self.interfaces),
            "metadata": dict(self.metadata),
        }


def coerce_module_manifest(value: Any) -> ModuleManifest:
    """Convert a module-owned manifest into PAH's dependency-free contract.

    External modules are not required to import :mod:`pah`. An entry point may
    therefore return a mapping, another dataclass, or an object exposing the
    expected attributes. This keeps dependency direction PAH -> adapter rather
    than forcing scientific modules to depend on the host package.
    """

    if isinstance(value, ModuleManifest):
        return value
    if callable(value) and not isinstance(value, type):
        value = value()
    if isinstance(value, ModuleManifest):
        return value
    if hasattr(value, "to_dict") and callable(value.to_dict):
        value = value.to_dict()
    elif is_dataclass(value):
        value = asdict(value)
    elif not isinstance(value, Mapping):
        names = (
            "module_id",
            "id",
            "display_name",
            "name",
            "version",
            "description",
            "collections",
            "capabilities",
            "interfaces",
            "metadata",
        )
        value = {name: getattr(value, name) for name in names if hasattr(value, name)}

    if not isinstance(value, Mapping):
        raise TypeError("PAH module manifest entry point must return a manifest-like value")

    module_id = value.get("module_id", value.get("id"))
    display_name = value.get("display_name", value.get("name", module_id))
    return ModuleManifest(
        module_id=str(module_id or ""),
        display_name=str(display_name or ""),
        version=value.get("version"),
        description=str(value.get("description") or ""),
        collections=tuple(value.get("collections") or ()),
        capabilities=tuple(value.get("capabilities") or ()),
        interfaces=tuple(value.get("interfaces") or ()),
        metadata=dict(value.get("metadata") or {}),
    )
