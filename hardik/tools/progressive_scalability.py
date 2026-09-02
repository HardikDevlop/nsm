"""Run the NMS load harness at progressively larger simulated fleet sizes."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from tools.nms_loadtest import DatabaseTelemetry, NMSLoadRunner, SimulatedSNMPWorkload, collect_system_snapshot


SCALE_POINTS = (100, 500, 1000, 2500, 5000)


async def run_point(size: int, args: argparse.Namespace) -> dict[str, object]:
    database = DatabaseTelemetry(args.database_url) if args.database_url else None
    before = collect_system_snapshot()
    if database:
        before.db_connections, before.query_count, before.poll_backlog = database.snapshot()

    started = time.perf_counter()
    workload = SimulatedSNMPWorkload(args.operation_ms, args.failure_rate, args.workers)
    snmp = await workload.run(size)
    api = None
    if args.api_path:
        runner = NMSLoadRunner(args.base_url, args.token, args.timeout_s)
        api = await runner.run_api("dashboard-api", [args.api_path], size, args.api_concurrency)

    after = collect_system_snapshot()
    if database:
        after.db_connections, after.query_count, after.poll_backlog = database.snapshot()
    return {
        "simulated_devices": size,
        "elapsed_s": round(time.perf_counter() - started, 3),
        "snmp": {key: value for key, value in snmp.__dict__.items() if key != "samples"},
        "api": None if api is None else {key: value for key, value in api.__dict__.items() if key != "samples"},
        "system_before": before.__dict__,
        "system_after": after.__dict__,
        "status": "stable" if snmp.failures == 0 else "unstable",
    }


async def run(args: argparse.Namespace) -> dict[str, object]:
    results = []
    for size in SCALE_POINTS:
        result = await run_point(size, args)
        results.append(result)
        if result["status"] != "stable" and args.stop_on_failure:
            break
    return {"scale_points": SCALE_POINTS, "results": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="Progressive NMS scalability validation")
    parser.add_argument("--base-url", default=os.getenv("NMS_BASE_URL", "http://127.0.0.1:8000/api/v1"))
    parser.add_argument("--token", default=os.getenv("NMS_TOKEN"))
    parser.add_argument("--api-path", default=os.getenv("NMS_SCALE_API_PATH", "/overview"))
    parser.add_argument("--database-url", default=os.getenv("NMS_DATABASE_URL"))
    parser.add_argument("--timeout-s", type=float, default=10.0)
    parser.add_argument("--api-concurrency", type=int, default=50)
    parser.add_argument("--workers", type=int, default=50)
    parser.add_argument("--operation-ms", type=float, default=1.0)
    parser.add_argument("--failure-rate", type=float, default=0.0)
    parser.add_argument("--stop-on-failure", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--output", type=Path, default=Path("scalability-results.json"))
    args = parser.parse_args()
    report = asyncio.run(run(args))
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
