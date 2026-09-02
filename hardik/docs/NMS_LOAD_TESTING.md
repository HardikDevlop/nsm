# NMS Load Testing

`tools/nms_loadtest.py` is a bounded, standalone load runner. It does not
modify backend code, collectors, scheduler behavior, or database contents.

## Configuration

```json
{
  "base_url": "http://127.0.0.1:8000/api/v1",
  "token": "<access-token>",
  "database_url": "postgresql://user:password@127.0.0.1:5432/nms",
  "timeout_s": 10,
  "api": {
    "paths": ["/health", "/devices", "/snmp/devices/1/metrics/latest"],
    "requests": 100,
    "concurrency": 10
  },
  "snmp_simulated": {
    "operations": 100,
    "operation_ms": 150,
    "workers": 10,
    "failure_rate": 0.02
  }
}
```

Run from `hardik/`:

```bash
./.venv/bin/python -m tools.nms_loadtest load.json --output load-results.json
```

The report contains request count, success/failure count, throughput and
p50/p95/p99 latency for each workload. Local process CPU and RSS are collected
when the platform exposes them. With `database_url`, read-only telemetry also
collects active connections, `pg_stat_statements` query count (if enabled), and
queued/running monitoring configs as poll backlog. If a database or optional
view is unavailable, that individual value is `null`; measurements are never
fabricated.

The simulated SNMP workload is useful for bounded scheduler-pressure tests only.
It is not a substitute for the optional real-device integration tests.
