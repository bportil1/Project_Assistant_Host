from __future__ import annotations

import json
import os
import re
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4


class WorkspaceError(ValueError):
    pass


RESOURCE_ROLES = (
    "repository",
    "documents",
    "papers",
    "bibliography",
    "datasets",
    "assets",
    "notes",
    "outputs",
    "archive",
)

SYNC_POLICIES = (
    "externally_managed",
    "local_only",
    "generated",
    "excluded",
)


def _clean_id(value: str, *, field_name: str) -> str:
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", str(value or "").strip().lower()).strip("-._")
    if not cleaned:
        raise WorkspaceError(f"{field_name} must not be empty.")
    return cleaned


def _relative_resource_path(value: str | Path | None) -> str:
    raw = str(value or "").strip()
    if not raw or raw == ".":
        return ""
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise WorkspaceError("Workspace resource subpaths must stay relative to their registered root.")
    return candidate.as_posix().strip("/")


class WorkspaceManager:
    """Persist PAH research-workspace state outside user projects.

    PAH historically treated a workspace as one physical directory.  The
    research-workspace model keeps that interface working while adding a
    logical layer:

        research workspace -> resource role -> registered root -> local path

    Workspace definitions therefore keep stable logical root identifiers while
    each PAH installation stores its own local filesystem mapping for those
    roots.  Existing callers may continue to use ``root``/``open``; ``root`` is
    the active workspace's repository resource when one is configured.
    """

    schema_version = 2

    def __init__(self, state_dir: str | Path | None = None) -> None:
        default_dir = Path.home() / ".local" / "share" / "pah"
        self.state_dir = Path(state_dir or os.environ.get("PAH_STATE_DIR", default_dir)).expanduser()
        self.state_file = self.state_dir / "state.json"
        self._lock = RLock()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    @classmethod
    def _empty_state(cls) -> dict[str, Any]:
        return {
            "schema_version": cls.schema_version,
            "current_root": None,
            "recent_roots": [],
            "environments": {},
            "active_workspace_id": None,
            "research_workspaces": {},
            "shared_roots": {},
        }

    def _load(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return self._empty_state()
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return self._empty_state()
        defaults = self._empty_state()
        for key, value in defaults.items():
            data.setdefault(key, value)
        data["schema_version"] = self.schema_version
        if not isinstance(data.get("research_workspaces"), dict):
            data["research_workspaces"] = {}
        if not isinstance(data.get("shared_roots"), dict):
            data["shared_roots"] = {}
        return data

    def _save(self) -> None:
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        tmp.replace(self.state_file)

    def _workspace(self, workspace_id: str | None = None) -> dict[str, Any] | None:
        selected = workspace_id or self._state.get("active_workspace_id")
        if not selected:
            return None
        return self._state.get("research_workspaces", {}).get(str(selected))

    def _require_workspace(self, workspace_id: str | None = None) -> dict[str, Any]:
        workspace = self._workspace(workspace_id)
        if workspace is None:
            requested = workspace_id or self._state.get("active_workspace_id") or "<active>"
            raise WorkspaceError(f"Unknown research workspace: {requested}")
        return workspace

    def _unique_workspace_id(self, preferred: str) -> str:
        base = _clean_id(preferred, field_name="workspace id")
        existing = self._state.get("research_workspaces", {})
        if base not in existing:
            return base
        for _ in range(100):
            candidate = f"{base}-{uuid4().hex[:6]}"
            if candidate not in existing:
                return candidate
        raise WorkspaceError("Could not allocate a unique workspace id.")

    @property
    def active_workspace_id(self) -> str | None:
        value = self._state.get("active_workspace_id")
        return str(value) if value else None

    @property
    def active_workspace_name(self) -> str | None:
        workspace = self._workspace()
        return str(workspace.get("name")) if workspace else None

    def _resolved_resource(self, role: str, workspace_id: str | None = None) -> dict[str, Any] | None:
        role = str(role or "").strip().lower()
        if role not in RESOURCE_ROLES:
            raise WorkspaceError(f"Unknown workspace resource role: {role}")
        workspace = self._workspace(workspace_id)
        if workspace is None:
            return None
        binding = dict(workspace.get("resources", {}).get(role) or {})
        root_id = binding.get("root_id")
        if not root_id:
            return None
        registered = self._state.get("shared_roots", {}).get(root_id)
        if not isinstance(registered, dict):
            return {
                "role": role,
                "root_id": root_id,
                "relative_path": binding.get("relative_path", ""),
                "path": None,
                "available": False,
                "status": "unmapped_root",
            }
        raw_local = str(registered.get("local_path") or "").strip()
        if not raw_local:
            resolved = None
        else:
            base = Path(raw_local).expanduser()
            relative = _relative_resource_path(binding.get("relative_path"))
            resolved = (base / relative).resolve() if relative else base.resolve()
        available = bool(resolved and resolved.exists() and resolved.is_dir())
        return {
            "role": role,
            "root_id": root_id,
            "root_name": registered.get("name") or root_id,
            "relative_path": binding.get("relative_path", ""),
            "path": str(resolved) if resolved else None,
            "available": available,
            "status": "available" if available else "unavailable",
            "sync_policy": registered.get("sync_policy", "externally_managed"),
            "transport_hint": registered.get("transport_hint"),
        }

    def resolve_resource(self, role: str, *, workspace_id: str | None = None) -> Path | None:
        resource = self._resolved_resource(role, workspace_id)
        if not resource or not resource.get("available") or not resource.get("path"):
            return None
        return Path(resource["path"])

    def require_resource(self, role: str, *, workspace_id: str | None = None) -> Path:
        path = self.resolve_resource(role, workspace_id=workspace_id)
        if path is None:
            raise WorkspaceError(f"Workspace resource {role!r} is not mapped to an available directory.")
        return path

    def resolved_resources(self, *, workspace_id: str | None = None) -> dict[str, Path]:
        result: dict[str, Path] = {}
        for role in RESOURCE_ROLES:
            path = self.resolve_resource(role, workspace_id=workspace_id)
            if path is not None:
                result[role] = path
        return result

    @property
    def root(self) -> Path | None:
        repository = self.resolve_resource("repository")
        if repository is not None:
            return repository
        raw = self._state.get("current_root")
        if not raw:
            return None
        path = Path(raw)
        return path.resolve() if path.is_dir() else None

    def require_root(self) -> Path:
        root = self.root
        if root is None:
            raise WorkspaceError("No repository root is available for the active workspace.")
        return root

    def register_root(
        self,
        root_id: str,
        *,
        name: str | None = None,
        role: str | None = None,
        path: str | Path | None = None,
        sync_policy: str = "externally_managed",
        transport_hint: str | None = None,
    ) -> dict[str, Any]:
        root_id = _clean_id(root_id, field_name="root id")
        normalized_role = str(role or "").strip().lower() or None
        if normalized_role is not None and normalized_role not in RESOURCE_ROLES:
            raise WorkspaceError(f"Unknown workspace resource role: {normalized_role}")
        normalized_policy = str(sync_policy or "externally_managed").strip().lower()
        if normalized_policy not in SYNC_POLICIES:
            raise WorkspaceError(f"Unknown sync policy: {normalized_policy}")
        local_path = None
        if path is not None and str(path).strip():
            candidate = Path(path).expanduser()
            if candidate.exists() and not candidate.is_dir():
                raise WorkspaceError(f"Registered root is not a directory: {candidate}")
            local_path = str(candidate.resolve())
        with self._lock:
            roots = self._state.setdefault("shared_roots", {})
            existing = dict(roots.get(root_id) or {})
            roots[root_id] = {
                "id": root_id,
                "name": str(name or existing.get("name") or root_id).strip(),
                "role": normalized_role if normalized_role is not None else existing.get("role"),
                "local_path": local_path if path is not None else existing.get("local_path"),
                "sync_policy": normalized_policy,
                "transport_hint": (
                    str(transport_hint).strip() if transport_hint is not None and str(transport_hint).strip() else None
                ),
            }
            self._save()
        return self.shared_root(root_id)

    def shared_root(self, root_id: str) -> dict[str, Any]:
        root_id = _clean_id(root_id, field_name="root id")
        raw = self._state.get("shared_roots", {}).get(root_id)
        if not isinstance(raw, dict):
            raise WorkspaceError(f"Unknown registered root: {root_id}")
        local_path = raw.get("local_path")
        candidate = Path(local_path).expanduser() if local_path else None
        return {
            **raw,
            "available": bool(candidate and candidate.exists() and candidate.is_dir()),
        }

    def create_workspace(
        self,
        name: str,
        *,
        workspace_id: str | None = None,
        activate: bool = False,
    ) -> dict[str, Any]:
        display_name = str(name or "").strip()
        if not display_name:
            raise WorkspaceError("Workspace name must not be empty.")
        with self._lock:
            selected_id = _clean_id(workspace_id, field_name="workspace id") if workspace_id else self._unique_workspace_id(display_name)
            if selected_id in self._state.get("research_workspaces", {}):
                raise WorkspaceError(f"Research workspace already exists: {selected_id}")
            self._state.setdefault("research_workspaces", {})[selected_id] = {
                "id": selected_id,
                "name": display_name,
                "resources": {},
            }
            if activate:
                self._state["active_workspace_id"] = selected_id
                self._state["current_root"] = None
            self._save()
        return self.workspace_snapshot(selected_id)

    def activate(self, workspace_id: str) -> dict[str, Any]:
        workspace_id = _clean_id(workspace_id, field_name="workspace id")
        with self._lock:
            self._require_workspace(workspace_id)
            self._state["active_workspace_id"] = workspace_id
            repository = self.resolve_resource("repository", workspace_id=workspace_id)
            self._state["current_root"] = str(repository) if repository else None
            if repository:
                recent = [p for p in self._state.get("recent_roots", []) if p != str(repository)]
                recent.insert(0, str(repository))
                self._state["recent_roots"] = recent[:12]
            self._save()
        return self.workspace_snapshot(workspace_id)

    def set_resource(
        self,
        workspace_id: str,
        role: str,
        *,
        root_id: str,
        relative_path: str | Path | None = None,
    ) -> dict[str, Any]:
        workspace_id = _clean_id(workspace_id, field_name="workspace id")
        role = str(role or "").strip().lower()
        if role not in RESOURCE_ROLES:
            raise WorkspaceError(f"Unknown workspace resource role: {role}")
        root_id = _clean_id(root_id, field_name="root id")
        relative = _relative_resource_path(relative_path)
        with self._lock:
            workspace = self._require_workspace(workspace_id)
            if root_id not in self._state.get("shared_roots", {}):
                raise WorkspaceError(f"Unknown registered root: {root_id}")
            workspace.setdefault("resources", {})[role] = {
                "root_id": root_id,
                "relative_path": relative,
            }
            if workspace_id == self.active_workspace_id and role == "repository":
                repository = self.resolve_resource("repository", workspace_id=workspace_id)
                self._state["current_root"] = str(repository) if repository else None
            self._save()
        return self.workspace_snapshot(workspace_id)

    def remove_resource(self, workspace_id: str, role: str) -> dict[str, Any]:
        workspace_id = _clean_id(workspace_id, field_name="workspace id")
        role = str(role or "").strip().lower()
        if role not in RESOURCE_ROLES:
            raise WorkspaceError(f"Unknown workspace resource role: {role}")
        with self._lock:
            workspace = self._require_workspace(workspace_id)
            workspace.setdefault("resources", {}).pop(role, None)
            if workspace_id == self.active_workspace_id and role == "repository":
                self._state["current_root"] = None
            self._save()
        return self.workspace_snapshot(workspace_id)

    def open(self, path: str | Path) -> Path:
        """Open a directory through the legacy UI and promote it to a workspace.

        This keeps the existing PAH interaction intact while ensuring every new
        directory-based session also has a logical research-workspace identity.
        """
        candidate = Path(path).expanduser().resolve()
        if not candidate.exists():
            raise WorkspaceError(f"Workspace does not exist: {candidate}")
        if not candidate.is_dir():
            raise WorkspaceError(f"Workspace is not a directory: {candidate}")
        with self._lock:
            matched_id = None
            for workspace_id in self._state.get("research_workspaces", {}):
                repository = self.resolve_resource("repository", workspace_id=workspace_id)
                if repository == candidate:
                    matched_id = workspace_id
                    break
            if matched_id is None:
                matched_id = self._unique_workspace_id(candidate.name or "workspace")
                root_id = self._unique_root_id(f"{matched_id}-repository")
                self._state.setdefault("shared_roots", {})[root_id] = {
                    "id": root_id,
                    "name": f"{candidate.name or matched_id} Repository",
                    "role": "repository",
                    "local_path": str(candidate),
                    "sync_policy": "externally_managed",
                    "transport_hint": "git",
                }
                self._state.setdefault("research_workspaces", {})[matched_id] = {
                    "id": matched_id,
                    "name": candidate.name or matched_id,
                    "resources": {
                        "repository": {"root_id": root_id, "relative_path": ""},
                    },
                }
            self._state["active_workspace_id"] = matched_id
            self._state["current_root"] = str(candidate)
            recent = [p for p in self._state.get("recent_roots", []) if p != str(candidate)]
            recent.insert(0, str(candidate))
            self._state["recent_roots"] = recent[:12]
            self._save()
        return candidate

    def _unique_root_id(self, preferred: str) -> str:
        base = _clean_id(preferred, field_name="root id")
        existing = self._state.get("shared_roots", {})
        if base not in existing:
            return base
        for _ in range(100):
            candidate = f"{base}-{uuid4().hex[:6]}"
            if candidate not in existing:
                return candidate
        raise WorkspaceError("Could not allocate a unique registered-root id.")

    def current_environment(self) -> str | None:
        root = self.root
        if root is None:
            return None
        return self._state.get("environments", {}).get(str(root))

    def set_environment(self, path: str | Path | None) -> str | None:
        root = self.require_root()
        with self._lock:
            envs = self._state.setdefault("environments", {})
            if path is None:
                envs.pop(str(root), None)
                selected = None
            else:
                candidate = Path(path).expanduser()
                if not candidate.is_absolute():
                    candidate = root / candidate
                candidate = candidate.resolve()
                if not candidate.exists() or not candidate.is_dir():
                    raise WorkspaceError(f"Environment directory does not exist: {candidate}")
                envs[str(root)] = str(candidate)
                selected = str(candidate)
            self._save()
        return selected

    def workspace_snapshot(self, workspace_id: str | None = None) -> dict[str, Any]:
        workspace = self._workspace(workspace_id)
        if workspace is None:
            return {}
        selected_id = str(workspace["id"])
        resources: dict[str, Any] = {}
        for role in RESOURCE_ROLES:
            resolved = self._resolved_resource(role, selected_id)
            if resolved is not None:
                resources[role] = resolved
        return {
            "id": selected_id,
            "name": workspace.get("name") or selected_id,
            "active": selected_id == self.active_workspace_id,
            "resources": resources,
        }

    def catalog_snapshot(self) -> dict[str, Any]:
        workspaces = [
            self.workspace_snapshot(workspace_id)
            for workspace_id in sorted(self._state.get("research_workspaces", {}))
        ]
        roots = [
            self.shared_root(root_id)
            for root_id in sorted(self._state.get("shared_roots", {}))
        ]
        return {
            "schema_version": self.schema_version,
            "resource_roles": list(RESOURCE_ROLES),
            "sync_policies": list(SYNC_POLICIES),
            "active_workspace_id": self.active_workspace_id,
            "workspaces": workspaces,
            "shared_roots": roots,
        }

    def snapshot(self) -> dict[str, Any]:
        root = self.root
        return {
            "root": str(root) if root else None,
            "recent": list(self._state.get("recent_roots", [])),
            "environment": self.current_environment(),
            "workspace_id": self.active_workspace_id,
            "workspace_name": self.active_workspace_name,
            "resources": self.workspace_snapshot().get("resources", {}),
        }
