import time
from pathlib import Path

from pah.core.terminal import TerminalManager


def test_terminal_executes_command(tmp_path: Path):
    manager = TerminalManager()
    session = manager.start(tmp_path, {})
    try:
        manager.write(session.id, "printf 'PAH_TERMINAL_OK\\n'\n")
        output = ""
        deadline = time.time() + 3
        while time.time() < deadline and "PAH_TERMINAL_OK" not in output:
            time.sleep(0.05)
            output += manager.read(session.id)["output"]
        assert "PAH_TERMINAL_OK" in output
    finally:
        manager.stop(session.id)


def test_terminal_resize_updates_pty_window_size(tmp_path: Path):
    manager = TerminalManager()
    session = manager.start(tmp_path, {})
    try:
        manager.resize(session.id, 100, 30)
        manager.write(session.id, "stty size\n")
        output = ""
        deadline = time.time() + 3
        while time.time() < deadline and "30 100" not in output:
            time.sleep(0.05)
            output += manager.read(session.id)["output"]
        assert "30 100" in output
    finally:
        manager.stop(session.id)


def test_terminal_accepts_readline_history_escape_sequence(tmp_path: Path):
    manager = TerminalManager()
    session = manager.start(tmp_path, {})
    try:
        manager.write(session.id, "printf 'PAH_HISTORY_OK\\n'\n")
        output = ""
        deadline = time.time() + 3
        while time.time() < deadline and "PAH_HISTORY_OK" not in output:
            time.sleep(0.05)
            output += manager.read(session.id)["output"]
        assert "PAH_HISTORY_OK" in output

        manager.write(session.id, "\x1b[A\n")
        repeated = ""
        deadline = time.time() + 3
        while time.time() < deadline and "PAH_HISTORY_OK" not in repeated:
            time.sleep(0.05)
            repeated += manager.read(session.id)["output"]
        assert "PAH_HISTORY_OK" in repeated
    finally:
        manager.stop(session.id)
