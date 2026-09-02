"""Reusable, dependency-light load runner for the NMS.

The runner performs real HTTP requests against a configured NMS instance. The
SNMP workload is explicitly simulated and never changes application behavior.
Database telemetry is optional; unavailable measurements are reported as null,
not invented.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Sample:
    latency_ms: float
    ok: bool
    status: int | None = None
    error: str | None = None


@dataclass
class WorkloadResult:
    name: str
    requests: int
    successes: int
    failures: int
    duration_s: float
    throughput_rps: float
    p50_ms: float | None
    p95_ms: float | None
    p99_ms: float | None
    max_backlog: int | None = None
    samples: list[Sample] = field(default_factory=list)

    @classmethod
    def from_samples(cls, name: str, samples: list[Sample], duration_s: float) -> "WorkloadResult":
        values = sorted(s.latency_ms for s in samples)

        def percentile(percent: float) -> float | None:
            if not values:
                return None
            index = min(len(values) - 1, max(0, int((percent / 100) * len(values))))
            return round(values[index], 3)

        successes = sum(sample.ok for sample in samples)
        return cls(
            name=name,
            requests=len(samples),
            successes=successes,
            failures=len(samples) - successes,
            duration_s=round(duration_s, 3),
            throughput_rps=round(len(samples) / duration_s, 3) if duration_s else 0.0,
            p50_ms=percentile(50),
            p95_ms=percentile(95),
            p99_ms=percentile(99),
            samples=samples,
        )


@dataclass
class SystemSnapshot:
    timestamp: float
    process_cpu_percent: float | None = None
    process_rss_bytes: int | None = None
    db_connections: int | None = None
    query_count: int | None = None
    poll_backlog: int | None = None


class DatabaseTelemetry:
    """Read-only PostgreSQL telemetry for a configured load-test target."""

    def __init__(self, database_url: str):
        self.database_url = database_url

    def snapshot(self) -> tuple[int | None, int | None, int | None]:
        try:
            import psycopg

            with psycopg.connect(self.database_url, connect_timeout=3) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
                    connections = int(cursor.fetchone()[0])
                    try:
                        cursor.execute("SELECT COALESCE(sum(calls), 0) FROM pg_stat_statements")
                        query_count = int(cursor.fetchone()[0])
                    except Exception:
                        query_count = None
                    try:
                        cursor.execute("SELECT count(*) FROM monitoring_configs WHERE status IN ('queued', 'running')")
                        poll_backlog = int(cursor.fetchone()[0])
                    except Exception:
                        poll_backlog = None
            return connections, query_count, poll_backlog
        except Exception:
            return None, None, None


class NMSLoadRunner:
    def __init__(self, base_url: str, token: str | None = None, timeout_s: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout_s = timeout_s

    def request(self, path: str) -> Sample:
        started = time.perf_counter()
        request = urllib.request.Request(f"{self.base_url}/{path.lstrip('/')}")
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                response.read()
                return Sample((time.perf_counter() - started) * 1000, 200 <= response.status < 400, response.status)
        except urllib.error.HTTPError as exc:
            return Sample((time.perf_counter() - started) * 1000, False, exc.code, str(exc))
        except (OSError, TimeoutError) as exc:
            return Sample((time.perf_counter() - started) * 1000, False, None, str(exc))

    async def run_api(self, name: str, paths: list[str], requests: int, concurrency: int) -> WorkloadResult:
        semaphore = asyncio.Semaphore(max(1, concurrency))
        samples: list[Sample] = []
        started = time.perf_counter()

        async def one(path: str) -> None:
            async with semaphore:
                sample = await asyncio.to_thread(self.request, path)
                samples.append(sample)

        await asyncio.gather(*(one(paths[index % len(paths)]) for index in range(requests)))
        return WorkloadResult.from_samples(name, samples, time.perf_counter() - started)


class SimulatedSNMPWorkload:
    """Bounded SNMP workload generator for scheduler capacity testing.

    It models operation duration and failures without returning data to the
    application or replacing a collector. Use real-device tests separately.
    """

    def __init__(self, operation_ms: float = 100.0, failure_rate: float = 0.0, workers: int = 10):
        self.operation_ms = max(0.0, operation_ms)
        self.failure_rate = min(1.0, max(0.0, failure_rate))
        self.workers = max(1, workers)
        self.backlog = 0
        self.max_backlog = 0

    async def run(self, operations: int) -> WorkloadResult:
        import random

        semaphore = asyncio.Semaphore(self.workers)
        samples: list[Sample] = []
        started = time.perf_counter()

        async def one() -> None:
            self.backlog += 1
            self.max_backlog = max(self.max_backlog, self.backlog)
            async with semaphore:
                self.backlog -= 1
                operation_started = time.perf_counter()
                await asyncio.sleep(self.operation_ms / 1000)
                ok = random.random() >= self.failure_rate
                samples.append(Sample((time.perf_counter() - operation_started) * 1000, ok, 200 if ok else None, None if ok else "simulated SNMP failure"))

        await asyncio.gather(*(one() for _ in range(operations)))
        result = WorkloadResult.from_samples("snmp-simulated", samples, time.perf_counter() - started)
        result.max_backlog = self.max_backlog
        return result


def collect_system_snapshot() -> SystemSnapshot:
    """Collect local runner telemetry without adding a runtime dependency."""
    snapshot = SystemSnapshot(timestamp=time.time())
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        snapshot.process_rss_bytes = int(usage.ru_maxrss * (1024 if os.name != "darwin" else 1))
    except (ImportError, OSError):
        pass
    try:
        import psutil

        process = psutil.Process()
        snapshot.process_cpu_percent = process.cpu_percent(interval=0.05)
        snapshot.process_rss_bytes = process.memory_info().rss
    except (ImportError, OSError):
        pass
    return snapshot


def _json_ready(value: Any) -> Any:
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {key: _json_ready(item) for key, item in asdict(value).items() if key != "samples"}
    return value


async def run(config: dict[str, Any]) -> dict[str, Any]:
    runner = NMSLoadRunner(config["base_url"], config.get("token"), config.get("timeout_s", 10.0))
    database = DatabaseTelemetry(config["database_url"]) if config.get("database_url") else None

    def snapshot() -> SystemSnapshot:
        value = collect_system_snapshot()
        if database:
            value.db_connections, value.query_count, value.poll_backlog = database.snapshot()
        return value

    snapshots = [snapshot()]
    results = []
    api = config.get("api", {})
    if api.get("paths") and api.get("requests", 0):
        results.append(await runner.run_api("api", api["paths"], int(api["requests"]), int(api.get("concurrency", 10))))
    snmp = config.get("snmp_simulated", {})
    if snmp.get("operations", 0):
        workload = SimulatedSNMPWorkload(snmp.get("operation_ms", 100), snmp.get("failure_rate", 0), snmp.get("workers", 10))
        results.append(await workload.run(int(snmp["operations"])))
        snapshots.append(snapshot())
    return {"results": [_json_ready(result) for result in results], "system": [_json_ready(snapshot) for snapshot in snapshots]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run bounded NMS API and simulated SNMP load")
    parser.add_argument("config", type=Path, help="JSON workload configuration")
    parser.add_argument("--output", type=Path, help="Write JSON results to this file")
    args = parser.parse_args()
    report = asyncio.run(run(json.loads(args.config.read_text(encoding="utf-8"))))
    encoded = json.dumps(report, indent=2)
    if args.output:
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
