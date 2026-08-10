"""TCP port scanning and service detection."""

from __future__ import annotations

import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Iterable

from config import MAX_WORKERS, SOCKET_TIMEOUT_SECONDS, TCP_PORTS


SERVICE_NAMES: dict[int, str] = {
    22: "SSH",
    23: "TELNET",
    25: "SMTP",
    53: "DNS",
    80: "HTTP",
    110: "POP3",
    135: "MS-RPC",
    139: "NETBIOS",
    143: "IMAP",
    161: "SNMP",
    389: "LDAP",
    443: "HTTPS",
    445: "SMB",
    587: "SMTP-SUBMISSION",
    636: "LDAPS",
    993: "IMAPS",
    995: "POP3S",
    1433: "MSSQL",
    1521: "ORACLE",
    3306: "MYSQL",
    3389: "RDP",
    5432: "POSTGRESQL",
    5900: "VNC",
    5985: "WINRM-HTTP",
    5986: "WINRM-HTTPS",
    8080: "HTTP-ALT",
    8443: "HTTPS-ALT",
    9100: "PRINTER",
}


@dataclass(frozen=True)
class PortProbe:
    """Single TCP port probe result."""

    port: int
    open: bool
    service: str


class TCPDiscovery:
    """Concurrent TCP connector scanner with static service fingerprinting."""

    def __init__(
        self,
        ports: Iterable[int] | None = None,
        timeout_seconds: float = SOCKET_TIMEOUT_SECONDS,
        max_workers: int = MAX_WORKERS,
    ) -> None:
        self.ports = tuple(dict.fromkeys(ports or TCP_PORTS))
        self.timeout_seconds = timeout_seconds
        self.max_workers = max(1, max_workers)

    def scan_port(self, ip_address: str, port: int) -> PortProbe:
        """Return whether a TCP port accepts a connection."""
        try:
            with socket.create_connection((ip_address, port), timeout=self.timeout_seconds):
                return PortProbe(port=port, open=True, service=SERVICE_NAMES.get(port, "UNKNOWN"))
        except OSError:
            return PortProbe(port=port, open=False, service=SERVICE_NAMES.get(port, "UNKNOWN"))

    def scan_host(self, ip_address: str) -> dict[str, str]:
        """Scan configured ports for a single host.

        Returns a JSON-friendly mapping such as {"22": "SSH", "80": "HTTP"}.
        """
        if not self.ports:
            return {}

        workers = min(self.max_workers, len(self.ports))
        open_ports: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="tcp") as executor:
            futures = {executor.submit(self.scan_port, ip_address, port): port for port in self.ports}
            for future in as_completed(futures):
                result = future.result()
                if result.open:
                    open_ports[str(result.port)] = result.service

        return dict(sorted(open_ports.items(), key=lambda item: int(item[0])))

