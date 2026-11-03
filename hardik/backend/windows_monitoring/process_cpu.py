"""Pure two-sample CPU accounting for Windows process snapshots."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from .cim import WindowsProcessResult


@dataclass(frozen=True)
class ProcessCPUResult:
    process_id: int
    cpu_percent: float | None
    status: str
    reason: str | None = None


def calculate_process_cpu(
    previous: Iterable[WindowsProcessResult],
    current: Iterable[WindowsProcessResult],
    *,
    previous_monotonic_seconds: float,
    current_monotonic_seconds: float,
    logical_processor_count: int | None,
) -> list[ProcessCPUResult]:
    """Calculate normalized CPU percentages between two monotonic samples.

    Windows ``KernelModeTime`` and ``UserModeTime`` are converted to seconds
    by the CIM collector before reaching this utility. Process identity is
    PID plus creation time, preventing PID reuse from inheriting old CPU.
    """
    current_rows = list(current)
    previous_rows = list(previous)
    previous_by_identity = {
        (row.process_id, row.creation_time): row
        for row in previous_rows
        if row.process_id is not None and row.creation_time is not None
    }
    current_identities = {
        (row.process_id, row.creation_time)
        for row in current_rows
        if row.process_id is not None and row.creation_time is not None
    }
    elapsed = current_monotonic_seconds - previous_monotonic_seconds
    valid_elapsed = (
        isinstance(elapsed, (int, float))
        and math.isfinite(elapsed)
        and elapsed > 0
    )
    valid_processors = (
        isinstance(logical_processor_count, int)
        and not isinstance(logical_processor_count, bool)
        and logical_processor_count > 0
    )
    results: list[ProcessCPUResult] = []

    for row in current_rows:
        pid = row.process_id
        if pid is None:
            continue
        if row.creation_time is None:
            results.append(ProcessCPUResult(pid, None, "unavailable", "missing_creation_time"))
            continue
        old = previous_by_identity.get((pid, row.creation_time))
        if old is None:
            reused_pid = any(candidate.process_id == pid for candidate in previous_rows)
            reason = "pid_reused" if reused_pid else "first_sample_or_new_process"
            results.append(ProcessCPUResult(pid, None, "warming_up", reason))
            continue
        if row.cpu_time_seconds is None or old.cpu_time_seconds is None:
            results.append(ProcessCPUResult(pid, None, "unavailable", "missing_cpu_time"))
            continue
        if not valid_elapsed:
            results.append(ProcessCPUResult(pid, None, "unavailable", "invalid_elapsed_time"))
            continue
        if not valid_processors:
            results.append(ProcessCPUResult(pid, None, "unavailable", "invalid_logical_processor_count"))
            continue
        if not all(math.isfinite(value) and value >= 0 for value in (old.cpu_time_seconds, row.cpu_time_seconds)):
            results.append(ProcessCPUResult(pid, None, "unavailable", "invalid_cpu_time"))
            continue
        delta = row.cpu_time_seconds - old.cpu_time_seconds
        if delta < 0:
            results.append(ProcessCPUResult(pid, None, "unavailable", "cpu_counter_reset"))
            continue
        percentage = delta / (elapsed * logical_processor_count) * 100
        if not math.isfinite(percentage) or percentage < 0 or percentage > 100:
            results.append(ProcessCPUResult(pid, None, "unavailable", "impossible_cpu_percentage"))
            continue
        results.append(ProcessCPUResult(pid, percentage, "ok"))

    for row in previous_rows:
        if row.process_id is not None and row.creation_time is not None and (row.process_id, row.creation_time) not in current_identities:
            results.append(ProcessCPUResult(row.process_id, None, "terminated", "absent_from_current_sample"))
    return results
