"""Optional, read-only Linux process identity and resource observations.

Never enumerate unrelated processes, run shell commands, or signal a PID.
Unknown and permission-denied observations remain unobservable, not 'alive'.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import sys


@dataclass(frozen=True)
class ProcessObservation:
    status: str  # alive | gone | reused | unobservable
    start_id: str | None = None
    cpu_seconds: float | None = None
    rss_bytes: int | None = None


def observe_pid(pid: int, expected_start_id: str | None = None) -> ProcessObservation:
    """Inspect only a caller-registered Linux PID, using /proc identity.

    If identity was not captured at registration, 'alive' is not asserted:
    an OS PID may be recycled and mistakenly attributed to another job.
    """
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        raise ValueError("pid must be a positive integer")
    if not sys.platform.startswith("linux"):
        return ProcessObservation("unobservable")
    try:
        raw = (Path("/proc") / str(pid) / "stat").read_text(encoding="ascii")
    except FileNotFoundError:
        return ProcessObservation("gone")
    except (OSError, UnicodeError):
        return ProcessObservation("unobservable")
    end = raw.rfind(")")
    if end < 0:
        return ProcessObservation("unobservable")
    # After '(comm)' the fields start at #3. In particular starttime is #22.
    fields = raw[end + 1:].split()
    if len(fields) < 22:
        return ProcessObservation("unobservable")
    try:
        state = fields[0]
        start_id = fields[19]
        ticks = os.sysconf("SC_CLK_TCK")
        cpu_seconds = (int(fields[11]) + int(fields[12])) / ticks
        rss_bytes = int(fields[21]) * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, KeyError, ZeroDivisionError):
        return ProcessObservation("unobservable")
    if expected_start_id and start_id != expected_start_id:
        return ProcessObservation("reused", start_id)
    if state in {"Z", "X", "x"}:
        return ProcessObservation("gone", start_id)
    if not expected_start_id:
        return ProcessObservation("unobservable", start_id)
    return ProcessObservation("alive", start_id, cpu_seconds, rss_bytes)
