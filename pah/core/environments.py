from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .workspace import WorkspaceManager


class EnvironmentError(ValueError):
    pass


class EnvironmentManager:
    def __init__(self, workspaces: WorkspaceManager) -> None:
        self.workspaces = workspaces

    def _python_in(self, env_dir: Path) -> Path:
        if os.name == "nt":
            return env_dir / "Scripts" / "python.exe"
        return env_dir / "bin" / "python"

    def selected_dir(self) -> Path | None:
        raw = self.workspaces.current_environment()
        return Path(raw) if raw else None

    def interpreter(self) -> Path:
        selected = self.selected_dir()
        if selected:
            python = self._python_in(selected)
            if python.exists():
                return python
        return Path(sys.executable)

    def create(self, relative: str = ".venv", python: str | None = None) -> dict[str, Any]:
        root = self.workspaces.require_root()
        env_dir = Path(relative).expanduser()
        if not env_dir.is_absolute():
            env_dir = root / env_dir
        env_dir = env_dir.resolve()
        try:
            env_dir.relative_to(root)
        except ValueError as exc:
            raise EnvironmentError("New PAH environments must be created inside the current workspace.") from exc
        if env_dir.exists() and any(env_dir.iterdir()):
            raise EnvironmentError(f"Environment path is not empty: {env_dir}")
        command = [python or sys.executable, "-m", "venv", str(env_dir)]
        result = subprocess.run(command, cwd=root, capture_output=True, text=True)
        if result.returncode != 0:
            raise EnvironmentError(result.stderr.strip() or "Failed to create virtual environment.")
        self.workspaces.set_environment(env_dir)
        return self.status()

    def select(self, path: str | None) -> dict[str, Any]:
        if path is None:
            self.workspaces.set_environment(None)
            return self.status()
        root = self.workspaces.require_root()
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        candidate = candidate.resolve()
        python = self._python_in(candidate)
        if not python.exists():
            raise EnvironmentError(f"No Python interpreter found in environment: {candidate}")
        self.workspaces.set_environment(candidate)
        return self.status()

    def status(self) -> dict[str, Any]:
        selected = self.selected_dir()
        interpreter = self.interpreter()
        version = "unknown"
        try:
            result = subprocess.run([str(interpreter), "--version"], capture_output=True, text=True, timeout=5)
            version = (result.stdout or result.stderr).strip()
        except (OSError, subprocess.SubprocessError):
            pass
        return {
            "selected": str(selected) if selected else None,
            "interpreter": str(interpreter),
            "version": version,
            "is_venv": selected is not None,
        }

    def process_env(self) -> dict[str, str]:
        env = os.environ.copy()
        selected = self.selected_dir()
        if selected:
            bin_dir = selected / ("Scripts" if os.name == "nt" else "bin")
            env["VIRTUAL_ENV"] = str(selected)
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            env.pop("PYTHONHOME", None)
        return env
