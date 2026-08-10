"""Phase-4 ICMP monitoring."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Iterable

from config import MAX_WORKERS, PING_COUNT, PING_TIMEOUT
from parser import parse_ping_output
from ping_engine import run_ping


class ICMPMonitor:
    """Collect ping monitoring metrics for known inventory devices."""

    def __init__(self, max_workers: int = MAX_WORKERS, timeout_ms: int = PING_TIMEOUT) -> None:
        self.max_workers = max(1, max_workers)
        self.timeout_ms = timeout_ms

    def check(self, ip_address: str) -> dict[str, Any]:
        """Return one ICMP monitoring sample."""
        timestamp = datetime.now(timezone.utc).isoformat()
        try:
            process = run_ping(ip_address, count=PING_COUNT, timeout_ms=self.timeout_ms)
            parsed = parse_ping_output(process.stdout, process.returncode)
        except Exception as exc:
            return {
                "ip": ip_address,
                "monitor": "icmp",
                "timestamp": timestamp,
                "up": False,
                "rtt_ms": None,
                "ttl": None,
                "packet_loss_percent": 100,
                "error": str(exc),
            }

        return {
            "ip": ip_address,
            "monitor": "icmp",
            "timestamp": timestamp,
            "up": bool(parsed["reachable"]),
            "rtt_ms": parsed["avg_rtt"],
            "ttl": parsed["ttl"],
            "packet_loss_percent": parsed["packet_loss"],
        }

    def check_many(self, ip_addresses: Iterable[str]) -> list[dict[str, Any]]:
        """Collect ICMP samples concurrently for many devices."""
        ips = list(dict.fromkeys(ip_addresses))
        if not ips:
            return []

        workers = min(self.max_workers, len(ips))
        samples: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="icmp-monitor") as executor:
            futures = {executor.submit(self.check, ip_address): ip_address for ip_address in ips}
            for future in as_completed(futures):
                samples.append(future.result())
        return sorted(samples, key=lambda item: item["ip"])

