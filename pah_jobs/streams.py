"""Optional bounded stdout/stderr draining for already-started subprocesses.

Never spawns or terminates a child. Call only when caller owns Popen pipes;
do not combine with ``Popen.communicate()`` on the same streams.
"""
from __future__ import annotations

import codecs
from threading import Thread
from typing import IO

from .registry import JobRegistry


class ProcessStreamCapture:
    """Concurrent readers ensure full pipes cannot stall the producing process."""

    def __init__(self, registry: JobRegistry, job_id: str, *, stdout: IO | None = None,
                 stderr: IO | None = None, chunk_size: int = 2048,
                 max_pending_chars: int = 4096):
        if not 1 <= chunk_size <= 65536 or max_pending_chars < 32:
            raise ValueError("invalid capture limits")
        self.registry = registry
        self.job_id = job_id
        self._streams = (("stdout", stdout), ("stderr", stderr))
        self._chunk_size = chunk_size
        self._max_pending = max_pending_chars
        self._threads: list[Thread] = []

    def start(self) -> "ProcessStreamCapture":
        if self._threads:
            raise RuntimeError("capture already started")
        for name, source in self._streams:
            if source is not None:
                t = Thread(target=self._drain, args=(name, source),
                           daemon=True, name=f"pah-job-{name}")
                self._threads.append(t)
                t.start()
        return self

    def _drain(self, name: str, source: IO) -> None:
        # Chunked reads (never readline) ensure maliciously long lines are bounded.
        decoder = codecs.getincrementaldecoder("utf-8")("replace")
        pending = ""
        try:
            while True:
                read_chunk = getattr(source, "read1", None) or source.read
                piece = read_chunk(self._chunk_size)
                if not piece:
                    break
                text = decoder.decode(piece) if isinstance(piece, bytes) else str(piece)
                pending += text
                while "\n" in pending:
                    line, pending = pending.split("\n", 1)
                    self.registry.output(self.job_id, line.rstrip("\r"), stream=name)
                if len(pending) >= self._max_pending:
                    self.registry.output(self.job_id, pending[:self._max_pending] + "…[line continued]", stream=name)
                    pending = pending[self._max_pending:]
            pending += decoder.decode(b"", final=True)
            if pending:
                self.registry.output(self.job_id, pending, stream=name)
        except (OSError, ValueError) as exc:
            self.registry.output(self.job_id, f"output reader error: {type(exc).__name__}", stream="event")

    def join(self, timeout: float | None = None) -> bool:
        for t in self._threads:
            t.join(timeout=timeout)
        return all(not t.is_alive() for t in self._threads)
