"""ICMP discovery module."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Iterable
import logging

from config import MAX_WORKERS, PING_COUNT, PING_TIMEOUT
from parser import parse_ping_output
from ping_engine import run_ping

logger = logging.getLogger(__name__)


class ICMPDiscovery:
    """Probe hosts with ICMP and return alive/dead telemetry."""

    def __init__(self, max_workers: int = MAX_WORKERS, timeout_ms: int = PING_TIMEOUT) -> None:
        self.max_workers = max(1, max_workers)
        self.timeout_ms = timeout_ms

    def probe(self, ip_address: str) -> dict[str, Any]:
        """Probe one host and return normalized ICMP fields."""
        logger.info("icmp_probe_start ip=%s timeout_ms=%s", ip_address, self.timeout_ms)
        try:
            process = run_ping(ip_address, count=PING_COUNT, timeout_ms=self.timeout_ms)
            parsed = parse_ping_output(process.stdout, process.returncode)
        except Exception as exc:
            logger.warning("icmp_probe_error ip=%s error=%s", ip_address, exc)
            return {
                "ip": ip_address,
                "status": "DOWN",
                "reachable": False,
                "ttl": None,
                "rtt": None,
                "packet_loss": 100,
                "error": str(exc),
            }

        result = {
            "ip": ip_address,
            "status": "UP" if parsed["reachable"] else "DOWN",
            "reachable": parsed["reachable"],
            "ttl": parsed["ttl"],
            "rtt": parsed["avg_rtt"],
            "packet_loss": parsed["packet_loss"],
            "estimated_os": parsed["estimated_os"],
            "hop_count": parsed["hop_count"],
        }
        logger.info("icmp_probe_result ip=%s status=%s rtt_ms=%s packet_loss=%s", ip_address, result["status"], result["rtt"], result["packet_loss"])
        return result

    def discover(self, ip_addresses: Iterable[str]) -> list[dict[str, Any]]:
        """Probe many hosts concurrently with bounded worker pressure."""
        ips = list(dict.fromkeys(ip_addresses))
        if not ips:
            return []

        workers = min(self.max_workers, len(ips))
        results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="icmp") as executor:
            futures = {executor.submit(self.probe, ip_address): ip_address for ip_address in ips}
            for future in as_completed(futures):
                results.append(future.result())

        return sorted(results, key=lambda item: tuple(int(part) for part in item["ip"].split(".") if part.isdigit()))
