# SNMP Step 3 Parallel Root Walk Report

## Result

Step 3 is complete. Independent table roots now execute concurrently with a configurable per-device limit of 3. Identity collection and vendor detection remain sequential prerequisites. Results are merged in the original declared root order after every submitted task finishes, preserving deterministic overwrite and output behavior.

## Root classification

- **Must remain sequential/dependent:** identity scalar GET, then vendor/device-type detection, then construction of the applicable root set. Normalization, OID registry construction, and collector execution remain after all root work.
- **Safe to run concurrently:** all roots within `_STANDARD_TABLE_WALKS`, vendor table roots, and `_DOMAIN_WALKS`. These are independent SNMP table reads. Tables combined later by interface, environment, MAC, inventory, or topology collectors have an aggregation dependency but no network-fetch dependency.

## Concurrency and deadline safety

`SNMPService._walk_roots()` uses a shared eight-thread orchestration executor and admits at most `SNMP_ROOT_CONCURRENCY` roots from one poll, default 3. The existing client executor remains the sole physical SNMP executor and stays capped at eight threads, so Step 3 does not increase physical SNMP concurrency or scheduler workers.

The existing 120-second operation budget is treated as the root phase's poll deadline. Each newly started root receives only the remaining budget. `SNMPClient.walk()` accepts this optional remaining operation budget but retains its existing configured timeout when no override is supplied. Request timeout (3 seconds), retry count (1), GETBULK, GETNEXT fallback, and cancellation behavior are unchanged. The orchestrator waits for submitted work to finish; roots cannot continue as abandoned orchestration futures after `_walk_roots()` returns.

## Partial results and ordering

Each root retains the previous independent failure behavior: timeout or exception is logged and omitted, while successful sibling dictionaries remain available. Empty successful walks remain empty. Aggregation iterates the original ordered root mapping rather than future-completion order, so concurrent completion cannot change which value wins if roots overlap.

## Observability

Each root emits a credential-free debug event containing root OID, operation, duration, status, and row count. Each root phase emits a summary with host, root count, succeeded, failed, timed out, and total duration. Step 2 continues to emit its cache hit/miss/wait/network/expiry events; cache state is not guessed or inferred by Step 3.

## Preservation

No API, database schema, frontend, scheduler interval/worker configuration, collector implementation, normalization rule, OID registry rule, persistence behavior, alert behavior, or polling-history behavior changed. SNMP v2c/v3 authentication and physical GET/GETBULK/GETNEXT behavior remain intact. Step 2 cache keys and single-flight implementation are unchanged and continue to wrap each physical root operation.

## Verification

Focused tests prove:

- independent roots overlap;
- the configured per-device limit is respected;
- identity completes before root work;
- a timed-out root does not erase successful siblings;
- all submitted root work is cleaned up before return;
- merge order is deterministic;
- later roots receive a decreasing remaining poll-deadline budget;
- deterministic serial-versus-parallel instrumentation observes overlap without claiming real-world speedup.

The focused Step 3, Step 2 cache/factory, protocol, bulk/fallback, endpoint, port, and guard subset passed **49 tests**. The broader non-database SNMP suite passed **210 tests**, with one opt-in real-device integration test skipped and two pysnmp deprecation warnings. Compilation and diff validation passed.

## Execution model

- **Before:** identity and vendor detection, followed by every independent table root serially; root deadlines could accumulate.
- **After:** identity and vendor detection remain first; up to three independent roots overlap per device, later roots receive the remaining root-phase deadline, and successful results merge in declared order.

The next recommended optimization is to reuse a long-lived event loop and `SnmpEngine` within each dedicated physical SNMP worker, with explicit worker ownership and shutdown.
