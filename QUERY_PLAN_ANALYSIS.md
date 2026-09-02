# PostgreSQL Query Plan Analysis

## Scope

The high-traffic NMS reads reviewed were:

- `GET /api/v1/snmp/devices`
- dashboard latest metrics reads
- polling history and status reads
- interface statistics reads

The primary list query filters active devices, optionally applies search and
status/module filters, sorts, counts, and fetches one page. Page metadata is
then loaded for credentials, identity, and monitoring configuration.

## Existing Index Coverage

No new index is justified by the current query shapes. Existing coverage is:

- `devices.ip_address`: unique index, also protects discovery deduplication.
- `devices.deleted_at`: active-device filtering.
- `ix_devices_deleted_status`: active device plus status filtering.
- `ix_devices_deleted_site`: active device plus site filtering.
- `monitoring_configs(device_id, module_name)`: unique constraint index.
- `polling_history(device_id, created_at)` and
  `polling_history(device_id, status, created_at)`.
- `interface_statistics(device_id, created_at)` and
  `interface_statistics(interface_id, created_at)`.
- `latest_* .device_id`: indexed on each latest metrics table.

Adding standalone indexes on `device_id`, `interface_id`, or `created_at`
would duplicate these existing indexes or the model-generated indexes.

## Before / After Shape

Before the device-list metadata optimization, a page required:

1. one count query,
2. one paginated device query,
3. one credentials query,
4. one identity query,
5. one monitoring-config query.

The page metadata is now loaded by one batched outer-join query. The normal
page path is therefore reduced from five database statements to three, while
pagination, filters, ordering, and response fields remain unchanged.

The latest metrics endpoint already uses one PostgreSQL statement with
correlated reads for CPU, memory, storage, interfaces, and environment. No
additional index or query rewrite is needed for that endpoint.

## Query Plans

The development PostgreSQL instance was unavailable during this audit
(`127.0.0.1:5432` did not respond), so `EXPLAIN (ANALYZE, BUFFERS)` output
could not be collected safely against production data. The expected plan for
the active-device list is an index-assisted scan on `deleted_at`/status (or a
planner-selected sequential scan for a small table), followed by the requested
sort and `LIMIT/OFFSET`. The metadata query uses indexed foreign-key joins on
`device_id`; PostgreSQL may choose hash joins for a larger page.

Before deployment, run the following with representative production statistics
and retain the output with the release record:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id, hostname, ip_address, model, status, last_seen
FROM devices
WHERE deleted_at IS NULL
ORDER BY id ASC
LIMIT 50 OFFSET 0;

EXPLAIN (ANALYZE, BUFFERS)
SELECT dc.device_id, dc.snmp_version,
       di.vendor, di.hostname, di.sys_name, di.mac_addresses,
       mc.module_name, mc.enabled, mc.status, mc.last_poll_at
FROM devices d
LEFT JOIN device_credentials dc ON dc.device_id = d.id
LEFT JOIN device_identity di ON di.device_id = d.id
LEFT JOIN monitoring_configs mc ON mc.device_id = d.id
WHERE d.id = ANY(:page_device_ids);
```

