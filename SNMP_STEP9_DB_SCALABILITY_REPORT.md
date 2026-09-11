# SNMP Step 9 Database Scalability Report

## Outcome

Static query/index matching found eight justified composite/partial indexes. An idempotent application-managed migration adds them without altering tables or deleting data. SNMP retention is explicitly configurable but disabled by default; no cleanup job or deletion was added. Step 8 notification status persistence now uses one SQLAlchemy executemany update instead of one SELECT/update per notification.

PostgreSQL is unavailable in this environment, so live `EXPLAIN (ANALYZE, BUFFERS)` and production row counts are **RUNTIME VERIFICATION PENDING**. No query-plan or timing result is invented.

## Table inventory and growth

All listed SNMP model tables use integer `id` primary keys and `created_at`/`updated_at` audit timestamps unless noted. Foreign-key deletion behavior is unchanged.

| Table | Key/FKs and important time | Hot filters/order | Existing support before Step 9 | Growth |
|---|---|---|---|---|
| `cpu_statistics` | PK `id`; FK/index `device_id`; `created_at` | device + time range, time ASC | separate device/time indexes only | HIGH: up to 1 row/minute/device (1,440/day) |
| `memory_statistics` | same | device + time range, time ASC | separate indexes | HIGH: up to 1,440/day/device |
| `storage_statistics` | PK; FK/index device; `created_at`; mount name | device + time range | separate indexes | HIGH: up to 288 × volume count/day/device |
| `environment_statistics` | PK; FK/index device; `created_at`; sensor name | historical/device reads when used | separate indexes | HIGH where enabled: 288 × sensor count/day/device |
| `interface_statistics` | PK; FK/index device and interface; `created_at` | device/interface/time; latest previous row ordered time DESC, id DESC; charts time ASC | device+time and interface+time composites, but neither fully matches Step 7 device/interface ranking | **HIGHEST**: up to 5,760 × interface count/day/device at 15 seconds |
| `polling_history` | PK; FK/index device; collector/status indexes; `created_at` | device + time + id DESC + limit 500; device + id DESC + limit 10; device/collector latest | device+time and device/status/time | HIGH: approximately 20,305 rows/day/device if all default modules are enabled |
| `device_performance` | PK; FK/index device; `created_at` | no current Step 6 scheduled writer found | separate indexes | LOW currently |
| `power_statistics`, `poe_statistics` | PK; FK/index device; `created_at` | no current scheduled writer found | separate indexes | LOW currently |
| `latest_cpu`, `latest_memory` | PK; unique/index device; `polled_at` | exact device | unique device index | bounded: 1/device |
| `latest_storage` | PK; FK/index device; unique device+volume; `polled_at` | all rows for device | unique composite begins with device | bounded by current volumes/device |
| `latest_interface` | PK; FK/index device/interface; unique device+interface; `polled_at` | all device interfaces; device+oper status | unique composite and device/status index | bounded by interfaces/device |
| `latest_environment` | PK; FK/index device; unique device+sensor; `polled_at` | all sensors for device | unique composite begins with device | bounded by sensors/device |
| `monitoring_configs` | PK; FK/index device; unique device+module; status and next-poll indexes | enabled+status load; exact config ID; device/module | unique composite plus singles | LOW/bounded by modules/device |
| `monitoring_fields` | PK; FK/index config; unique config+field | config/field | unique composite | LOW/bounded configuration |
| `device_inventory` | PK; FK/index device | device | device index | LOW |
| `device_interfaces` | PK; FK/index device; unique device+ifIndex | device/ifIndex | unique composite | LOW/bounded |
| `oid_cache` | PK; FK/index device; unique device+OID | device/OID | unique composite | LOW/bounded by observed OIDs |
| `snmp_traps` | PK; optional FK/index device; source index; `created_at` | source/device/time when queried | single indexes | potentially HIGH, but asynchronous traps are outside scheduled polling writes |
| `vlan_information`, `lldp_neighbors`, `routing_table`, `system_health`, `alarms` | PK; device FK/index; `created_at` | limited/no current scheduled normalized writer | single/field indexes | LOW currently |
| `device_capabilities` | device identity; JSON capability detail; updated time | exact device or batched device IDs | device lookup support | bounded: updated snapshot, not append-only topology history |
| `alerts` | PK; device/interface FKs; status/severity/time/deleted fields | device+title+active status+not-deleted dedup; interface/status resolution; global status/time | device/status/time and interface/status | MEDIUM; dedup bounds active repeats but resolved/new conditions append |
| `notifications` | PK; alert FK; status/sent time | Step 8 update by notification PK | primary key | MEDIUM; one row per eligible recipient per created alert |

Growth figures are code-derived upper patterns based on configured default intervals, not live row counts. Disabled modules and unsupported/missing data reduce actual writes.

## Hot-query audit

- Latest metrics: `WHERE device_id = ?`; latest CPU/memory use `first`, storage/interface/environment use all current-device rows. Unique/device-leading indexes already support these.
- CPU/memory/storage history charts: `WHERE device_id = ? AND created_at >= ? ORDER BY created_at ASC`; no limit in several routes. New device/time composites support range and ordering, though response volume remains caller-window dependent.
- Interface charts: `WHERE device_id = ? AND interface_id = ? AND created_at >= ? ORDER BY created_at ASC`; other route uses interface/time. New device/interface/time index matches the complete predicate.
- Step 7 previous sample: current device, relevant interface IDs, window partition by interface, ordered `created_at DESC, id DESC`; new four-column index matches filtering/ranking and tie-break order.
- Polling history: device/time range ordered `id DESC LIMIT 500`; device ordered `id DESC LIMIT 10`; device/collector latest patterns. New device/id and device/collector/time indexes supplement the existing device/time index.
- Alert evaluation: device + exact title + active status + `deleted_at IS NULL`; new partial active-alert index matches this. Interface recovery retains the existing interface/status index.
- Monitoring status: startup filters enabled/status; job updates use PK; device module reads use the existing unique device/module key. No additional index was justified.
- Topology/capability reads: exact/batched `DeviceCapabilities.device_id` and JSON snapshot reads. No append-only topology history exists in this path and no new index was justified.
- Notification status: primary-key updates. Step 9 supplies one parameter batch to a single `UPDATE notifications ... WHERE id = ?` executemany operation.

## Index migration

Migration `20260910_0045_snmp_scalability_indexes` uses `CREATE INDEX IF NOT EXISTS` and adds:

1. `ix_cpu_statistics_device_time (device_id, created_at DESC, id DESC)`
2. `ix_memory_statistics_device_time (device_id, created_at DESC, id DESC)`
3. `ix_storage_statistics_device_time (device_id, created_at DESC, id DESC)`
4. `ix_environment_statistics_device_time (device_id, created_at DESC, id DESC)`
5. `ix_interface_statistics_device_interface_time (device_id, interface_id, created_at DESC, id DESC)`
6. `ix_polling_history_device_collector_time (device_id, collector, created_at DESC, id DESC)`
7. `ix_polling_history_device_id_desc (device_id, id DESC)`
8. partial `ix_alerts_active_device_title_status (device_id, title, status) WHERE deleted_at IS NULL`

Existing indexes were not removed. Some single-column indexes may become less useful after live plan/statistics review, but none is proven redundant without PostgreSQL usage statistics, so removal would be premature.

## Retention proposal

No scheduled SNMP history retention existed. `SNMP_HISTORY_RETENTION_DAYS` is now defined with default `0`, meaning disabled. It deliberately has no automatic deletion implementation in Step 9.

Recommended future policy, requiring explicit operator enablement and bounded deletion batches:

- interface history/high-frequency metrics: 30–90 days;
- CPU/memory history: 90–180 days;
- storage/environment history: 180 days;
- polling history: 90 days;
- alerts/events: policy/compliance-driven, commonly 1–3 years;
- topology snapshots: no append-only SNMP topology table currently exists; retain capability latest state indefinitely.

No data was deleted.

## Bulk-write review

Remaining opportunities, not implemented here:

- interface, storage, and environment history objects could use grouped `add_all()`; SQLAlchemy already flushes pending ORM inserts together, so proof is needed before changing semantics;
- large interface latest/history persistence could use PostgreSQL upsert/bulk insert, but this is a broader persistence rewrite;
- polling history is one row per module poll and does not benefit materially from batching under the current scheduler unit of work.

Step 8 notification delivery outcomes were safe to batch because each row is independently keyed by primary key and retains its exact status/sent timestamp. One executemany call replaces N SELECT/update lookup cycles; external delivery order and semantics are unchanged.

## Verification

Focused tests verify migration registration, all eight idempotent index definitions, the partial-index predicate, the Step 7 index column order, retention disabled by default, and one bulk notification-status execute for three distinct outcomes.

Broader non-database SNMP/incident suite: **239 passed, 0 failed, 1 skipped**. The skipped test is opt-in live-device integration. Python compilation and `git diff --check` passed.

Live PostgreSQL query plans and migration execution remain pending because the configured PostgreSQL service is inaccessible.
