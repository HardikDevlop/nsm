# SNMP Step 4 Engine and Event-Loop Reuse Report

## Result

Step 4 is complete. Physical SNMP work now runs on a fixed pool of eight dedicated workers. Each worker owns exactly one thread, asyncio event loop, and `SnmpEngine`; operations assigned to that worker reuse its loop and engine serially. Engines are never shared across threads or event loops.

## Lifecycle audit and reuse boundary

Before Step 4, every `_run_in_thread()` call submitted a temporary worker function that created and closed an asyncio event loop. Every GET and every root WALK also created a new `SnmpEngine`; WALK closed its dispatcher after the request. Authentication, context, and `UdpTransportTarget` were created per operation.

After Step 4:

- event loop: one long-lived loop per dedicated worker;
- `SnmpEngine`: one long-lived engine per worker, used only on its owning loop/thread;
- authentication: still constructed per request, preserving v2c/v3 credential isolation;
- transport target: still constructed per request with the requested host, port, timeout, and retries;
- context and OID objects: still per request;
- worker selection: round-robin across the fixed eight-worker physical pool;
- operation execution: serialized by each worker's queue, preventing concurrent engine use.

The existing `_run_in_thread(coro, timeout)` seam remains intact. When protocol tests replace that seam and execute outside a managed worker, the client creates an operation-owned engine and retains the prior cleanup behavior.

## Shutdown and recovery

`shutdown_snmp_workers()` first stops admission, drains accepted queues, sends one stop marker per worker, closes each engine dispatcher, cancels remaining loop tasks, closes loops, and joins all worker threads. FastAPI lifespan shutdown calls it after polling scheduler shutdown, so no new scheduled SNMP work should enter during teardown. Repeated shutdown is idempotent and post-shutdown submissions fail clearly while closing the unsubmitted coroutine.

Ordinary request exceptions fail only that request and do not replace or poison the worker. A `RuntimeError`, treated as an unusable runtime signal, is returned to the affected request and then causes only that worker's engine/loop to close and be recreated. The error is not swallowed.

## Behavior preservation

- SNMP v2c and v3 authentication construction is unchanged.
- GET request and response semantics are unchanged.
- GETBULK batching, subtree bounds, row cap, and GETNEXT fallback are unchanged.
- Request timeout, retries, internal operation timeout margin, and external future deadline are unchanged.
- Authentication objects are not reused across credentials.
- Step 2 cache keys, TTL, result copying, failure behavior, and single-flight logic are unchanged.
- Step 3 root concurrency remains 3 per device.
- Scheduler workers remain 8.
- Vendor detection, OID registry, collectors, normalization, persistence, polling history, alerts, APIs, and schema are unchanged.

## Observability

Debug-level lifecycle events were added without device or credential data:

- `SNMP_WORKER_STARTED`
- `SNMP_ENGINE_CREATED`
- `SNMP_ENGINE_REUSED`
- `SNMP_WORKER_RECOVERED`
- `SNMP_WORKER_STOPPED`

## Deterministic proof and tests

Focused instrumentation submits multiple operations to a one-worker pool and records the loop, engine, and thread identities. The identities remain identical across operations and only one engine is created. A two-worker test confirms distinct loop, engine, and thread identities. Shutdown tests confirm dispatcher closure and joined threads; failure tests confirm both ordinary continued use and runtime recreation.

Focused Step 4/protocol/Step 2/Step 3 suite: **44 passed, 0 failed**.

Broader non-database SNMP suite: **215 passed, 0 failed, 1 skipped**. The skipped test is the opt-in real-device integration test. Python compilation and `git diff --check` passed.

No timing improvement percentage is claimed. The deterministic lifecycle count changes from potentially one loop and engine per physical operation to one loop and engine per worker across multiple operations.

The next recommended optimization is to replace storage/environment/interface-alert N+1 persistence queries with set-based preloads while retaining the current schema and transaction semantics.
