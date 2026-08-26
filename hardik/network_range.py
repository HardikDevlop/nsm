"""Expand a user-friendly IP range into a list of host IPs and filter out
devices that are already known (e.g. stored in PostgreSQL) so the caller
only spends network probes on *new* devices.

Supported input formats:
    "192.168.1.0/24"            # CIDR
    "192.168.1.1-192.168.1.50"  # start-end range
    "192.168.1.1-50"            # start + last-octet end
    "192.168.1.1,192.168.1.5"   # comma-separated list
    "192.168.1.1"               # single host

Usage::

    from network_range import NetworkRange
    result = NetworkRange("192.168.1.0/24").expand(max_hosts=256)
    # -> ['192.168.1.1', '192.168.1.2', ...]
"""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass, field
from typing import Iterable


_DASH_RANGE_RE = re.compile(
    r"^\s*(\d{1,3}(?:\.\d{1,3}){3})\s*-\s*(\d{1,3}(?:\.\d{1,3}){3}|\d{1,3})\s*$"
)
_MAX_HOSTS = 255


@dataclass
class NetworkRange:
    """Parse and expand a human-readable IP range specification."""

    spec: str
    max_hosts: int = 1024

    def expand(self) -> list[str]:
        """Return the list of host IPs (strings) represented by ``spec``."""
        spec = (self.spec or "").strip()
        if not spec:
            raise ValueError("empty range specification")
        limit = min(max(1, self.max_hosts), _MAX_HOSTS)

        # 1) Comma-separated list
        if "," in spec:
            out: list[str] = []
            for chunk in spec.split(","):
                out.extend(NetworkRange(chunk, max_hosts=limit).expand())
                if len(out) > limit:
                    raise ValueError("IP range cannot contain more than 255 addresses")
            return out

        # 2) CIDR notation
        if "/" in spec:
            try:
                network = ipaddress.ip_network(spec, strict=False)
            except ValueError as exc:
                raise ValueError(f"invalid CIDR: {spec!r}") from exc
            hosts = [str(ip) for ip in network.hosts()] or [str(network.network_address)]
            if len(hosts) > limit:
                raise ValueError("IP range cannot contain more than 255 addresses")
            return hosts

        # 3) Dash range
        match = _DASH_RANGE_RE.match(spec)
        if match:
            start_s, end_s = match.group(1), match.group(2)
            start = ipaddress.ip_address(start_s)
            try:
                end = ipaddress.ip_address(end_s)
            except ValueError:
                # "192.168.1.1-50" -> last octet only
                end = ipaddress.ip_address(f"{start_s.rsplit('.', 1)[0]}.{int(end_s)}")
            if int(end) < int(start):
                raise ValueError(f"end {end_s} is before start {start_s}")
            hosts = [str(ipaddress.ip_address(i)) for i in range(int(start), int(end) + 1)]
            if len(hosts) > limit:
                raise ValueError("IP range cannot contain more than 255 addresses")
            return hosts

        # 4) Single host
        try:
            address = ipaddress.ip_address(spec)
            if address.version != 4:
                raise ValueError("IPv4 addresses only")
            return [str(address)]
        except ValueError as exc:
            raise ValueError(f"unrecognised range spec: {spec!r}") from exc


def diff_against_known(
    candidates: Iterable[str],
    known_ips: Iterable[str],
) -> tuple[list[str], list[str]]:
    """Split ``candidates`` into (new, already_known)."""
    known = {str(ip).strip() for ip in known_ips if ip}
    new, existing = [], []
    for ip in candidates:
        s = str(ip).strip()
        if s in known:
            existing.append(s)
        else:
            new.append(s)
    return new, existing


@dataclass
class ScanPlan:
    """Bundled output of :func:`plan_scan`."""

    spec: str
    all_ips: list[str] = field(default_factory=list)
    new_ips: list[str] = field(default_factory=list)
    known_ips: list[str] = field(default_factory=list)


def plan_scan(spec: str, known_ips: Iterable[str], max_hosts: int = 1024) -> ScanPlan:
    """Expand ``spec`` and partition into new/known hosts."""
    rng = NetworkRange(spec, max_hosts=max_hosts)
    all_ips = rng.expand()
    new_ips, known_in_range = diff_against_known(all_ips, known_ips)
    return ScanPlan(spec=spec, all_ips=all_ips, new_ips=new_ips, known_ips=known_in_range)
