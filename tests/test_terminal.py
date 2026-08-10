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
