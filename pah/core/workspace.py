from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock
from typing import Any


class WorkspaceError(ValueError):
    pass


class WorkspaceManager:
    """Persist host workspace state outside user projects."""

    def __init__(self, state_dir: str | Path | None = None) -> None:
        default_dir = Path.home() / ".local" / "share" / "pah"
        self.state_dir = Path(state_dir or os.environ.get("PAH_STATE_DIR", default_dir)).expanduser()
        self.state_file = self.state_dir / "state.json"
        self._lock = RLock()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return {"current_root": None, "recent_roots": [], "environments": {}}
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"current_root": None, "recent_roots": [], "environments": {}}
        data.setdefault("current_root", None)
        data.setdefault("recent_roots", [])
        data.setdefault("environments", {})
        return data

    def _save(self) -> None:
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        tmp.replace(self.state_file)

    @property
    def root(self) -> Path | None:
        raw = self._state.get("current_root")
        if not raw:
            return None
        path = Path(raw)
        return path if path.is_dir() else None

    def require_root(self) -> Path:
        root = self.root
        if root is None:
            raise WorkspaceError("No workspace is open.")
        return root

    def open(self, path: str | Path) -> Path:
        candidate = Path(path).expanduser().resolve()
        if not candidate.exists():
            raise WorkspaceError(f"Workspace does not exist: {candidate}")
        if not candidate.is_dir():
            raise WorkspaceError(f"Workspace is not a directory: {candidate}")
        with self._lock:
            self._state["current_root"] = str(candidate)
            recent = [p for p in self._state.get("recent_roots", []) if p != str(candidate)]
            recent.insert(0, str(candidate))
            self._state["recent_roots"] = recent[:12]
            self._save()
        return candidate

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

    def snapshot(self) -> dict[str, Any]:
        root = self.root
        return {
            "root": str(root) if root else None,
            "recent": list(self._state.get("recent_roots", [])),
            "environment": self.current_environment(),
        }
