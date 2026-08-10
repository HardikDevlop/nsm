"""DNS reverse lookup discovery."""

from __future__ import annotations

import socket
from typing import Any


class DNSDiscovery:
    """Resolve IP addresses to hostnames."""

    def resolve(self, ip_address: str) -> dict[str, Any]:
        """Return reverse DNS details for an IP address."""
        try:
            hostname, aliases, addresses = socket.gethostbyaddr(ip_address)
            return {
                "ip": ip_address,
                "hostname": hostname,
                "aliases": aliases,
                "addresses": addresses,
                "resolved": True,
            }
        except (OSError, socket.herror):
            return {
                "ip": ip_address,
                "hostname": None,
                "aliases": [],
                "addresses": [],
                "resolved": False,
            }

