"""Per-process runtime identity and isolation for PAH instances.

Durable research-workspace definitions continue to live in ``WorkspaceManager``.
This module owns only ephemeral process state: instance identity, ports, runtime
paths, health, and module/process ownership.  Keeping those concerns separate is
what allows multiple PAH processes to use the same installation/state catalog
without sharing temp files, hosted-tool ports, or child-process bookkeeping.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
from threading import RLock
from typing import Any, Mapping
from uuid import uuid4


DEFAULT_PORTS = {
    "host": 8765,
    "analysis": 8766,
    "documents": 8767,
    "references": 8768,
    "ml_lab": 8769,
}


class InstanceRuntimeError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True



def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def _valid_instance_id(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise InstanceRuntimeError("instance_id must not be empty")
    if any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for ch in raw):
        raise InstanceRuntimeError("instance_id contains unsupported characters")
    return raw


def _port_is_available(host: str, port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, int(port)))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def _ephemeral_port(host: str, excluded: set[int]) -> int:
    for _ in range(100):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((host, 0))
            port = int(sock.getsockname()[1])
        finally:
            sock.close()
        if port not in excluded:
            return port
    raise InstanceRuntimeError("Could not allocate a free loopback port")


class InstanceRuntime:
    """Runtime state belonging to exactly one PAH process/instance."""

    def __init__(
        self,
        *,
        state_dir: str | Path,
        instance_id: str | None = None,
        workspace_id: str | None = None,
        host: str = "127.0.0.1",
        preferred_ports: Mapping[str, int] | None = None,
    ) -> None:
        self.state_dir = Path(state_dir).expanduser().resolve()
        self.runtime_root = self.state_dir / "runtime"
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.instance_id = _valid_instance_id(instance_id or uuid4().hex)
        self.runtime_dir = self.runtime_root / self.instance_id
        if self.runtime_dir.exists() and any(self.runtime_dir.iterdir()):
            raise InstanceRuntimeError(f"Runtime directory already exists for instance {self.instance_id!r}")
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir = self.runtime_dir / "logs"
        self.temp_dir = self.runtime_dir / "tmp"
        self.cache_dir = self.runtime_dir / "cache"
        self.modules_dir = self.runtime_dir / "modules"
        for path in (self.logs_dir, self.temp_dir, self.cache_dir, self.modules_dir):
            path.mkdir(parents=True, exist_ok=True)
        self.log_file = self.logs_dir / "pah.log"
        self.log_file.touch(exist_ok=True)
        self.instance_file = self.runtime_dir / "instance.json"
        self.process_file = self.runtime_dir / "module-processes.json"
        self.host = str(host or "127.0.0.1").strip() or "127.0.0.1"
        self.pid = os.getpid()
        self.started_at = _utc_now()
        self.workspace_id = str(workspace_id).strip() if workspace_id else None
        self.health = "starting"
        self._lock = RLock()
        self._module_processes: dict[str, dict[str, Any]] = {}
        self._ports = self._allocate_ports(preferred_ports or {})
        self._persist()

    def _live_reserved_ports(self) -> set[int]:
        reserved: set[int] = set()
        for path in self.runtime_root.glob("*/instance.json"):
            if path == self.instance_file:
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                pid = int(payload.get("pid") or 0)
                health = str(payload.get("health") or "")
                if health == "stopped" or not _pid_alive(pid):
                    continue
                for value in dict(payload.get("ports") or {}).values():
                    port = int(value)
                    if 1 <= port <= 65535:
                        reserved.add(port)
            except Exception:
                continue
        return reserved

    def _allocate_ports(self, preferred_ports: Mapping[str, int]) -> dict[str, int]:
        reserved = self._live_reserved_ports()
        allocated: dict[str, int] = {}
        for name, default in DEFAULT_PORTS.items():
            raw = preferred_ports.get(name, default)
            preferred = int(raw)
            if preferred < 1 or preferred > 65535:
                raise InstanceRuntimeError(f"Preferred port {name!r} must be between 1 and 65535")
            excluded = reserved | set(allocated.values())
            if preferred not in excluded and _port_is_available(self.host, preferred):
                port = preferred
            else:
                port = _ephemeral_port(self.host, excluded)
            allocated[name] = port
            reserved.add(port)
        return allocated

    def port(self, name: str) -> int:
        try:
            return int(self._ports[str(name)])
        except KeyError as exc:
            raise InstanceRuntimeError(f"Unknown PAH runtime port {name!r}") from exc

    @property
    def ports(self) -> dict[str, int]:
        return dict(self._ports)

    def set_workspace(self, workspace_id: str | None) -> None:
        with self._lock:
            self.workspace_id = str(workspace_id).strip() if workspace_id else None
            self._persist()

    def mark_running(self) -> None:
        with self._lock:
            self.health = "running"
            self._persist()

    def register_module_runtime(
        self,
        module_id: str,
        *,
        pid: int | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        module_id = str(module_id or "").strip()
        if not module_id:
            raise InstanceRuntimeError("module_id must not be empty")
        with self._lock:
            record = {
                "module_id": module_id,
                "owner_instance_id": self.instance_id,
                "owner_pid": self.pid,
                "pid": int(pid) if pid is not None else None,
                "registered_at": _utc_now(),
                "metadata": _json_safe(dict(metadata or {})),
            }
            self._module_processes[module_id] = record
            self._persist_processes()
            self._persist()
            return dict(record)

    def unregister_module_runtime(self, module_id: str) -> None:
        with self._lock:
            self._module_processes.pop(str(module_id), None)
            self._persist_processes()
            self._persist()

    def module_processes(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {key: dict(value) for key, value in self._module_processes.items()}

    def _persist_processes(self) -> None:
        payload = {
            "instance_id": self.instance_id,
            "processes": self._module_processes,
        }
        tmp = self.process_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.process_file)

    def _persist(self) -> None:
        payload = self.snapshot()
        tmp = self.instance_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(self.instance_file)
        self._persist_processes()

    def snapshot(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "workspace_id": self.workspace_id,
            "pid": self.pid,
            "host": self.host,
            "port": self._ports.get("host") if hasattr(self, "_ports") else None,
            "ports": dict(getattr(self, "_ports", {})),
            "runtime_dir": str(self.runtime_dir),
            "log_file": str(self.log_file),
            "temp_dir": str(self.temp_dir),
            "cache_dir": str(self.cache_dir),
            "modules_dir": str(self.modules_dir),
            "started_at": self.started_at,
            "health": self.health,
            "child_processes": self.module_processes() if hasattr(self, "_module_processes") else {},
        }

    def stop(self) -> None:
        with self._lock:
            self.health = "stopped"
            self._persist()
