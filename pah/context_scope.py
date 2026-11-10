"""Instance-local workspace selection identity and optimistic request guard.

PAH workspace preferences remain JSON-owned by :class:`WorkspaceManager`.
A context token is ephemeral: it is not a project identifier, authentication
credential, or permission grant. It protects a selection made in one browser
view from being applied after this PAH *instance* changes its active scope.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from typing import Any, Mapping, Iterable
from uuid import uuid4
import json


class StaleWorkspaceContext(ValueError):
    """The selection seen by the caller is no longer this instance's selection."""


@dataclass(frozen=True)
class ContextSelection:
    instance_id: str
    workspace_id: str | None
    host_project_id: str | None
    revision: int
    context_token: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "workspace_id": self.workspace_id,
            "host_project_id": self.host_project_id,
            "revision": self.revision,
            "context_token": self.context_token,
        }


class WorkspaceContextGuard:
    """Track changes to the active workspace binding of one PAH instance.

    A token changes when the workspace selection, repository resource, any
    resource binding, or enabled-module profile changes. Changes in unrelated
    *inactive* workspaces do not invalidate this instance's selection.
    """

    def __init__(self, instance_id: str) -> None:
        self.instance_id = str(instance_id)
        if not self.instance_id.strip():
            raise ValueError("instance_id is required")
        self._lock = RLock()
        self._signature: str | None = None
        self._revision = 0
        self._token = ""
        self._selection: ContextSelection | None = None

    def capture(
        self,
        *,
        workspace_id: str | None,
        project_root: str | Path | None,
        resources: Mapping[str, Any] | None = None,
        enabled_modules: Iterable[str] = (),
    ) -> ContextSelection:
        project = str(Path(project_root).expanduser().resolve()) if project_root is not None else None
        selected = str(workspace_id).strip() if workspace_id else None
        signature = json.dumps({
            "workspace_id": selected,
            "host_project_id": project,
            "resources": resources or {},
            "enabled_modules": sorted(str(value) for value in enabled_modules),
        }, sort_keys=True, default=str)
        with self._lock:
            if signature != self._signature:
                self._signature = signature
                self._revision += 1
                self._token = uuid4().hex
                self._selection = ContextSelection(
                    self.instance_id, selected, project, self._revision, self._token
                )
            assert self._selection is not None
            return self._selection

    def require_current(self, token: str | None) -> None:
        """Reject a stale *supplied* token; legacy callers may omit it.

        Call ``capture`` with current host state before checking this guard.
        Omitting the optional header preserves older CLI and API integrations.
        """
        if token is None:
            return
        with self._lock:
            if not token or token != self._token:
                raise StaleWorkspaceContext(
                    "Workspace context changed. Refresh the module/workspace view before retrying."
                )
