# NMS Progressive Scalability Report

Run date: 2026-08-29

## Scope

The progressive harness was run with 100, 500, 1000, 2500 and 5000 simulated
SNMP operations. Each operation used the bounded simulator with 50 workers,
1 ms configured operation time and a 0% simulated failure rate. The simulator
does not inject data into the NMS or alter production code.

## Measurements

| Simulated devices | Requests | Success | Failures | Completion (s) | Throughput (req/s) | p50 (ms) | p95 (ms) | p99 (ms) | Max backlog | RSS before -> after |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 100 | 100 | 0 | 0.005 | 21777.298 | 1.755 | 1.781 | 1.812 | 50 | 22.11 -> 22.42 MB |
| 500 | 500 | 500 | 0 | 0.022 | 22427.448 | 1.540 | 2.593 | 2.605 | 450 | 22.42 -> 23.37 MB |
| 1000 | 1000 | 1000 | 0 | 0.045 | 22353.107 | 1.543 | 3.444 | 3.475 | 950 | 23.37 -> 24.66 MB |
| 2500 | 2500 | 2500 | 0 | 0.115 | 21755.169 | 1.539 | 1.601 | 9.239 | 2450 | 24.66 -> 28.52 MB |
| 5000 | 5000 | 5000 | 0 | 0.233 | 21460.289 | 1.537 | 1.589 | 17.842 | 4950 | 28.52 -> 35.52 MB |

## Result

All simulated points completed successfully, so the stop-on-instability rule
was not triggered. The first measured pressure signal is tail latency and
memory growth at 5000 operations: p99 reached 17.842 ms and RSS increased by
approximately 7.0 MB from the 2500-point baseline.

The measured simulator backlog is expected queued work (`operations - workers`)
and is not the production scheduler backlog. It demonstrates that the test
harness applies bounded concurrency rather than launching unbounded tasks.

## Not Measured

The local backend was not listening on `127.0.0.1:8000` during this run
(`curl /api/v1/health` returned connection refused). Therefore real API latency,
dashboard performance, PostgreSQL connections/query load, production scheduler
backlog and alert processing are untested and are not represented as passing.
Process CPU was unavailable because the optional `psutil` package is not
installed; RSS was collected from the operating-system resource counter.

To complete live validation, start the existing NMS with PostgreSQL and run:

```bash
cd /home/agnigate/Desktop/NMS/hardik
NMS_TOKEN='<token>' NMS_DATABASE_URL='postgresql://...' \
  ./.venv/bin/python -m tools.progressive_scalability \
  --base-url http://127.0.0.1:8000/api/v1 \
  --output scalability-results.json
```

The generated JSON is the raw measurement artifact for that environment.
