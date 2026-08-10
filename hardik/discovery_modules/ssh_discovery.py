"""SSH banner discovery and lightweight Linux fingerprinting."""

from __future__ import annotations

import re
import socket
from typing import Any

from config import SOCKET_TIMEOUT_SECONDS


SSH_PATTERN = re.compile(r"SSH-\d+\.\d+-(?P<server>[^\r\n]+)")


class SSHDiscovery:
    """Collect SSH server banner information."""

    def __init__(self, timeout_seconds: float = SOCKET_TIMEOUT_SECONDS) -> None:
        self.timeout_seconds = timeout_seconds

    def collect(self, ip_address: str, open_ports: dict[str, str] | None = None) -> dict[str, Any]:
        """Read the SSH banner when port 22 is open."""
        if open_ports is not None and "22" not in open_ports:
            return {"reachable": False}

        try:
            with socket.create_connection((ip_address, 22), timeout=self.timeout_seconds) as sock:
                sock.settimeout(self.timeout_seconds)
                banner = sock.recv(512).decode("utf-8", errors="replace").strip()
        except OSError as exc:
            return {"reachable": False, "error": str(exc)}

        match = SSH_PATTERN.search(banner)
        server = match.group("server") if match else None
        return {
            "reachable": True,
            "banner": banner,
            "server": server,
            "platform_hint": self._platform_hint(banner),
        }

    @staticmethod
    def _platform_hint(banner: str) -> str | None:
        lowered = banner.lower()
        for name in ("ubuntu", "debian", "centos", "rhel", "freebsd", "openbsd", "dropbear"):
            if name in lowered:
                return name
        return "linux/unix" if banner else None

