"""Local PAH workspace launcher and running-instance manager.

Sprint 4 keeps process discovery grounded in the per-instance metadata produced
by :mod:`pah.instance_runtime`.  The launcher owns no separate database: it
combines the durable workspace catalog with live runtime markers and can start
or stop additional PAH processes on this machine.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from typing import Any
from uuid import uuid4

from .core.workspace import WorkspaceManager
from .instance_runtime import _pid_alive
from .module_catalog import MODULE_CATEGORIES, module_category


class LauncherError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LauncherManager:
    """Read workspace/runtime state and launch isolated PAH processes."""

    def __init__(
        self,
        *,
        state_dir: str | Path,
        module_registry,
        current_instance_id: str | None = None,
        run_script: str | Path | None = None,
        process_factory=None,
    ) -> None:
        self.state_dir = Path(state_dir).expanduser().resolve()
        self.runtime_root = self.state_dir / "runtime"
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.module_registry = module_registry
        self.current_instance_id = str(current_instance_id or "").strip() or None
        self.run_script = Path(run_script or (Path(__file__).resolve().parents[1] / "run.py")).resolve()
        self.process_factory = process_factory or subprocess.Popen

    def _read_instance(self, path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None
        instance_id = str(payload.get("instance_id") or path.parent.name).strip()
        try:
            pid = int(payload.get("pid") or 0)
        except (TypeError, ValueError):
            pid = 0
        health = str(payload.get("health") or "unknown")
        alive = _pid_alive(pid)
        running = bool(alive and health not in {"stopped", "failed"})
        host = str(payload.get("host") or "127.0.0.1")
        try:
            port = int(payload.get("port") or dict(payload.get("ports") or {}).get("host") or 0)
        except (TypeError, ValueError):
            port = 0
        url = f"http://{host}:{port}/" if running and port else None
        return {
            **payload,
            "instance_id": instance_id,
            "pid": pid,
            "health": health,
            "alive": alive,
            "running": running,
            "stale": bool(not alive and health not in {"stopped", "failed"}),
            "current": instance_id == self.current_instance_id,
            "url": url,
        }

    def instances(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in sorted(self.runtime_root.glob("*/instance.json")):
            item = self._read_instance(path)
            if item is not None:
                items.append(item)
        items.sort(key=lambda item: (not item.get("running", False), str(item.get("started_at") or "")), reverse=False)
        return items

    def _write_instance_payload(self, instance_id: str, payload: dict[str, Any]) -> None:
        path = self.runtime_root / str(instance_id) / "instance.json"
        if not path.parent.is_dir():
            return
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        tmp.replace(path)

    def reconcile_stale_instances(self) -> list[dict[str, Any]]:
        """Mark dead instances that never recorded a clean stop as stale.

        Runtime directories are retained for diagnostics; reconciliation only
        updates health metadata and never removes user/workspace data.
        """
        changed: list[dict[str, Any]] = []
        for item in self.instances():
            if item.get("alive") or item.get("health") in {"stopped", "failed", "stale"}:
                continue
            payload = dict(item)
            for derived in ("alive", "running", "current", "url", "stale"):
                payload.pop(derived, None)
            payload["health"] = "stale"
            payload["stale_detected_at"] = _utc_now()
            self._write_instance_payload(str(item["instance_id"]), payload)
            changed.append(self._read_instance(self.runtime_root / str(item["instance_id"]) / "instance.json") or payload)
        return changed

    def _module_map(self) -> dict[str, Any]:
        return {manifest.module_id: manifest for manifest in self.module_registry.all()}

    def workspace_cards(self) -> list[dict[str, Any]]:
        manager = WorkspaceManager(self.state_dir, persist_active_workspace=False)
        manager.configure_available_modules(item.module_id for item in self.module_registry.all())
        catalog = manager.catalog_snapshot()
        module_map = self._module_map()
        all_instances = self.instances()
        by_workspace: dict[str, list[dict[str, Any]]] = {}
        for instance in all_instances:
            workspace_id = str(instance.get("workspace_id") or "").strip()
            if workspace_id:
                by_workspace.setdefault(workspace_id, []).append(instance)

        cards: list[dict[str, Any]] = []
        for workspace in catalog.get("workspaces", []):
            workspace_id = str(workspace.get("id") or "")
            enabled_ids = [str(value) for value in workspace.get("enabled_modules", [])]
            missing_modules = [module_id for module_id in enabled_ids if module_id not in module_map]
            modules = []
            categories: dict[str, dict[str, Any]] = {}
            for module_id in enabled_ids:
                manifest = module_map.get(module_id)
                if manifest is None:
                    modules.append({
                        "module_id": module_id,
                        "display_name": module_id,
                        "installed": False,
                        "category": "unavailable",
                        "category_label": "Unavailable",
                    })
                    continue
                category, label = module_category(manifest)
                modules.append({
                    "module_id": module_id,
                    "display_name": manifest.display_name,
                    "installed": True,
                    "category": category,
                    "category_label": label,
                })
                bucket = categories.setdefault(category, {"id": category, "label": label, "modules": []})
                bucket["modules"].append(module_id)

            unavailable_resources = []
            for role, resource in dict(workspace.get("resources") or {}).items():
                if not resource.get("available"):
                    unavailable_resources.append({
                        "role": role,
                        "root_id": resource.get("root_id"),
                        "path": resource.get("path"),
                        "status": resource.get("status"),
                    })

            warnings: list[str] = []
            if unavailable_resources:
                roles = ", ".join(item["role"] for item in unavailable_resources)
                warnings.append(f"Unavailable resources: {roles}")
            if missing_modules:
                warnings.append("Enabled but not installed: " + ", ".join(missing_modules))

            running_instances = [item for item in by_workspace.get(workspace_id, []) if item.get("running")]
            cards.append({
                **workspace,
                "modules": modules,
                "categories": sorted(categories.values(), key=lambda item: item["label"].lower()),
                "capability_labels": [item["label"] for item in sorted(categories.values(), key=lambda item: item["label"].lower())],
                "warnings": warnings,
                "unavailable_resources": unavailable_resources,
                "missing_modules": missing_modules,
                "instances": by_workspace.get(workspace_id, []),
                "running_instances": running_instances,
                "running_count": len(running_instances),
            })
        return cards

    def snapshot(self) -> dict[str, Any]:
        instances = self.instances()
        return {
            "generated_at": _utc_now(),
            "current_instance_id": self.current_instance_id,
            "categories": MODULE_CATEGORIES,
            "workspaces": self.workspace_cards(),
            "instances": instances,
            "running_count": sum(1 for item in instances if item.get("running")),
        }

    def resolve_workspace(self, workspace_ref: str) -> dict[str, Any]:
        workspace_ref = str(workspace_ref or "").strip()
        if not workspace_ref:
            raise LauncherError("workspace must not be empty")
        cards = self.workspace_cards()
        for workspace in cards:
            if workspace.get("id") == workspace_ref:
                return workspace
        matches = [
            workspace for workspace in cards
            if str(workspace.get("name") or "").casefold() == workspace_ref.casefold()
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise LauncherError(f"Workspace name is ambiguous: {workspace_ref}")
        raise LauncherError(f"Unknown research workspace: {workspace_ref}")

    def _workspace(self, workspace_id: str) -> dict[str, Any]:
        return self.resolve_workspace(workspace_id)

    def open_workspace(self, workspace_id: str, *, new_instance: bool = False) -> dict[str, Any]:
        workspace = self._workspace(workspace_id)
        running = [item for item in workspace.get("running_instances", []) if item.get("url")]
        if running and not new_instance:
            preferred = next((item for item in running if item.get("current")), running[0])
            return {
                "workspace_id": workspace_id,
                "reused": True,
                "spawned": False,
                "instance": preferred,
                "url": preferred.get("url"),
            }
        return self.spawn_instance(workspace_id)

    def spawn_instance(self, workspace_id: str) -> dict[str, Any]:
        self._workspace(workspace_id)
        if not self.run_script.is_file():
            raise LauncherError(f"PAH runner not found: {self.run_script}")
        instance_id = uuid4().hex
        command = [
            sys.executable,
            str(self.run_script),
            "--state-dir",
            str(self.state_dir),
            "--workspace-id",
            workspace_id,
            "--instance-id",
            instance_id,
            "--no-browser",
        ]
        try:
            process = self.process_factory(
                command,
                cwd=str(self.run_script.parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as exc:
            raise LauncherError(f"Could not start PAH instance: {exc}") from exc

        instance_file = self.runtime_root / instance_id / "instance.json"
        deadline = time.monotonic() + 2.0
        item = None
        while time.monotonic() < deadline:
            if instance_file.exists():
                item = self._read_instance(instance_file)
                if item and item.get("port"):
                    break
            if hasattr(process, "poll") and process.poll() is not None:
                break
            time.sleep(0.02)
        if item is None:
            item = {
                "instance_id": instance_id,
                "workspace_id": workspace_id,
                "pid": getattr(process, "pid", None),
                "health": "starting",
                "running": True,
                "current": False,
                "url": None,
            }
        return {
            "workspace_id": workspace_id,
            "reused": False,
            "spawned": True,
            "instance": item,
            "url": item.get("url"),
        }

    def stop_instance(
        self,
        instance_id: str,
        *,
        wait_timeout: float = 0.0,
        force: bool = False,
    ) -> dict[str, Any]:
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            raise LauncherError("instance_id must not be empty")
        instance = next((item for item in self.instances() if item.get("instance_id") == instance_id), None)
        if instance is None:
            raise LauncherError(f"Unknown PAH instance: {instance_id}")
        if instance.get("current"):
            raise LauncherError("The current PAH instance cannot stop itself from its launcher page.")
        if not instance.get("running"):
            if instance.get("stale"):
                self.reconcile_stale_instances()
            return {"instance_id": instance_id, "stopped": True, "already_stopped": True}

        pid = int(instance["pid"])
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            self.reconcile_stale_instances()
            return {"instance_id": instance_id, "stopped": True, "already_stopped": True}
        except (PermissionError, OSError) as exc:
            raise LauncherError(f"Could not stop PAH instance {instance_id}: {exc}") from exc

        wait_timeout = max(0.0, float(wait_timeout))
        if wait_timeout <= 0.0:
            # The web launcher keeps its historical non-blocking stop behavior.
            # CLI callers pass a positive timeout when they require confirmation.
            return {"instance_id": instance_id, "stopped": True, "already_stopped": False}

        deadline = time.monotonic() + wait_timeout
        while _pid_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        forced = False
        if _pid_alive(pid):
            if not force:
                raise LauncherError(
                    f"PAH instance {instance_id} did not stop within {float(wait_timeout):g}s; "
                    "retry with --force if required."
                )
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except (PermissionError, OSError) as exc:
                raise LauncherError(f"Could not force-stop PAH instance {instance_id}: {exc}") from exc
            forced = True
            deadline = time.monotonic() + 1.0
            while _pid_alive(pid) and time.monotonic() < deadline:
                time.sleep(0.05)
            if _pid_alive(pid):
                raise LauncherError(f"PAH instance {instance_id} is still running after SIGKILL.")

        refreshed = next((item for item in self.instances() if item.get("instance_id") == instance_id), None)
        if refreshed and refreshed.get("health") not in {"stopped", "failed"}:
            self.reconcile_stale_instances()
        result = {"instance_id": instance_id, "stopped": True, "already_stopped": False}
        if forced:
            result["forced"] = True
        return result

    def stop_workspace(
        self,
        workspace_id: str,
        *,
        wait_timeout: float = 5.0,
        force: bool = False,
    ) -> dict[str, Any]:
        workspace = self.resolve_workspace(workspace_id)
        instances = [
            item for item in self.instances()
            if item.get("workspace_id") == workspace["id"]
        ]
        results = []
        for item in instances:
            results.append(self.stop_instance(
                str(item["instance_id"]),
                wait_timeout=wait_timeout,
                force=force,
            ))
        return {
            "workspace_id": workspace["id"],
            "results": results,
            "stopped_count": sum(1 for item in results if item.get("stopped") and not item.get("already_stopped")),
            "already_stopped_count": sum(1 for item in results if item.get("already_stopped")),
        }
