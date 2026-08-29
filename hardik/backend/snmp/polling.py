"""Async SNMP polling engine and persistence hooks.

The engine is deliberately independent of FastAPI request lifetimes. A
deployment may start it from application lifespan or from a worker process.
"""

import asyncio
import time
from collections.abc import Callable
from typing import Any

from .poll_scheduler import POLL_INTERVALS
from .statistics_engine import counter_delta


def interface_rates(previous: dict[str, Any], current: dict[str, Any], elapsed: float, speed_bps: float | None = None) -> dict[str, float | None]:
    """Calculate human-readable interface traffic and quality statistics."""
    if elapsed <= 0:
        return {"rx_mbps": None, "tx_mbps": None, "utilization_percent": None, "error_rate": None, "packet_rate": None}
    rx = counter_delta(float(current.get("rx_octets", 0)), float(previous.get("rx_octets", 0))) * 8 / elapsed / 1_000_000
    tx = counter_delta(float(current.get("tx_octets", 0)), float(previous.get("tx_octets", 0))) * 8 / elapsed / 1_000_000
    packets = counter_delta(float(current.get("packets", 0)), float(previous.get("packets", 0))) / elapsed
    errors = counter_delta(float(current.get("errors", 0)), float(previous.get("errors", 0)))
    utilization = ((rx + tx) * 1_000_000 / speed_bps * 100) if speed_bps else None
    return {"rx_mbps": round(rx, 3), "tx_mbps": round(tx, 3), "utilization_percent": round(utilization, 2) if utilization is not None else None, "error_rate": round(errors / max(packets, 1) * 100, 4), "packet_rate": round(packets, 2)}


class SNMPPollingEngine:
    """Schedule collector callbacks on an asyncio event loop."""

    def __init__(self, poll: Callable[[str, str], Any]) -> None:
        self.poll = poll
        self.scheduler = None

    def start(self, devices: list[str]) -> None:
        """Register standard cadence jobs; APScheduler is imported lazily."""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        self.scheduler = AsyncIOScheduler()
        for device in devices:
            for collector, seconds in POLL_INTERVALS.items():
                self.scheduler.add_job(self._run, "interval", seconds=seconds, args=[device, collector], id=f"{device}:{collector}", replace_existing=True)
        self.scheduler.start()

    async def _run(self, device: str, collector: str) -> Any:
        """Execute one poll without blocking the event loop."""
        started = time.perf_counter()
        result = self.poll(device, collector)
        if asyncio.iscoroutine(result):
            result = await result
        return {"device": device, "collector": collector, "duration_ms": (time.perf_counter() - started) * 1000, "result": result}

    def shutdown(self) -> None:
        """Stop scheduled jobs during application shutdown."""
        if self.scheduler:
            self.scheduler.shutdown(wait=False)
