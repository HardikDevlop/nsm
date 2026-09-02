# One-Device End-to-End Verification Report

Date: 2026-08-29
Project: current NMS in `hardik/`
Scope: read-only verification only. No code was modified, no poll/discovery was triggered, and no mock/static data was inserted.

## Result

**No existing monitored device could be selected.** The first required step, reading the PostgreSQL device and monitoring records, was blocked because PostgreSQL was unavailable. Consequently, no credential record was read and no live SNMP operation was attempted.

This means the domain statuses below are `FAILED` at the shared runtime/database stage. They are **not** `UNSUPPORTED BY DEVICE`: device capability and OID responses were never observed. No domain is marked `WORKING`.

## Trace Status

| Trace stage | Status | Evidence |
|---|---|---|
| Device record | FAILED | PostgreSQL at `127.0.0.1:5432` returned no response. |
| Monitored-device selection | FAILED | Could not query devices, monitoring jobs/configuration, or enabled state. |
| Credentials | FAILED | Could not query `device_credentials`; no credential was read or exposed. |
| SNMP connection | FAILED | Not attempted because no real device/credential could be selected. |
| Collector | FAILED | Not attempted; source path is `_live_collect()` in `backend/api/snmp_device_routes.py`, backed by `SNMPService`. |
| Database persistence | FAILED | Could not inspect or write/read device metrics, identity, interfaces, or polling history. |
| Monitoring API | FAILED | FastAPI failed during lifespan before serving routes. |
| Frontend | FAILED | Frontend dev server failed to bind `127.0.0.1:5173` with `EPERM`; no page request was possible. |

## Domain Verification

| Domain | Status | Runtime reason |
|---|---|---|
| Identity | FAILED | Device and identity tables could not be queried; no SNMP identity response was collected. |
| Interfaces | FAILED | Device/interface records could not be queried; no interface collector/API request ran. |
| CPU | FAILED | Latest/history data could not be queried; no live domain poll ran. |
| Memory | FAILED | Latest/history data could not be queried; no live domain poll ran. |
| Storage | FAILED | Latest/history data could not be queried; no live domain poll ran. |
| Routing | FAILED | No device capability or routing response could be checked. |
| ARP | FAILED | No device capability or ARP response could be checked. |
| MAC | FAILED | No device capability or MAC-table response could be checked. |
| VLAN | FAILED | No device capability or VLAN response could be checked. |
| LLDP | FAILED | No device capability or LLDP response could be checked. |
| Latest metrics | FAILED | `GET /api/v1/snmp/devices/{device_id}/metrics/latest` was unreachable because FastAPI was not serving. |
| Metric history | FAILED | History endpoint/database query could not run. |
| Polling history | FAILED | `GET /api/v1/snmp/devices/{device_id}/polling-history` was unreachable and `polling_history` could not be queried. |

## Exact Runtime Checks

### PostgreSQL

Command:

```bash
pg_isready -h 127.0.0.1 -p 5432
```

Output:

```text
127.0.0.1:5432 - no response
```

Command:

```bash
psql -h 127.0.0.1 -d postgres -c 'SELECT 1;'
```

Output:

```text
psql: error: connection to server at "127.0.0.1", port 5432 failed: could not create socket: Operation not permitted
```

Because this failed, the following read-only selection query could not be executed:

```sql
SELECT d.id, d.hostname, d.ip_address, d.status,
       c.id AS credential_id, c.snmp_version,
       m.module_name, m.enabled
FROM devices d
LEFT JOIN device_credentials c ON c.device_id = d.id
LEFT JOIN monitoring_configs m ON m.device_id = d.id
WHERE d.deleted_at IS NULL
ORDER BY d.id;
```

No device ID is therefore claimed.

### FastAPI

Command from `/home/agnigate/Desktop/NMS/hardik`:

```bash
timeout 20s .venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Relevant output:

```text
INFO:     Waiting for application startup.
psycopg.OperationalError: connection is bad: no error details available
sqlalchemy.exc.OperationalError: (psycopg.OperationalError) connection is bad: no error details available
ERROR:    Application startup failed. Exiting.
```

Failing stage: `backend.main.lifespan`, at `Base.metadata.create_all(...)`, before migrations, scheduler initialization, or route serving.

### Frontend

Command from `/home/agnigate/Desktop/NMS/figma design`:

```bash
timeout 15s npm run dev -- --host 127.0.0.1 --port 5173
```

Output:

```text
error when starting dev server:
Error: listen EPERM: operation not permitted 127.0.0.1:5173
code: 'EPERM'
```

## Source-Level Trace Map

The source confirms the intended path, but this report does not treat source presence as runtime success.

| Layer | Actual project evidence |
|---|---|
| Device and credentials | `Device` and `DeviceCredential` in `backend/models/__init__.py`; credentials are selected by `_get_credentials()`. |
| Identity/capabilities | `DeviceIdentity` and `DeviceCapabilities` in `backend/models/identity.py`; endpoints are `/api/v1/snmp/devices/{id}/identity` and `/capabilities`. |
| SNMP connection/collector | `_live_collect()` in `backend/api/snmp_device_routes.py` imports `SNMPService` and uses stored credentials. |
| Domain endpoints | `/cpu`, `/memory`, `/storage`, `/interfaces`, `/routing`, `/vlans`, `/lldp`, `/arp`, and `/mac-table` are defined in `backend/api/snmp_device_routes.py`. |
| Persistence | SNMP models include `DeviceMetric`, `DeviceInterface`, and `PollingHistory`; identity models store identity/capability state. |
| Latest metrics | `GET /api/v1/snmp/devices/{id}/metrics/latest` reads latest-value tables in one database query. |
| Poll history | `GET /api/v1/snmp/devices/{id}/polling-history` reads `PollingHistory`; polling stats reads the same model. |
| Frontend | Existing API declarations are in `figma design/src/lib/api.ts`; runtime page verification was blocked by the Vite bind failure. |

## What Is Required to Complete This Check

1. Restore PostgreSQL and confirm `pg_isready` reports accepting connections.
2. Select one real device with an enabled monitoring job and record only its non-secret ID/hostname.
3. Read its stored credential metadata without exposing secrets.
4. Run the existing SNMP test/poll path using its stored v2c or v3 credential, preserving timeout/retry/OIDs.
5. Query each domain endpoint and classify an explicit unsupported-OID/device response as `UNSUPPORTED BY DEVICE`, not failure.
6. Verify persisted identity, interfaces, latest metrics, metric history, and polling history.
7. Load the corresponding frontend page and confirm displayed values match the API response.

