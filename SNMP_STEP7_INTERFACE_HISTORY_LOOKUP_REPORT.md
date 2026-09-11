# SNMP Step 7 Interface History Lookup Report

## Result

Step 7 now loads at most one deterministic previous counter sample per relevant interface. It replaces historical over-fetching without changing interface identities, formulas, persistence, alerts, transaction behavior, or external contracts.

## Previous query model

`backend/services/snmp_polling.py:SNMPPoller._persist_interfaces()` already used one set-based query rather than one query per interface:

```text
device_id = current device
interface_id IN (current database interface IDs plus legacy ifIndex fallbacks)
ORDER BY interface_statistics.id DESC
load all matching history rows
```

Python then iterated every returned row and used `setdefault()` to retain only the first row for each interface. Therefore this was not a query-count N+1, but it was an unbounded historical row/data-volume over-fetch that grew with retention.

The previous sample fields consumed by the unchanged delta path are `rx_octets`, `tx_octets`, optional `rx_packets`, optional `tx_packets`, `error_rate`, and `created_at`. Matching first uses the stable current device-scoped `Interface.id`, retaining the legacy same-device ifIndex fallback.

## New query model

`SNMPPoller._load_latest_interface_statistics()` performs one device- and relevant-interface-scoped query with:

```text
ROW_NUMBER() OVER (
  PARTITION BY interface_id
  ORDER BY created_at DESC, id DESC
)
```

Only rows ranked 1 are joined back to `InterfaceStatistic`. This returns at most one row per relevant interface. Timestamp is the primary latest criterion; row ID deterministically breaks equal-timestamp ties. The device predicate prevents an interface ID or legacy ifIndex from another device from participating.

An empty relevant-interface set returns immediately without issuing a query.

## Semantic preservation

No calculation code changed. Inbound/outbound octet deltas, packet-rate calculation, error-rate calculation, elapsed-time behavior, utilization assignment, and `counter_delta()` reset/wrap handling remain byte-for-byte on their prior path. First samples still have no previous-counter map and retain `None` rates. Latest-interface updates, one new history sample per current interface, error/discard fields, interface alerts, polling history, Step 5 preloads, and the Step 6 transaction are untouched.

## Deterministic proof

The query-shape test inserts:

- two historical rows for interface 11;
- two equal-timestamp rows for interface 12;
- a newer row for another device using interface 11;
- a newer row for an unrelated interface.

For device 7 and relevant interfaces `{11, 12}`, exactly one SELECT returns exactly two rows: the newest row for interface 11 and the larger-ID row for interface 12. The other device and unrelated interface are excluded. A separate first-sample test proves an empty identity set performs zero queries.

Focused Step 5–7 tests: **9 passed, 0 failed**.

Broader non-database SNMP regression suite: **224 passed, 0 failed, 1 skipped**. The skipped test is the opt-in real-device integration test. Python compilation and `git diff --check` passed.

PostgreSQL is unavailable in the current environment, so live PostgreSQL execution-plan and transaction verification is **RUNTIME VERIFICATION PENDING**. The window query was executed successfully through SQLite for deterministic semantic/query-count coverage; no PostgreSQL runtime result is claimed.

The next recommended optimization is to move synchronous alert notification delivery out of the poll transaction while preserving durable notification creation.
