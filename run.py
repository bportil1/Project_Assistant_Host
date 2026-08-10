#!/usr/bin/env python3
from __future__ import annotations

import argparse
import logging
import os
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


def _configure_access_logging() -> None:
    # Keep normal Werkzeug access/error logging, but do not flood the console
    # with the terminal's expected polling requests. Non-200 poll responses
    # remain visible for debugging.
    logging.getLogger("werkzeug").addFilter(_TerminalPollAccessFilter())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Project Assistant Host")
    parser.add_argument("project", nargs="?", help="Optional project directory to open")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    _configure_access_logging()
    app = create_app()
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
        Timer(0.7, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()
    app.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
