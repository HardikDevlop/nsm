"""Windows WMI/CIM inventory discovery."""

from __future__ import annotations

import json
import platform
import subprocess
from typing import Any

from config import WMI_TIMEOUT_SECONDS


class WMIDiscovery:
    """Collect Windows inventory through PowerShell CIM when available."""

    def __init__(self, timeout_seconds: int = WMI_TIMEOUT_SECONDS) -> None:
        self.timeout_seconds = timeout_seconds

    def collect(self, ip_address: str, open_ports: dict[str, str] | None = None) -> dict[str, Any]:
        """Return Windows host inventory.

        This uses the current user's Windows credentials. In production, this
        should be wrapped by a credential vault and least-privilege account.
        """
        if platform.system().lower() != "windows":
            return {"reachable": False, "skipped": "WMI discovery requires Windows"}

        if open_ports is not None and not {"135", "445", "5985", "5986"}.intersection(open_ports):
            return {"reachable": False, "skipped": "No Windows management ports detected"}

        command = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            self._powershell_script(ip_address),
        ]
        try:
            process = subprocess.run(command, capture_output=True, text=True, check=False, timeout=self.timeout_seconds)
        except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired) as exc:
            return {"reachable": False, "error": str(exc)}

        if process.returncode != 0:
            return {"reachable": False, "error": process.stderr.strip()[:500]}

        try:
            payload = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            return {"reachable": False, "error": f"Invalid WMI JSON: {exc}"}

        return {"reachable": True, **payload}

    @staticmethod
    def _powershell_script(ip_address: str) -> str:
        return (
            "$os = Get-CimInstance -ComputerName '" + ip_address + "' Win32_OperatingSystem; "
            "$cs = Get-CimInstance -ComputerName '" + ip_address + "' Win32_ComputerSystem; "
            "$bios = Get-CimInstance -ComputerName '" + ip_address + "' Win32_BIOS; "
            "[PSCustomObject]@{"
            "hostname=$cs.Name;"
            "manufacturer=$cs.Manufacturer;"
            "model=$cs.Model;"
            "os=$os.Caption;"
            "os_version=$os.Version;"
            "serial=$bios.SerialNumber;"
            "memory_bytes=[int64]$cs.TotalPhysicalMemory"
            "} | ConvertTo-Json -Compress"
        )

