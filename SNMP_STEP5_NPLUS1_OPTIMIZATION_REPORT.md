# SNMP Step 5 N+1 Optimization Report

## Result

Step 5 is complete. Storage latest-row lookup, environment latest-row lookup, and interface alert-state lookup now use current-device set-based preloads and in-memory maps. Transaction boundaries, ORM create/update/history behavior, alert rules, and external contracts are unchanged.

## N+1 locations traced

1. `backend/services/snmp_polling.py:SNMPPoller._persist_storage()` queried `LatestStorage` with `(device_id, volume_id)` inside the volume loop.
2. `backend/services/snmp_polling.py:SNMPPoller._persist_environment()` queried `LatestEnvironment` with `(device_id, sensor_id)` inside the sensor loop.
3. `backend/services/snmp_polling.py:SNMPPoller._evaluate_alerts()` queried `Interface` by `(device_id, interface_name)` inside the interface loop. It then called alert helpers which queried active alerts once for a down interface and up to twice for an up interface resolution.

## Changes

### Storage

All existing `LatestStorage` rows for the current device are loaded once and mapped by the unchanged `volume_id` identity. The loop updates the mapped row or creates the same new row it created previously. Newly created rows are immediately added to the map, preserving duplicate-key behavior within one payload. One `StorageStatistic` history object is still added for every valid volume with `total_bytes`.

### Environment

All existing `LatestEnvironment` rows for the current device are loaded once and mapped by the unchanged `sensor_id` identity. Status conversion, value conversion, sensor naming/type rules, latest updates, and one history object per sensor remain unchanged. Newly created rows are added to the map for consistent same-payload reuse.

### Interface alerts

For an interface poll, the code now loads current-device `Interface` rows once and active `Interface Down:` alerts once, ordered newest-first as before. Maps are built by interface ID and exact title. The existing business decisions remain:

- only administratively up interfaces with operational down state create critical alerts;
- exact-title active alerts suppress duplicates;
- operational recovery first matches interface ID, then the legacy exact-title fallback;
- only open/acknowledged, non-deleted alerts participate;
- the existing helper functions still create/notify/process incidents and resolve/process recovery.

The alert helpers gained an internal optional preloaded-state parameter. When omitted, their original query behavior is unchanged for all other callers. When explicitly supplied by SNMP polling, they use that state without repeating a query. Constructor/business exceptions are not hidden, and the transaction still commits only through the existing poll persistence boundary.

## Query-count proof

Deterministic fake-session tests use three storage volumes, three environment sensors, and three interfaces:

- storage latest lookup: 1 query for N volumes;
- environment latest lookup: 1 query for N sensors;
- interface lookup: 1 query for N interfaces;
- active interface-alert lookup: 1 query for N interfaces;
- no per-row commits were added.

The tests also verify existing-row updates, creation of missing latest rows, history-row counts, interface-down creation, active-alert deduplication, and resolution from preloaded state.

## Verification

- Focused Step 5 tests: **4 passed, 0 failed**.
- Broader non-database SNMP regression suite, including Steps 2–4: **219 passed, 0 failed, 1 skipped**.
- The skip is the opt-in real-device integration test.
- Python compilation and `git diff --check` passed.

No SNMP client, cache, root execution, worker runtime, scheduler, API, model/schema, migration, or frontend code was changed in Step 5.

The next recommended optimization is to consolidate the three normal successful poll commits into one transaction without changing persisted records.
