"""ARP cache discovery."""

from __future__ import annotations

import platform
import re
import subprocess
from typing import Any


MAC_PATTERN = re.compile(r"(?P<mac>(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2})", re.IGNORECASE)


class ARPDiscovery:
    """Read MAC addresses from the local ARP/neighbour cache."""

    def collect(self, ip_address: str) -> dict[str, Any]:
        """Return the MAC address for an IP when present in the local ARP table.

        Uses `ip neigh show` on Linux (preferred) and falls back to `arp -a`
        on systems with net-tools installed.
        """
        # --- Linux: ip neigh (works without net-tools) ---
        if platform.system().lower() != "windows":
            try:
                output = subprocess.run(
                    ["ip", "neigh", "show", ip_address],
                    capture_output=True, text=True, check=False, timeout=5,
                ).stdout
                match = MAC_PATTERN.search(output)
                if match:
                    return {"ip": ip_address, "mac": match.group("mac").replace("-", ":").lower(), "source": "ip-neigh"}
            except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired):
                pass

        # --- Fallback: arp command ---
        command = ["arp", "-a", ip_address] if platform.system().lower() == "windows" else ["arp", "-n", ip_address]
        try:
            process = subprocess.run(command, capture_output=True, text=True, check=False, timeout=3)
        except (FileNotFoundError, subprocess.SubprocessError, subprocess.TimeoutExpired) as exc:
            return {"ip": ip_address, "mac": None, "source": "arp", "error": str(exc)}

        output = f"{process.stdout}\n{process.stderr}"
        for line in output.splitlines():
            if ip_address not in line:
                continue
            match = MAC_PATTERN.search(line)
            if match:
                return {"ip": ip_address, "mac": match.group("mac").replace("-", ":").lower(), "source": "arp"}

        return {"ip": ip_address, "mac": None, "source": "arp"}

