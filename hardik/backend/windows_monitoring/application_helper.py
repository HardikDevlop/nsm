"""Read-only Windows interactive-window helper and payload validation.

The helper is intentionally isolated from WinRM collection. It is not
installed, scheduled, or invoked by the backend. On Windows it can be run in
an interactive user session; elsewhere its enumeration entry point fails
closed.
"""

from __future__ import annotations

from datetime import datetime, timezone
import ctypes
from ctypes import wintypes
import sys
from dataclasses import dataclass, is_dataclass, replace
import copy
from typing import Any, Iterable


MAX_PAYLOAD_BYTES = 64 * 1024
MAX_PROCESS_IDS = 4096
MAX_SESSION_ID = 0x7FFFFFFF
MAX_PID = 0x7FFFFFFF
MAX_AGE_SECONDS = 30


def classify_process_metadata(process: Any) -> tuple[str | None, str | None]:
    """Classify only from present, non-name metadata.

    An executable path is evidence of where a process runs, not a trust or
    malware verdict.  Processes without a path remain unknown until exact
    Helper evidence verifies an interactive window.
    """
    path = getattr(process, "executable_path", None)
    if not isinstance(path, str) or not path.strip():
        return None, None
    normalized = path.replace("/", "\\").casefold()
    if "\\windows\\system32\\" in normalized or "\\windows\\syswow64\\" in normalized:
        return "windows", "Windows system executable path"
    return "background", "Executable path available; no interactive-window evidence"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _valid_int(value: Any, maximum: int) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= maximum


def validate_helper_payload(payload: Any, *, now: datetime | None = None) -> dict[str, Any]:
    """Validate the minimal helper contract and return a normalized copy."""
    if not isinstance(payload, dict):
        raise ValueError("helper payload must be an object")
    if len(str(payload).encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError("helper payload is too large")
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported helper schema")
    session_id = payload.get("session_id")
    if not _valid_int(session_id, MAX_SESSION_ID):
        raise ValueError("invalid session_id")
    collected_at = payload.get("collected_at")
    if not isinstance(collected_at, str):
        raise ValueError("invalid collected_at")
    try:
        collected = datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid collected_at") from exc
    if collected.tzinfo is None:
        raise ValueError("collected_at must include timezone")
    reference = now or datetime.now(timezone.utc)
    if abs((reference - collected).total_seconds()) > MAX_AGE_SECONDS:
        raise ValueError("stale helper payload")
    pids = payload.get("visible_process_ids")
    if not isinstance(pids, list) or len(pids) > MAX_PROCESS_IDS:
        raise ValueError("invalid visible_process_ids")
    if any(not _valid_int(pid, MAX_PID) or pid == 0 for pid in pids):
        raise ValueError("invalid process id")
    return {
        "schema_version": 1,
        "collected_at": collected.isoformat(),
        "session_id": session_id,
        "visible_process_ids": sorted(set(pids)),
    }


def enumerate_visible_process_ids() -> dict[str, Any]:
    """Enumerate visible top-level windows in the current interactive session."""
    if sys.platform != "win32":
        raise RuntimeError("Windows interactive helper requires Windows")

    user32 = ctypes.windll.user32
    user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    pids: set[int] = set()
    GA_ROOT = 2
    kernel32 = ctypes.windll.kernel32
    kernel32.ProcessIdToSessionId.argtypes = [wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)]
    session = wintypes.DWORD()
    current_pid = kernel32.GetCurrentProcessId()
    if not kernel32.ProcessIdToSessionId(current_pid, ctypes.byref(session)):
        raise OSError("ProcessIdToSessionId failed")

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _lparam):
        try:
            if not user32.IsWindowVisible(hwnd):
                return True
            if user32.GetAncestor(hwnd, GA_ROOT) != hwnd:
                return True
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if 0 < pid.value <= MAX_PID:
                pids.add(pid.value)
        except (OSError, ValueError):
            pass
        return True

    if not user32.EnumWindows(callback, 0):
        raise OSError("EnumWindows failed")
    return {"schema_version": 1, "collected_at": _now(), "session_id": session.value,
            "visible_process_ids": sorted(pids)}


@dataclass(frozen=True)
class ClassificationResult:
    classification: str | None = None
    source: str | None = None
    confidence: str | None = None
    application_group_id: str | None = None


def classify_visible_processes(processes: Iterable[Any], payload: Any, *, now: datetime | None = None) -> tuple[Any, ...]:
    """Apply only verified helper evidence; otherwise preserve unknown values.

    The current helper contract contains no process creation timestamp. To
    prevent a PID-reuse race, callers must provide ``process_creation_times``
    keyed by PID when applying evidence. Without it, no process is promoted
    to ``app``.
    """
    validated = validate_helper_payload(payload, now=now)
    creation_times = payload.get("process_creation_times", {})
    if not isinstance(creation_times, dict):
        creation_times = {}
    visible = set(validated["visible_process_ids"])
    result = []
    for process in processes:
        pid = getattr(process, "process_id", None)
        session = getattr(process, "session_id", None)
        creation = getattr(process, "creation_time", None)
        if (pid in visible and session == validated["session_id"]
                and creation is not None and creation_times.get(str(pid)) == creation):
            if is_dataclass(process):
                process = replace(process, classification="app", classification_source="visible_window",
                                  classification_confidence="verified", application_group_id=None)
            else:
                process = copy.copy(process)
                process.classification = "app"
                process.classification_source = "visible_window"
                process.classification_confidence = "verified"
                process.application_group_id = None
            result.append(process)
        else:
            result.append(process)
    return tuple(result)
