"""IP discovery and address validation.

Supports IPv4 CIDR ranges, legacy three-octet prefixes, and single host targets.
IPv6 validation is available for future expansion, but discovery generation keeps
IPv4 as the default product path.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Iterable, Iterator


@dataclass(frozen=True)
class IPDiscoveryResult:
    """Normalized IP discovery output."""

    target: str
    total_hosts: int
    ips: list[str]
    version: int


class IPDiscovery:
    """Generate and validate IP candidates from user-friendly network targets."""

    def __init__(self, allow_ipv6: bool = False) -> None:
        self.allow_ipv6 = allow_ipv6

    def discover(self, target: str, limit: int | None = None) -> IPDiscoveryResult:
        """Generate IPs for a CIDR, single IP, or legacy prefix target."""
        network = self.parse_target(target)
        if network.version == 6 and not self.allow_ipv6:
            raise ValueError("IPv6 discovery is disabled. Enable allow_ipv6 to use IPv6 targets.")

        hosts = list(self.iter_hosts(network, limit=limit))
        return IPDiscoveryResult(
            target=str(network),
            total_hosts=network.num_addresses,
            ips=hosts,
            version=network.version,
        )

    def parse_target(self, target: str) -> ipaddress._BaseNetwork:
        """Parse CIDR, single host, or a three-octet IPv4 prefix."""
        normalized = target.strip()
        if not normalized:
            raise ValueError("target must not be empty")

        if "/" not in normalized and normalized.count(".") == 2:
            normalized = f"{normalized}.0/24"

        if "/" in normalized:
            return ipaddress.ip_network(normalized, strict=False)

        address = ipaddress.ip_address(normalized)
        suffix = 32 if address.version == 4 else 128
        return ipaddress.ip_network(f"{address}/{suffix}", strict=False)

    def validate_ip(self, ip_address: str) -> bool:
        """Return True when the input is a valid IP address."""
        try:
            parsed = ipaddress.ip_address(ip_address)
        except ValueError:
            return False
        return parsed.version == 4 or self.allow_ipv6

    @staticmethod
    def iter_hosts(network: ipaddress._BaseNetwork, limit: int | None = None) -> Iterator[str]:
        """Yield usable hosts without materializing large networks until needed."""
        iterator: Iterable[ipaddress._BaseAddress]
        if network.num_addresses <= 2:
            iterator = network
        else:
            iterator = network.hosts()

        yielded = 0
        for address in iterator:
            if limit is not None and yielded >= limit:
                break
            yielded += 1
            yield str(address)

