# ICMP Step 2 Executor Reuse Report

## Scope

Only the realtime monitor executor lifecycle was changed. The subprocess ping implementation, timeout, packet count, 15-second interval, RTT parsing, status transitions, alerts, persistence schema, APIs, and manual serial ping path were left unchanged.

## Change

`MonitorEngine` now owns one `ThreadPoolExecutor(max_workers=20, thread_name_prefix="mon-ping")`. It is created once when the engine loop is first ensured and reused by every monitoring cycle. The per-cycle `with ThreadPoolExecutor(...)` construction was removed. `MonitorEngine.shutdown()` stops and joins the loop, then shuts down the executor; application lifespan calls it during shutdown. A later monitor start can create a fresh lifecycle executor after shutdown. Existing same-process IP duplicate guards remain unchanged.

## Deterministic proof

Before: N monitoring cycles constructed N executors.

After: N cycles on one engine use 1 executor construction. Focused tests verify construction count, max worker count (20), shutdown/restart cleanup, failed/normal future isolation through the existing future handling, and unchanged one-packet/timeout ping arguments.

## Tests

`tests/test_icmp_executor_reuse.py`: **3 passed**.

`tests/test_icmp_preservation.py`: executor-related tests passed; three database-backed preservation tests could not connect because PostgreSQL is unavailable in this environment (unrelated runtime limitation).

`compileall`: passed.

