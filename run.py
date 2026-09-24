#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
from pathlib import Path
import os
import signal
import webbrowser
from threading import Timer

from pah import create_app


class _TerminalPollAccessFilter(logging.Filter):
    """Hide only successful high-frequency terminal-read access log entries."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        is_terminal_poll = "GET /api/terminal/read?" in message
        is_success = '" 200 ' in message
        return not (is_terminal_poll and is_success)


def _configure_access_logging(log_file: str | Path | None = None) -> None:
    # Keep normal Werkzeug access/error logging, but do not flood the console
    # with the terminal's expected polling requests. Non-200 poll responses
    # remain visible for debugging.
    logging.getLogger("werkzeug").addFilter(_TerminalPollAccessFilter())
    if log_file is not None:
        target = Path(log_file)
        target.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(target, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logging.getLogger().addHandler(handler)
        logging.getLogger().setLevel(logging.INFO)




def _install_signal_handlers(app) -> None:
    shutdown = app.extensions.get("pah_shutdown")
    if not callable(shutdown):
        return

    def handle_stop(signum, frame):  # noqa: ARG001 - signal callback signature
        shutdown()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, handle_stop)
    if hasattr(signal, "SIGINT"):
        signal.signal(signal.SIGINT, handle_stop)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Project Assistant Host")
    parser.add_argument("project", nargs="?", help="Optional project directory to open")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--state-dir", help="PAH state directory (used by launcher-managed instances)")
    parser.add_argument("--workspace-id", help="Research workspace id to bind to this instance")
    parser.add_argument("--instance-id", help="Explicit runtime instance id")
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    app = create_app(
        state_dir=args.state_dir,
        instance_id=args.instance_id,
        preferred_ports={"host": args.port},
        host=args.host,
        workspace_id=args.workspace_id,
    )
    instance_runtime = app.extensions["pah_instance_runtime"]
    selected_port = instance_runtime.port("host")
    _configure_access_logging(instance_runtime.log_file)
    _install_signal_handlers(app)
    if args.project:
        # Use the same manager backing the app through the HTTP endpoint once running;
        # a startup environment variable keeps run.py thin and avoids reaching into app internals.
        os.environ["PAH_START_PROJECT"] = os.path.abspath(os.path.expanduser(args.project))
        # Opening through test_request_context keeps startup behavior inside the public HTTP surface.
        with app.test_client() as client:
            response = client.post("/api/workspace/open", json={"path": os.environ["PAH_START_PROJECT"]})
            if response.status_code >= 400:
                raise SystemExit(response.get_json().get("error", "Could not open project"))

    if not args.no_browser:
        landing_path = "/" if (args.project or args.workspace_id) else "/launcher"
        Timer(0.7, lambda: webbrowser.open(f"http://{args.host}:{selected_port}{landing_path}")).start()
    print(
        f"PAH instance {instance_runtime.instance_id} | "
        f"workspace={instance_runtime.workspace_id or '<none>'} | "
        f"http://{args.host}:{selected_port}"
    )
    app.run(host=args.host, port=selected_port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
