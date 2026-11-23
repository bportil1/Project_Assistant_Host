"""Local OS-process supervisor for independent PAH module instances.

The module type and its scientific project/state are opaque to PAH.  A trusted
runtime adapter supplies an argv-style launch command; PAH owns only process
identity, private scratch paths, an optional local port, logging, and teardown.

This is intentionally not an HTTP command-execution API.  MI-04 will provide
instance-specific routing; legacy adapter launches remain unchanged in MI-03.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
from threading import RLock
from typing import Any, Mapping, Sequence
from uuid import uuid4

from .instance_runtime import (
    InstanceRuntime,
    InstanceRuntimeError,
    _ephemeral_port,
    _pid_alive,
    _port_is_available,
    _valid_module_instance_id,
)


class ModuleProcessError(RuntimeError):
    """Raised for launch, ownership, and lifecycle errors."""


@dataclass
class _OwnedProcess:
    module_id: str
    process: subprocess.Popen
    runtime_dir: Path
    port: int | None


class ModuleProcessLauncher:
    """Supervisor for child processes *started by this PAH process only*.

    A registry entry alone is not authority to signal a PID: shutdown requires
    the actual Popen handle retained by the owner.  This avoids killing a
    different PAH process, unrelated module, or a recycled PID.
    """

    def __init__(self, runtime: InstanceRuntime, *, process_factory=None) -> None:
        self.runtime = runtime
        self.process_factory = process_factory or subprocess.Popen
        self._lock = RLock()
        self._owned: dict[str, _OwnedProcess] = {}

    def _other_ports(self) -> set[int]:
        """Exclude ports already recorded for this host and live peer hosts."""
        used = set(self.runtime.ports.values()) | set(self.runtime._live_reserved_ports())
        for instance in self.runtime.module_instances().values():
            try:
                port = int(instance.get("metadata", {}).get("port") or 0)
                if port:
                    used.add(port)
            except (TypeError, ValueError):
                continue
        for path in self.runtime.runtime_root.glob("*/module-processes.json"):
            if path == self.runtime.process_file:
                continue
            try:
                owner_file = path.with_name("instance.json")
                owner = json.loads(owner_file.read_text(encoding="utf-8"))
                if owner.get("health") == "stopped" or not _pid_alive(int(owner.get("pid") or 0)):
                    continue
                registrations = json.loads(path.read_text(encoding="utf-8"))
                for record in registrations.get("processes", {}).values():
                    port = int(record.get("metadata", {}).get("port") or 0)
                    if port:
                        used.add(port)
            except (OSError, ValueError, TypeError, KeyError, AttributeError):
                continue
        return used

    def _select_port(self, requested_port: int | None) -> int | None:
        if requested_port is None:
            return None
        if isinstance(requested_port, bool) or (not isinstance(requested_port, int) and
                                               (not isinstance(requested_port, str) or not requested_port.isdecimal())):
            raise ModuleProcessError("requested_port must be 0, 1–65535, or None")
        try:
            requested = int(requested_port)
        except (TypeError, ValueError) as exc:
            raise ModuleProcessError("requested_port must be 0, 1–65535, or None") from exc
        if requested < 0 or requested > 65535:
            raise ModuleProcessError("requested_port must be 0, 1–65535, or None")
        excluded = self._other_ports()
        if requested == 0:
            return _ephemeral_port(self.runtime.host, excluded)
        if requested in excluded or not _port_is_available(self.runtime.host, requested):
            raise ModuleProcessError(f"Port {requested} is already in use or reserved")
        return requested

    @staticmethod
    def _argv(command: Sequence[str]) -> list[str]:
        if isinstance(command, (str, bytes)) or not command:
            raise ModuleProcessError("command must be a nonempty argv sequence; shell commands are not accepted")
        if any(not isinstance(item, str) or not item or "\x00" in item for item in command):
            raise ModuleProcessError("command must contain nonempty argv strings without NUL characters")
        return list(command)

    def launch(
        self,
        module_id: str,
        command: Sequence[str],
        *,
        module_instance_id: str | None = None,
        cwd: str | Path | None = None,
        env: Mapping[str, str] | None = None,
        requested_port: int | None = 0,
        ui_path: str | None = None,
        workspace_id: str | None = None,
        host_project_id: str | None = None,
    ) -> dict[str, Any]:
        """Start a fresh process; never reuse/rebind another running instance.

        ``requested_port=0`` allocates a currently free loopback port and passes
        it via PAH_MODULE_PORT. It is a best-effort allocation, NOT a reserved
        listening socket: the module must bind it promptly, and only modules
        supporting a configurable port can use that facility safely.
        Set ``requested_port=None`` for modules with no HTTP listener.
        """
        module = str(module_id or "").strip()
        try:
            _valid_module_instance_id(module)
            identity = _valid_module_instance_id(
                module_instance_id or f"{self.runtime.instance_id}:{module}:{uuid4().hex}"
            )
            if identity == self.runtime._default_module_instance_id(module):
                raise ModuleProcessError("The stable host:module identity is reserved for legacy adapters")
        except InstanceRuntimeError as exc:
            raise ModuleProcessError(str(exc)) from exc
        argv = self._argv(command)
        directory = Path(cwd).expanduser().resolve() if cwd is not None else None
        if directory is not None and not directory.is_dir():
            raise ModuleProcessError(f"Module working directory does not exist: {directory}")
        if env is not None and any(not isinstance(k, str) or not isinstance(v, str)
                                   for k, v in env.items()):
            raise ModuleProcessError("Environment overrides must have string names and values")

        with self._lock:
            if identity in self._owned or identity in self.runtime.module_instances():
                raise ModuleProcessError(f"Module instance {identity!r} already exists")
            port = self._select_port(requested_port)
            if ui_path is not None:
                if not isinstance(ui_path, str) or not re.fullmatch(r"/[A-Za-z0-9/_\-.]*", ui_path):
                    raise ModuleProcessError("ui_path must be a local absolute path without URL syntax")
                if ui_path.startswith("//") or port is None:
                    raise ModuleProcessError("ui_path requires an allocated port and a local path")
            # UUID-backed path never uses a module name or caller-supplied ID as
            # a path component (including dots, colons, or traversal sequences).
            run_dir = self.runtime.modules_dir / uuid4().hex
            paths = {name: run_dir / name for name in ("logs", "tmp", "cache")}
            for path in paths.values():
                path.mkdir(parents=True, exist_ok=False)
            log_path = paths["logs"] / "process.log"
            work_dir = directory or run_dir
            environment = os.environ.copy()
            if env is not None:
                environment.update(env)
            # Reserved variables cannot be forged by an adapter-supplied env.
            environment.update({
                "PAH_MODULE_ID": module,
                "PAH_MODULE_INSTANCE_ID": identity,
                "PAH_HOST_INSTANCE_ID": self.runtime.instance_id,
                "PAH_MODULE_RUNTIME_DIR": str(run_dir),
                "PAH_MODULE_LOG_DIR": str(paths["logs"]),
                "PAH_MODULE_TMP_DIR": str(paths["tmp"]),
                "PAH_MODULE_CACHE_DIR": str(paths["cache"]),
                "PAH_MODULE_HOST": self.runtime.host,
                "TMPDIR": str(paths["tmp"]),
                "TMP": str(paths["tmp"]),
                "TEMP": str(paths["tmp"]),
            })
            if port is not None:
                environment["PAH_MODULE_PORT"] = str(port)
            else:
                environment.pop("PAH_MODULE_PORT", None)
            # Do not inherit a stale binding from the parent PAH process.
            environment.pop("PAH_WORKSPACE_ID", None)
            environment.pop("PAH_HOST_PROJECT_ID", None)
            if workspace_id is not None:
                environment["PAH_WORKSPACE_ID"] = str(workspace_id)
            if host_project_id is not None:
                environment["PAH_HOST_PROJECT_ID"] = str(host_project_id)
            # Do not log argv or environment: either may contain credentials.
            try:
                with log_path.open("ab", buffering=0) as output:
                    proc = self.process_factory(
                        argv,
                        cwd=str(work_dir),
                        env=environment,
                        stdin=subprocess.DEVNULL,
                        stdout=output,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                        close_fds=True,
                    )
            except OSError as exc:
                shutil.rmtree(run_dir, ignore_errors=True)
                raise ModuleProcessError(f"Could not launch module {module!r}: {exc}") from exc
            try:
                record = self.runtime.register_module_runtime(
                    module,
                    module_instance_id=identity,
                    pid=proc.pid,
                    metadata={
                        "presentation": "external_process",
                        "runtime_dir": str(run_dir),
                        "log_file": str(log_path),
                        "working_dir": str(work_dir),
                        "port": port,
                        "host": self.runtime.host,
                        # Only advertise a URL when the trusted adapter explicitly
                        # declares a browser entry point. Headless modules get none.
                        "url": (
                            f"http://127.0.0.1:{port}{ui_path}"
                            if ui_path is not None and self.runtime.host in {"127.0.0.1", "localhost"}
                            else None
                        ),
                        "workspace_id": workspace_id,
                        "host_project_id": host_project_id,
                        "lifecycle": "spawned",
                    },
                )
            except Exception:
                # A failed bookkeeping operation must not orphan a new process.
                try:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=3)
                finally:
                    raise
            self._owned[identity] = _OwnedProcess(module, proc, run_dir, port)
            return record

    def owns(self, module_instance_id: str) -> bool:
        """Whether this PAH process retains the live child process handle."""
        with self._lock:
            owned = self._owned.get(str(module_instance_id))
            return owned is not None and owned.process.poll() is None

    def reap_exited(self) -> list[str]:
        """Remove registrations for exited children, preserving logs on disk."""
        with self._lock:
            exited = [identity for identity, owned in self._owned.items() if owned.process.poll() is not None]
            for identity in exited:
                owned = self._owned.pop(identity)
                self.runtime.unregister_module_runtime(owned.module_id, module_instance_id=identity)
            return exited

    def stop(self, module_instance_id: str, *, wait_timeout: float = 2.0, force: bool = False) -> bool:
        """Terminate exactly one *owned* child, never an arbitrary registry PID."""
        identity = str(module_instance_id or "")
        with self._lock:
            owned = self._owned.get(identity)
            if owned is None:
                raise ModuleProcessError(f"Module instance {identity!r} is not owned by this process")
            proc = owned.process
            if proc.poll() is None:
                try:
                    if os.name == "posix":
                        os.killpg(proc.pid, signal.SIGTERM)
                    else:
                        proc.terminate()
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=max(0.0, float(wait_timeout)))
                except subprocess.TimeoutExpired:
                    if not force:
                        raise ModuleProcessError(f"Module instance {identity!r} did not stop; retry with force=True")
                    try:
                        if os.name == "posix":
                            os.killpg(proc.pid, signal.SIGKILL)
                        else:
                            proc.kill()
                    except ProcessLookupError:
                        pass
                    proc.wait(timeout=max(0.1, float(wait_timeout)))
            self.runtime.unregister_module_runtime(owned.module_id, module_instance_id=identity)
            del self._owned[identity]
            return True

    def stop_all(self, *, wait_timeout: float = 2.0, force: bool = True) -> None:
        """Close managed children during PAH shutdown, including siblings."""
        for identity in list(self._owned):
            try:
                self.stop(identity, wait_timeout=wait_timeout, force=force)
            except (ModuleProcessError, OSError, subprocess.TimeoutExpired):
                # Other children must still receive shutdown signals.
                continue
