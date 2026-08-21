from __future__ import annotations

import errno
import fcntl
import os
import pty
import struct
import termios
import select
import signal
import subprocess
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class TerminalError(ValueError):
    pass


@dataclass
class TerminalSession:
    id: str
    process: subprocess.Popen[bytes]
    master_fd: int
    cwd: Path
    output: deque[str] = field(default_factory=deque)
    lock: threading.Lock = field(default_factory=threading.Lock)
    closed: bool = False

    def append(self, text: str) -> None:
        with self.lock:
            self.output.append(text)
            total = sum(len(x) for x in self.output)
            while total > 250_000 and self.output:
                total -= len(self.output.popleft())

    def drain(self) -> str:
        with self.lock:
            text = "".join(self.output)
            self.output.clear()
            return text


class TerminalManager:
    """Small PTY-backed local terminal service.

    The browser terminal forwards raw terminal input/control sequences into a real
    PTY.  Terminal emulation stays in the browser while shell history, completion,
    cursor editing, signals, and interactive programs remain owned by the shell.
    """

    def __init__(self) -> None:
        self._sessions: dict[str, TerminalSession] = {}
        self._lock = threading.Lock()

    def start(self, cwd: Path, env: dict[str, str]) -> TerminalSession:
        shell = env.get("SHELL") or "/bin/bash"
        master_fd, slave_fd = pty.openpty()
        session_id = uuid.uuid4().hex
        child_env = env.copy()
        child_env.setdefault("TERM", "xterm-256color")
        child_env["PS1"] = "PAH:\\w$ "
        argv = [shell]
        if Path(shell).name in {"bash", "zsh"}:
            argv += ["-i"]
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=child_env,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            start_new_session=True,
            close_fds=True,
        )
        os.close(slave_fd)
        try:
            os.set_blocking(master_fd, False)
        except AttributeError:
            pass
        session = TerminalSession(session_id, process, master_fd, cwd)
        with self._lock:
            self._sessions[session_id] = session
        thread = threading.Thread(target=self._reader, args=(session,), daemon=True)
        thread.start()
        return session

    def _reader(self, session: TerminalSession) -> None:
        while not session.closed:
            if session.process.poll() is not None:
                # Drain whatever is still readable before closing.
                self._read_available(session)
                session.append("\n[terminal exited]\n")
                session.closed = True
                break
            self._read_available(session)
            time.sleep(0.04)

    def _read_available(self, session: TerminalSession) -> None:
        try:
            ready, _, _ = select.select([session.master_fd], [], [], 0)
            if not ready:
                return
            while True:
                try:
                    data = os.read(session.master_fd, 8192)
                except BlockingIOError:
                    break
                except OSError as exc:
                    if exc.errno in {errno.EIO, errno.EBADF}:
                        break
                    raise
                if not data:
                    break
                session.append(data.decode("utf-8", errors="replace"))
                if len(data) < 8192:
                    break
        except (OSError, ValueError):
            return

    def get(self, session_id: str) -> TerminalSession:
        with self._lock:
            session = self._sessions.get(session_id)
        if not session:
            raise TerminalError("Unknown terminal session.")
        return session

    def write(self, session_id: str, data: str) -> None:
        session = self.get(session_id)
        if session.closed or session.process.poll() is not None:
            raise TerminalError("Terminal session is closed.")
        os.write(session.master_fd, data.encode("utf-8"))

    def read(self, session_id: str) -> dict[str, Any]:
        session = self.get(session_id)
        return {
            "output": session.drain(),
            "closed": session.closed or session.process.poll() is not None,
        }

    def resize(self, session_id: str, cols: int, rows: int) -> None:
        session = self.get(session_id)
        if session.closed or session.process.poll() is not None:
            raise TerminalError("Terminal session is closed.")
        cols = int(cols)
        rows = int(rows)
        if cols < 2 or rows < 1 or cols > 1000 or rows > 500:
            raise TerminalError("Terminal size is outside the supported range.")
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(session.master_fd, termios.TIOCSWINSZ, winsize)
        try:
            os.killpg(session.process.pid, signal.SIGWINCH)
        except (ProcessLookupError, PermissionError):
            pass

    def stop(self, session_id: str) -> None:
        session = self.get(session_id)
        session.closed = True
        if session.process.poll() is None:
            try:
                os.killpg(session.process.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                session.process.terminate()
            try:
                session.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(session.process.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    session.process.kill()
        try:
            os.close(session.master_fd)
        except OSError:
            pass
        with self._lock:
            self._sessions.pop(session_id, None)

    def stop_all(self) -> None:
        with self._lock:
            ids = list(self._sessions)
        for session_id in ids:
            try:
                self.stop(session_id)
            except TerminalError:
                pass
