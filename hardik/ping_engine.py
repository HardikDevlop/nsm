"""Small platform-aware wrapper around the system ping command."""

from __future__ import annotations

import platform
import subprocess


def run_ping(ip_address: str, count: int = 1, timeout_ms: int = 1000) -> subprocess.CompletedProcess[str]:
    system = platform.system().lower()
    if system == "windows":
        command = ["ping", "-n", str(count), "-w", str(timeout_ms), ip_address]
    else:
        command = ["ping", "-c", str(count), "-W", str(max(1, round(timeout_ms / 1000))), ip_address]
    return subprocess.run(command, capture_output=True, text=True, timeout=max(2, count * timeout_ms / 1000 + 2), check=False)
