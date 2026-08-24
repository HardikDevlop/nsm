# API Performance And Loading Audit

Date: 2026-08-24

Scope: frontend API call flow, loading states, refresh behavior, caching, and the `192.168.100.1` SNMP device path.

Important: this is a read-only code audit. No application behavior was changed. Exact network milliseconds require a browser Network trace or server access log; this report records every statically verifiable endpoint, trigger, cache window, retry policy, and likely bottleneck.

## Executive Findings

1. `192.168.100.1` is not discovered live by the SNMP Devices list. The list reads database `Device` rows only. The backend excludes rows where `deleted_at IS NOT NULL`. If the IP is missing, soft-deleted, or stored with a different value, the list returns nothing.
2. The legacy `SNMPDashboard` has an infinite-looking loading state on request failure: its `catch` sets `error` but does not set `loading(false)`. A failed `/snmp/devices` call can therefore keep showing loading indefinitely.
3. `requestJson()` has no client-side timeout. Any backend SNMP call that waits for an unreachable device can keep the UI loading until the server, proxy, or browser eventually terminates it.
4. The optimized SNMP device list uses React Query plus a second API cache. Normal list reads are cached for 15 seconds in `api.ts`, while the query is considered fresh for 15 seconds. Duplicate in-flight GETs are deduplicated by the API helper.
5. The SNMP Monitoring page starts three requests in parallel on mount: `/overview?hours=24`, `/device-metrics?limit=200`, and `/discovery/monitoring/status`. Its first render waits for the slowest of those three.
6. Device detail/module pages can make live SNMP calls. The DB-backed overview is fast compared with `/system`, `/cpu`, `/memory`, `/interfaces`, `/environment`, `/lldp`, `/routing`, and similar collector endpoints, which may wait on SNMP timeout/retry behavior.
7. Several older pages use direct `useEffect` loading instead of React Query, so their calls do not share the same cache/deduplication policy.

## `192.168.100.1` Trace

### SNMP Devices page

File: `figma design/src/features/snmp/pages/SNMPDevices.tsx`

On mount, React Query calls:

```text
GET /api/v1/snmp/devices?page=1&page_size=25&sort_by=id&sort_order=asc
```

When the search box contains `192.168.100.1`, the request becomes:

```text
GET /api/v1/snmp/devices?page=1&page_size=25&search=192.168.100.1&sort_by=id&sort_order=asc
```

The backend route is `hardik/backend/api/snmp_device_routes.py:list_snmp_devices_optimized`.

The query searches `Device.ip_address`, `Device.hostname`, and `Device.mac_address`, then applies `Device.deleted_at IS NULL`. It does not perform an SNMP probe. Therefore:

- The IP must already exist in the application database.
- A soft-deleted row is intentionally hidden.
- A discovery result is not enough until it is persisted as a device.
- A device with no SNMP credential can still appear in the optimized list, but it may show `snmp_status=unknown`.

### Legacy SNMP dashboard

File: `figma design/src/features/snmp/pages/SNMPDashboard.tsx`

On mount, and again when the URL `deviceId` changes:

```text
GET /api/v1/snmp/devices
```

This page uses `listSNMPDevices()`, not the paginated optimized hook. If this request fails, the catch block sets the error but leaves `loading` unchanged. This is the strongest code-level explanation for a loading indicator that appears to run for a very long time.

### SNMP Monitoring page

File: `figma design/src/features/snmp/pages/SNMPMonitoring.tsx`

On mount, these start in parallel:

```text
GET /api/v1/overview?hours=24
GET /api/v1/device-metrics?limit=200
GET /api/v1/discovery/monitoring/status
```

The page filters `overview.devices` with `Boolean(device.snmp_version)`. A database device without `snmp_version` is removed from this page even if it exists in the general device inventory. This is another possible reason `192.168.100.1` is absent on this page.

## Timing And Caching

| Layer | Behavior | Value |
|---|---|---:|
| API GET cache | `src/lib/api.ts` memory/session cache | 15 seconds |
| API in-flight dedupe | Same authenticated GET path shares one promise | Until request completes |
| React Query global stale time | `src/lib/queryProvider.tsx` | 30 seconds |
| SNMP device list stale time | `useSnmpQueries.ts` | 15 seconds |
| SNMP device details stale time | `useSnmpQueries.ts` | 10 seconds |
| Most latest metrics hooks | `useSnmpQueries.ts` | 30 seconds |
| Module capability data | `useSNMPModules.ts` | 60 seconds |
| React Query retry | Global default | 1 retry |
| Window focus refetch | React Query | Disabled |
| Reconnect refetch | React Query | Disabled |
| `requestJson` timeout | Client | Not configured |

The 15-second cache is only used for GET requests without a signal/body. Mutations clear the GET cache. A slow first request is still slow; cache only helps later reads.

## Page And API Inventory

### SNMP pages

| Page | Initial calls | Live/refresh behavior |
|---|---|---|
| `SNMPDevices.tsx` | `/snmp/devices` | React Query; search/filter/page changes create a new query key |
| `SNMPDashboard.tsx` | `/snmp/devices` | Legacy direct effect; failed request can leave loading true |
| `SNMPMonitoring.tsx` | `/overview`, `/device-metrics`, `/discovery/monitoring/status` | Initial three-way `Promise.all`; service controls can start/stop all monitoring |
| `SNMPDeviceDetails.tsx` | Device overview/details and module data through SNMP hooks | Module navigation can trigger endpoint-specific reads |
| `SNMPGenericModulePage.tsx` | `/snmp/devices/{id}/{module}` and capability/config hooks | One module collector read per selected module |
| CPU, Memory, Interfaces, Storage, Environment pages | Module-specific SNMP endpoints | Query cache according to module hook |
| LLDP, Routing, VLAN, OID, Polling, Capabilities pages | Corresponding `/snmp/devices/{id}/...` endpoints | Mostly on mount; history pages include time-window parameters |
| `AddSNMPDevice.tsx` | Manual create/test/discover endpoints only on user action | SNMP test/discover can be slow because they contact the device |
| `SNMPDiscoveryPanel.tsx` | Discovery scan endpoints on user action | Direct scan/start/status calls; duration depends on target count and timeout |

### Monitoring and topology pages

| Page | Initial calls | Refresh behavior |
|---|---|---|
| `DeviceMonitoringList.tsx` | `/devices`, `/discovery/monitoring/status` | SSE connection; one fallback status refresh after stream failure |
| `DeviceMonitoring.tsx` | `/devices/{id}`, metrics, status history, device history, monitoring status | Metrics/status history every 15 seconds; SSE for live updates |
| `Topology.tsx` | `/snmp/topology`, inventory/device detail/module calls as needed | Topology refresh every 30 seconds; selected/expanded nodes can add calls |
| `ManualTopology.tsx` | Manual snapshot reads/reconcile plus device list | Change check every 120 seconds; saves/reconcile on actions |
| `ISPMonitoring.tsx` | Overview/monitoring/discovery-related calls | Monitoring interval and live collection can create repeated work |

### General pages

The CRUD pages use one initial list request from a mount `useEffect`, then mutation plus list reload after create/update/delete:

`Dashboard`, `AlertsManagement`, `AuditLogs`, `Compliance`, `DailyReport`, `DeviceCredentials`, `DeviceTypes`, `Events`, `Forensics`, `Incidents`, `InterfacesList`, `MonitoringJobs`, `Notifications`, `Organizations`, `PacketAnalysis`, `Reports`, `RoleManagement`, `ServerMonitoring`, `Sites`, `Thresholds`, `UserManagement`, and `Vendors`.

Most of these pages use direct API calls rather than the React Query cache. Their largest repeat patterns are:

- list on mount;
- reload after mutation;
- periodic refresh on dashboard/monitoring pages;
- chart/history endpoints with potentially large time windows;
- SSE or monitoring-status polling on live monitoring pages.

## Likely Slow Call Classes

### High risk: live SNMP collector calls

These can wait on device/network timeout and should be checked first in the browser Network panel:

```text
/snmp/devices/{id}/system
/snmp/devices/{id}/cpu
/snmp/devices/{id}/memory
/snmp/devices/{id}/interfaces
/snmp/devices/{id}/storage
/snmp/devices/{id}/environment
/snmp/devices/{id}/lldp
/snmp/devices/{id}/routing
/snmp/devices/{id}/vlans
/snmp/devices/{id}/poll
/snmp/devices/{id}/discover
/snmp/devices/{id}/test-snmp
```

### Medium risk: large aggregate requests

```text
/overview?hours=24
/device-metrics?limit=200
/discovery/monitoring/status
/discovery/device-history/{ip}?hours=24
```

These may be database-heavy or return large payloads, even when they do not contact the device directly.

### Lower risk: DB-backed list/detail requests

```text
/snmp/devices?page=...&page_size=...
/snmp/devices/{id}
/devices
/devices/{id}
/organizations
/sites
/vendors
/reports
/alerts
/events
/notifications
```

They can still be slow due to database joins/count queries, but they should not wait for an SNMP timeout.

## What To Check For `192.168.100.1`

1. In Network, filter `192.168.100.1` or `snmp/devices` and confirm whether the list request returns the IP.
2. Check the list response fields: `id`, `ip_address`, `deleted_at` behavior, `snmp_version`, `snmp_status`, and `status`.
3. If it is absent, verify the database row and whether it is soft-deleted. The frontend cannot display a row the optimized endpoint excludes.
4. If it is present in `/snmp/devices` but absent in `SNMPMonitoring`, check `snmp_version`; that page explicitly filters devices without it.
5. If the row is present but details keep loading, inspect the first slow endpoint after navigation. A live collector endpoint is more likely than the DB details endpoint.
6. If the request is pending with no response, the current client has no timeout. If it returns an error, the legacy dashboard may continue showing loading because of the missing `setLoading(false)` in its error path.

## Runtime Measurements Needed

The source can identify call order and policies, but not production response duration. For a complete timing report, capture one clean browser session and record:

| Field | Where to get it |
|---|---|
| Request start/end and duration | Browser Network tab |
| Waiting/TTFB | Network timing details |
| HTTP status and payload size | Network response/size columns |
| Backend `collection_ms` | SNMP system/collector response body where present |
| SQL/API server duration | Backend access log or request middleware |
| Number of calls per navigation | Network request count grouped by route |

## Recommended Fix Order (not applied)

1. Confirm the database/device record for `192.168.100.1` and its `deleted_at`, credential, and `snmp_version` values.
2. Fix the legacy dashboard error path so failed requests stop loading.
3. Add an explicit AbortController timeout to `requestJson` for live SNMP calls.
4. Keep DB-backed overview calls separate from live collector calls and show partial data while a collector is pending.
5. Standardize direct-effect pages on one query/cache policy to prevent repeated list requests.
6. Add request timing instrumentation in development and server access logs in production.
