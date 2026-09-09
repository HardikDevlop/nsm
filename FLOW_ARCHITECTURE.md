# NMS Flow Monitoring Architecture

## 1. Purpose and Constraints

This document defines an additive flow-monitoring subsystem for the existing
NMS. It is a design only; no UI, migration, route, collector, or scheduler
behavior is changed by this document.

The design preserves:

- Existing SNMP v2c/v3 credentials, OIDs, collectors and discovery.
- Existing JWT/RBAC, PostgreSQL data, alerts, topology, reports and API
  contracts.
- The existing FastAPI application and centralized APScheduler lifecycle.
- Existing device identity through `device_id`; flow records never create a
  second device inventory.

Flow ingestion is separate from SNMP polling because exporters send flows to
the NMS, while SNMP remains a pull-based device and interface telemetry path.

## 2. End-to-End Flow

```text
Exporter
  -> UDP listener (IPFIX/sFlow)
  -> bounded receive queue
  -> protocol decoder
  -> common normalizer
  -> validation + deduplication
  -> batch writer
  -> PostgreSQL flow tables / rollups
  -> retention worker
  -> read-only flow APIs
  -> alerts, reports and future UI
```

The receiver must acknowledge or consume packets without holding a database
connection. Decode and persistence are bounded separately so a slow database
cannot create unbounded memory growth.

## 3. Protocol Support

Each protocol has an adapter implementing the same interface:

```python
class FlowProtocolAdapter(Protocol):
    protocol: str

    def parse(self, payload: bytes, source_ip: str, source_port: int) -> Iterable[RawFlowRecord]: ...
```

| Protocol | Adapter responsibility | Device/exporter identity |
|---|---|---|
| IPFIX | Template lifecycle, enterprise fields, data sets and withdrawals | exporter IP + observation domain |
| sFlow | Datagram/sample decoding and sampled packet counters | agent address + sub-agent |

Only standards-compliant IPFIX and sFlow exporters are accepted. No vendor
identity is required; compatible exporters use the same protocol adapter.

Templates are cached per exporter, protocol and observation domain. A data
record received before its template is retained only as a bounded decode miss;
it is not guessed or converted into static data. Template expiry and malformed
packet counters are observable.

## 4. Common Normalized Schema

Normalization produces one `NormalizedFlowRecord` regardless of source
protocol. Protocol-specific fields remain in `raw_fields` JSON for evidence,
but reporting and querying use the common columns.

### Identity and timestamps

| Field | Type | Requirement |
|---|---|---|
| `id` | bigint | Database identity |
| `device_id` | bigint nullable | Matched NMS device, nullable for unresolved exporters |
| `exporter_ip` | inet/text | Source exporter address |
| `observation_domain` | text nullable | IPFIX domain or sFlow sub-agent |
| `protocol` | enum/text | `ipfix` or `sflow` for newly ingested records |
| `source_version` | text nullable | Protocol version, such as `5` for sFlow or `10` for IPFIX |
| `flow_start` | timestamp | Original start time normalized to UTC |
| `flow_end` | timestamp | Original end time normalized to UTC |
| `received_at` | timestamp | NMS receive time |
| `sampling_rate` | integer nullable | Effective sampling rate when supplied |

### Network dimensions

| Field | Type |
|---|---|
| `src_ip`, `dst_ip` | inet/text nullable |
| `src_port`, `dst_port` | integer nullable |
| `ip_protocol` | integer nullable |
| `ip_version` | smallint nullable |
| `src_as`, `dst_as` | integer nullable |
| `next_hop` | inet/text nullable |
| `src_country`, `dst_country` | text nullable |
| `input_interface_id`, `output_interface_id` | bigint nullable |
| `vlan_id` | integer nullable |
| `dscp` | smallint nullable |
| `tcp_flags` | integer nullable |

### Counters and source evidence

| Field | Type |
|---|---|
| `bytes` | bigint |
| `packets` | bigint |
| `octets_delta` | bigint nullable |
| `duration_ms` | bigint nullable |
| `direction` | text nullable |
| `flow_id` | text nullable |
| `sequence_number` | bigint nullable |
| `raw_fields` | JSONB | Original fields not represented above |
| `parse_warnings` | JSONB | Non-fatal normalization warnings |
| `record_hash` | text | Stable deduplication fingerprint |

Required validation: `bytes >= 0`, `packets >= 0`, valid timestamp ordering,
bounded field lengths, supported protocol, and a non-empty exporter identity.
Invalid records are counted and sent to a bounded dead-letter path; they do
not abort the receive loop.

## 5. Collector and Parser Layers

### Flow collector

`FlowReceiver` owns listeners, socket limits, source allowlisting, packet size
limits, receive metrics and backpressure. It must not import SQLAlchemy models
or perform per-packet commits.

Recommended listener configuration:

- One configured UDP/TCP endpoint per protocol or port.
- Maximum datagram size and maximum pending queue size.
- Optional exporter allowlist associated with a site or organization.
- Graceful stop that closes sockets, drains a bounded queue, then stops.
- No use of `asyncio.run()` inside request handlers or scheduler jobs.

### Parser

`FlowParserRegistry` selects an adapter using listener protocol and packet
metadata. Parsers are pure with respect to persistence: bytes in, raw records
out, parse counters emitted. Template caches are scoped to an exporter and
bounded with expiry.

### Normalizer

`FlowNormalizer` resolves exporter IP to the existing `Device` and
`Interface` records where possible. Unresolved records remain queryable with
`device_id = NULL` and a resolution status; they are not silently discarded.
Interface mapping uses exporter, interface index and observation domain, then
records an explicit ambiguity warning if more than one match exists.

## 6. PostgreSQL Storage

Storage is additive and should use a migration rather than `create_all` for
production changes.

### Tables

1. `flow_records`: normalized raw flow records, append-oriented and time
   partitionable by `received_at` or `flow_start`.
2. `flow_templates`: active protocol templates keyed by exporter, protocol,
   observation domain and template ID, with expiry metadata.
3. `flow_exporters`: exporter endpoint/configuration, protocol status, last
   packet time, packet/parse/error counters and optional `device_id`.
4. `flow_ingest_errors`: bounded operational evidence for malformed packets,
   missing templates and normalization failures.
5. `flow_rollups_5m` and `flow_rollups_1h`: aggregate facts for dashboard,
   report and trend APIs. Rollups are derived data and can be rebuilt from
   retained raw records where the retention policy allows.

### Keys and indexes

Use a unique `record_hash` only for the deduplication window, or a separate
deduplication table if partitioning prevents a global unique index. Initial
query-driven indexes should be limited to:

- `(device_id, flow_start DESC)` for device history.
- `(exporter_ip, received_at DESC)` for exporter health.
- `(src_ip, flow_start DESC)` and `(dst_ip, flow_start DESC)` only if traffic
  investigations require them.
- `(flow_start, protocol)` for time-window aggregation.
- `(record_hash, received_at)` for bounded duplicate detection.

Indexes must be justified with `EXPLAIN (ANALYZE, BUFFERS)` against production-
representative data before migration. Avoid indexes on every raw JSONB key.

Batch writes use `executemany`/PostgreSQL bulk insert and one transaction per
bounded batch. They must not reuse the per-device SNMP polling commit path or
hold a connection during parsing.

## 7. Retention and Backpressure

Retention is configurable per organization/site, with safe defaults documented
in deployment configuration rather than hard-coded into handlers:

- Raw records: short operational window, partition-drop deletion preferred.
- Five-minute rollups: medium-term trend window.
- Hourly rollups: long-term reporting window.
- Templates/exporter health/errors: retained longer than raw packets for audit.

The retention worker deletes or detaches complete partitions in bounded jobs,
records duration and failures, and never competes with the receive loop for an
unbounded transaction.

Backpressure behavior is explicit:

1. Queue depth warning.
2. Parser concurrency remains bounded.
3. Batch size or flush interval is reduced only within configured limits.
4. If the queue is full, packets are dropped with a counter and sampled error
   evidence; the process does not crash or allocate unbounded memory.

## 8. APIs

New flow APIs should be additive under `/api/v1/flows` and protected by new
RBAC codes. Existing endpoint contracts remain unchanged.

### Read APIs

- `GET /api/v1/flows/summary?from=&to=&device_id=&site_id=`
- `GET /api/v1/flows/records?from=&to=&device_id=&src_ip=&dst_ip=&protocol=&page=&page_size=`
- `GET /api/v1/flows/talkers?from=&to=&device_id=&limit=`
- `GET /api/v1/flows/interfaces?from=&to=&device_id=`
- `GET /api/v1/flows/protocols?from=&to=&device_id=`
- `GET /api/v1/flows/exporters`
- `GET /api/v1/flows/exporters/{exporter_id}/status`
- `GET /api/v1/flows/ingestion/status`

Responses must contain a stable envelope:

```json
{
  "items": [],
  "total": 0,
  "from": "2026-01-01T00:00:00Z",
  "to": "2026-01-01T01:00:00Z",
  "filters": {},
  "data_quality": {"unresolved_exporters": 0, "parse_errors": 0}
}
```

### Administrative APIs

- `POST /api/v1/flows/exporters` to register an exporter and protocol.
- `PATCH /api/v1/flows/exporters/{id}` to enable/disable or update mapping.
- `DELETE /api/v1/flows/exporters/{id}` to disable ingestion without deleting
  historical flow data.
- `POST /api/v1/flows/retention/run` for an explicitly authorized maintenance
  action.

All administrative routes require dedicated permissions such as
`flows:read`, `flows:create`, `flows:update`, `flows:delete` and
`flows:retention`. Device/site scoping must follow existing RBAC conventions.

## 9. Scheduler Integration

The existing centralized scheduler remains the owner of periodic work. Flow
receivers are application-managed services started once during application
lifespan, not one receiver per HTTP request.

Scheduler jobs should be limited to:

- Rollup aggregation at fixed intervals.
- Template and exporter health expiry checks.
- Retention and partition maintenance.
- Optional unresolved-exporter/device reconciliation.

Every flow job needs a stable ID such as `flows:rollup:5m` and
`flows:retention`, `replace_existing=True`, and a single-flight guard so a
restart or slow run cannot overlap the same job. Flow jobs must use bounded
database batches and release sessions before waiting on external work.

SNMP polling jobs remain unchanged. Flow ingestion does not trigger a full
SNMP poll. If an exporter is unresolved, a low-frequency reconciliation may
read existing device/interface inventory; it must not create duplicate devices
or credentials.

## 10. Alerts, Reports and Topology Integration

- Flow thresholds generate normalized alert candidates through the existing
  alert service, with a source such as `flow` and a stable fingerprint. Alert
  deduplication and acknowledgement remain existing behavior.
- Reports read rollups, not raw flow rows, unless an explicitly bounded detail
  export is requested.
- Topology may consume interface-level flow direction as an optional evidence
  layer, but flow data never replaces LLDP/CDP/SNMP topology facts.
- Existing dashboard and report APIs are not changed in the first delivery;
  new flow APIs provide the source for future UI integration.

## 11. Observability and Failure Handling

Important flow operations should emit structured metrics/logs with
`request_id` where an HTTP request exists, plus:

- packets received, decoded, normalized, persisted and dropped;
- bytes/records by protocol and exporter;
- parse errors, missing templates and unresolved device/interface counts;
- queue depth, batch size, flush duration and database write duration;
- rollup duration, retention duration and scheduler backlog;
- API `total_ms`, `db_ms`, `query_count` and result row count.

Failures are isolated by stage. A malformed packet cannot stop the listener; a
failed batch is retried with bounded backoff and then recorded for operator
action; a failed rollup does not delete raw data.

## 12. Delivery Sequence

1. Add feature flags/configuration and protocol-independent interfaces.
2. Add migrations for exporter, template, raw, error and rollup tables.
3. Implement protocol adapters for IPFIX and sFlow without vendor-specific assumptions.
4. Add batch persistence and retention with PostgreSQL query-plan tests.
5. Add read/admin APIs and RBAC permissions without changing existing routes.
6. Integrate lifecycle and scheduler jobs with restart/single-flight tests.
7. Add optional alert/report adapters.
8. Add real-exporter integration tests separately from unit parser fixtures.

No UI implementation is included in this design.
