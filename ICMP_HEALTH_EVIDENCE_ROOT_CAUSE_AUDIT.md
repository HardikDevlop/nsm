# ICMP Health Evidence Root-Cause Audit

Read-only audit based on source and supplied runtime facts. No code, database, service, scheduler, SNMP, Redis, or frontend state was changed.

## End-to-end path

FastAPI `lifespan()` calls `get_engine().restore_enabled_devices()`. That loads non-deleted `Device` rows with `monitoring_status=True`, passes their real `device_id` and `ip_address` to the singleton `MonitorEngine.start_all()`, and starts the monitor loop. The supplied runtime count of 11 therefore represents the persisted monitoring opt-in population used by the engine.

The loop submits each registered IP to `_ping_one()` through the engine-lifetime executor. `_ping_one()` calls the existing `_ping()` implementation, updates process-memory `MonitoredDevice` counters/status/history, and calls `_persist_ping_result()` when the monitored object has a real `device_id`.

The in-memory summary (`total_monitored`, `up`, `down`, `unknown`, `loop_running`) is computed directly from `MonitorEngine._devices`. It is not the source used by `derive_device_health()`.

## ICMP persistence targets

`_persist_ping_result()` and its batch path write the following:

- `Device.last_seen`: updated on every reachable ping. The transition path also updates `Device.status` to `online`/`offline` and `last_status_change`; uptime/downtime counters and `DeviceStatusHistory` are updated on confirmed transitions.
- `DeviceMetric`: one row per ping is intended. Transition/unknown paths insert directly; steady-state rows are queued and inserted by `_flush_metric_batch()` with `latency`, `packet_loss` (`0.0` success, `100.0` failure), and the supplied timestamp.
- `DeviceStatusHistory`: only confirmed status transitions, not every ping.
- Alerts: offline transition may create an alert; this is unrelated to freshness.

There is no dedicated ICMP evidence table, ICMP-specific `last_success_at`, or ICMP-specific `last_attempt_at`. `PollingHistory` is SNMP/module history and is not written by realtime ICMP. `MonitoringConfig` is also SNMP configuration and is not updated by realtime ICMP.

## Exact health-reader fields and semantics

`derive_device_health()` reads:

```text
Device.monitoring_status
Device.last_seen
Device.status
MonitoringConfig.interval_seconds (minimum among enabled configs)
```

It computes `icmp_age = now - Device.last_seen`, with `now=utc_now()` (aware UTC). ICMP freshness is:

```text
icmp_age is not None and icmp_age <= min(enabled SNMP interval, default 60) * 3
```

If fresh and `Device.status == "online"`, ICMP is reachable; if fresh and status is offline, it is unreachable. Otherwise, when monitoring is enabled and a timestamp exists, ICMP is stale.

The reader’s `_aware()` function treats a naive database datetime as Asia/Kolkata and converts it to UTC. This is a deliberate legacy interpretation in the health contract, but it conflicts with the realtime writer’s actual naive-UTC values.

## Writer versus reader comparison

The same device identity is used: startup loads `Device.id` into `MonitoredDevice.device_id`, and persistence queries `Device.id == dev.device_id`. There is no IP-based health lookup in the persistence/derivation path.

The evidence target is also nominally the same: realtime writes `Device.last_seen`, and health reads `Device.last_seen`. Successful steady samples are queued into `DeviceMetric`, and the batch worker commits both the metric row and `Device.last_seen` update. Transition samples are committed immediately. The batch interval is `METRIC_BATCH_INTERVAL` and flushes on the batch-size threshold or shutdown; the source does not show a batching delay remotely comparable to the observed five-and-a-half-hour age.

The decisive mismatch is timestamp semantics:

- `_persist_ping_result()` generates `now = datetime.utcnow()`, a naive value semantically representing UTC.
- `_flush_metric_batch()` persists the same timestamp supplied by that writer.
- `derive_device_health()` sees the naive `Device.last_seen` and interprets it as India local time, then converts it to UTC.

For example, a writer value representing `12:15 UTC` is interpreted by the reader as `12:15 IST = 06:45 UTC`, making it appear approximately 5h30m old. That exceeds the normal freshness window, so active realtime polling derives `stale` even while the loop reports UP.

The in-memory `_ping_one()` display timestamp uses an IST string, but that value is only process-memory history and is not the health evidence column. It does not repair the persisted timestamp mismatch.

## Batching and commit behavior

Steady same-state pings close their per-ping session, enqueue a tuple, and return. The dedicated batch thread flushes periodically; at flush it opens its own `SessionLocal`, adds `DeviceMetric` rows, updates `Device.last_seen` for successful rows, commits, and restores rows to the queue on failure. Confirmed transitions flush pending batches first and then commit their transition and metric synchronously.

Thus successful UP samples are designed to reach durable storage, and the runtime loop being healthy makes persistence plausible, but source audit alone cannot prove the current host rows were committed. The timestamp mismatch is sufficient to explain the exact stale contradiction. A failed batch would log `ICMP_METRIC_BATCH_FAILED`; a transition persistence failure logs `DB persist failed`.

## Other timestamp risks in this path

The ICMP writer still contains `datetime.utcnow()` in `_persist_ping_result()` and `datetime.utcnow()` in a separate realtime-monitoring elapsed calculation. `_ping_one()` creates an IST string for in-memory `last_check/history`. `derive_device_health()` uses aware UTC now but intentionally treats naive DB values as IST. This path therefore does not have consistent canonical aware-UTC semantics.

No latest-row query is used for ICMP freshness: health reads the single `Device.last_seen` field. DeviceMetric latest rows are used by overview metrics, not by the ICMP freshness decision. No later source writer was found that intentionally overwrites a fresh `Device.last_seen` with older data; the batch writer can only update it from queued samples, whose ordering/commit timing should be checked if host evidence shows a separate anomaly.

## Restart identity

`restore_enabled_devices()` selects the same real `Device.id` records that health derivation receives from overview. It filters `deleted_at IS NULL` and `monitoring_status IS TRUE`. The current count of 11 is therefore consistent with the active ICMP registry, subject to the supplied runtime observation.

## Required host evidence command

If live DB confirmation is needed, run this read-only PostgreSQL command on the real host. It reports the actual discovered fields: device identity, monitoring flag, `last_seen`, latest `DeviceMetric.created_at` overall (attempt), latest successful metric by `packet_loss=0`, latest persisted status, and age relative to UTC now.

```bash
psql "$DATABASE_URL" -x -c "WITH monitored AS (SELECT d.id,d.ip_address,d.monitoring_status,d.last_seen,d.status FROM devices d WHERE d.deleted_at IS NULL AND d.monitoring_status IS TRUE), latest AS (SELECT DISTINCT ON (m.device_id) m.device_id,m.created_at AS latest_metric_at,m.packet_loss AS latest_packet_loss,m.latency AS latest_latency FROM device_metrics m JOIN monitored d ON d.id=m.device_id ORDER BY m.device_id,m.created_at DESC,m.id DESC), success AS (SELECT DISTINCT ON (m.device_id) m.device_id,m.created_at AS latest_success_at FROM device_metrics m JOIN monitored d ON d.id=m.device_id WHERE m.packet_loss=0.0 ORDER BY m.device_id,m.created_at DESC,m.id DESC) SELECT d.id AS device_id,d.ip_address,d.monitoring_status,d.last_seen,l.latest_metric_at,s.latest_success_at,d.status AS persisted_status,EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - d.last_seen)) AS last_seen_age_seconds,EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - l.latest_metric_at)) AS metric_age_seconds,l.latest_packet_loss,l.latest_latency FROM monitored d LEFT JOIN latest l ON l.device_id=d.id LEFT JOIN success s ON s.device_id=d.id ORDER BY d.id;"
```

## Conclusion

The realtime ICMP loop and derived-health reader are not using consistent timestamp semantics. The writer persists naive UTC, while the reader interprets naive values as IST. This makes fresh successful ICMP evidence appear approximately 5h30m stale. The runtime summary is process memory, so it can remain UP independently of the stale persisted health evidence. No health semantics were changed in this audit and no direct “mark online from memory” shortcut is recommended.

REALTIME ICMP LOOP RUNNING: YES
REALTIME MONITORED DEVICES: 11
REALTIME UP/DOWN SOURCE: Process-memory `MonitorEngine._devices` statuses from `_ping_one()`
DERIVED HEALTH ICMP SOURCE: Persisted `Device.monitoring_status`, `Device.last_seen`, and `Device.status`
WRITER AND HEALTH READER USE SAME EVIDENCE: PARTIAL
SUCCESSFUL UP SAMPLES DURABLY PERSISTED: UNPROVEN
LAST SUCCESS UPDATED BY REALTIME POLLS: YES
LAST ATTEMPT UPDATED BY REALTIME POLLS: YES
TIMESTAMP SEMANTICS CONSISTENT: NO
DEVICE IDENTITY MAPPING CONSISTENT: YES
BATCHING/FLUSH ISSUE FOUND: NO
STALE QUERY/LATEST-ROW ISSUE FOUND: NO
OVERWRITE/RACE FOUND: UNPROVEN
PRIMARY ROOT CAUSE: Realtime ICMP persists naive UTC timestamps while derive_device_health interprets naive database timestamps as Asia/Kolkata, adding approximately 5h30m to evidence age
SECONDARY ROOT CAUSES: Process-memory summary is independent of persisted health; steady samples are asynchronously batched; no dedicated persisted ICMP success/attempt fields exist
LIVE DB COMMAND REQUIRED: YES
CODE CHANGED: NO
DATABASE CHANGED: NO
SNMP/SCHEDULER CHANGED: NO
SAFE FOR FIX IMPLEMENTATION: YES
