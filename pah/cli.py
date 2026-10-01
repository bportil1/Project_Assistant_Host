"""Command-line process management for local PAH instances."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import webbrowser

from .launcher import LauncherError, LauncherManager
from .module_catalog import default_module_registry


def _default_state_dir() -> Path:
    return Path(os.environ.get("PAH_STATE_DIR", Path.home() / ".local" / "share" / "pah")).expanduser().resolve()


def _launcher(state_dir: str | Path | None = None) -> LauncherManager:
    return LauncherManager(
        state_dir=Path(state_dir).expanduser().resolve() if state_dir else _default_state_dir(),
        module_registry=default_module_registry(discover=True),
    )


def _instance_state(item: dict) -> str:
    if item.get("running"):
        return str(item.get("health") or "running")
    if item.get("stale"):
        return "stale"
    return str(item.get("health") or "stopped")


def _print_instances(launcher: LauncherManager, *, as_json: bool = False) -> int:
    launcher.reconcile_stale_instances()
    snapshot = launcher.snapshot()
    if as_json:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
        return 0

    instances = snapshot.get("instances", [])
    if not instances:
        print("No PAH instances found.")
        return 0

    headers = ("INSTANCE", "WORKSPACE", "STATE", "PID", "HOST:PORT", "STARTED")
    rows = []
    for item in instances:
        host = str(item.get("host") or "127.0.0.1")
        port = item.get("port") or "-"
        rows.append((
            str(item.get("instance_id") or "-"),
            str(item.get("workspace_id") or "-"),
            _instance_state(item),
            str(item.get("pid") or "-"),
            f"{host}:{port}",
            str(item.get("started_at") or "-"),
        ))
    widths = [max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))]
    print("  ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    print("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        print("  ".join(row[i].ljust(widths[i]) for i in range(len(headers))))
    return 0


def _open_workspace(launcher: LauncherManager, args: argparse.Namespace) -> int:
    workspace = launcher.resolve_workspace(args.workspace)
    result = launcher.open_workspace(workspace["id"], new_instance=bool(args.new_instance))
    url = result.get("url")
    instance = result.get("instance") or {}
    action = "reused" if result.get("reused") else "started"
    print(
        f"{action} PAH instance {instance.get('instance_id') or '<starting>'} "
        f"for workspace {workspace['id']}"
    )
    if url:
        print(url)
        if not args.no_browser:
            webbrowser.open(str(url))
    elif not result.get("reused"):
        print("Instance is starting; use `pah list` to inspect its port and health.")
    return 0


def _stop(launcher: LauncherManager, args: argparse.Namespace) -> int:
    if args.workspace:
        workspace = launcher.resolve_workspace(args.workspace)
        result = launcher.stop_workspace(
            workspace["id"],
            wait_timeout=float(args.timeout),
            force=bool(args.force),
        )
        print(
            f"Stopped {result['stopped_count']} instance(s) for workspace {workspace['id']}; "
            f"{result['already_stopped_count']} already stopped."
        )
        return 0

    result = launcher.stop_instance(
        args.instance,
        wait_timeout=float(args.timeout),
        force=bool(args.force),
    )
    if result.get("already_stopped"):
        print(f"PAH instance {args.instance} is already stopped.")
    else:
        print(f"Stopped PAH instance {args.instance}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pah", description="Project Assistant Host process manager")
    parser.add_argument("--state-dir", help="PAH state directory (defaults to PAH_STATE_DIR or ~/.local/share/pah)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List known PAH runtime instances")
    list_parser.add_argument("--json", action="store_true", help="Emit the launcher snapshot as JSON")

    open_parser = subparsers.add_parser("open", help="Open a research workspace")
    open_parser.add_argument("workspace", help="Workspace id or exact workspace name")
    open_parser.add_argument("--new-instance", action="store_true", help="Start another instance even if one is already running")
    open_parser.add_argument("--no-browser", action="store_true", help="Do not open the instance URL in a browser")

    stop_parser = subparsers.add_parser("stop", help="Stop one instance or all instances for a workspace")
    target = stop_parser.add_mutually_exclusive_group(required=True)
    target.add_argument("instance", nargs="?", help="Runtime instance id")
    target.add_argument("--workspace", help="Workspace id or exact workspace name")
    stop_parser.add_argument("--timeout", type=float, default=5.0, help="Seconds to wait for clean shutdown before failing")
    stop_parser.add_argument("--force", action="store_true", help="Send SIGKILL if clean shutdown exceeds --timeout")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        launcher = _launcher(args.state_dir)
        if args.command == "list":
            return _print_instances(launcher, as_json=bool(args.json))
        if args.command == "open":
            return _open_workspace(launcher, args)
        if args.command == "stop":
            return _stop(launcher, args)
    except LauncherError as exc:
        parser.error(str(exc))
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
