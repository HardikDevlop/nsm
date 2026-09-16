# Health Contract Adoption and Refresh Consolidation Report

## Scope

Step 5 only. No collector, scheduler interval, timezone helper, historical data, or page visual redesign was changed. Runtime verification is explicitly deferred to the actual host.

## Health contract adoption

`backend/services/device_health.py` remains the single derived-health calculation. The overview endpoint now derives each device's current health and exposes it additively as `devices[].health`; raw `devices[].status` remains the last-known/backward-compatible field. Overview counts now use derived health rather than blindly counting raw `Device.status == online`, with `summary.health_counts` for ONLINE/OFFLINE/DEGRADED/STALE/UNKNOWN.

The existing monitoring-data endpoint already exposes the same `health` object. SNMP failure remains separate from device liveness and is represented as DEGRADED when ICMP is reachable. No topology node/link/discovery logic was changed.

## Refresh ownership audit

| Page/domain | Refresh mechanism found | Duplicate conclusion | Action |
|---|---|---|---|
| Dashboard/overview | Page timer plus overview API cache | Same API ownership not proven from shared hook usage | No speculative removal |
| SNMP module data | React Query `useModuleData`, interval from persisted module config | Query key includes device/module | Retained |
| SNMP device queries | React Query hooks | Device/module keys are parameterized | Retained |
| Device Monitoring | Existing interval/SSE/manual state paths | Requires page-specific runtime inspection | Not changed |
| Topology | Existing timers/live rebuild paths | Multiple domains, not proven same-resource duplicate | Not changed |
| Manual Topology | Existing topology synchronization timers | Separate topology data domain | Not changed |
| Shared `useRealtimeData` | `setInterval` helper exists but its specialized hooks have no consumers in current `src` search | No active duplicate consumer found | Retained for compatibility |

No verified same-resource `setInterval + React Query` path was safe to remove in this step. Refresh ownership changes were therefore limited to health adoption; speculative global timer removal was avoided.

## Query key review

SNMP keys include device ID, module, interface ID, or time range where applicable. No verified collisions were found/fixed. Monitoring query behavior continues to use React Query cancellation/query-key semantics for late-response protection.

## Required summary

- RAW DEVICE.STATUS CONSUMERS: **10 backend writer/consumer groups plus frontend display consumers**
- CURRENT-HEALTH CONSUMERS MIGRATED: **2 API domains** (overview and monitoring data)
- LEGACY RAW STATUS CONSUMERS REMAINING: **many, intentionally** — historical/last-known status, administrative transitions, topology compatibility, and pages not yet in page-by-page verification
- OVERVIEW DERIVED HEALTH: **PASS**
- DEVICE LIST DERIVED HEALTH: **PARTIAL** — overview list is adopted; generic `/devices` list still preserves raw response contract
- DEVICE DETAIL DERIVED HEALTH: **PARTIAL** — monitoring-data detail is adopted; legacy CRUD/SNMP detail paths retain raw fields
- TOPOLOGY HEALTH DISPLAY: **NOT CHANGED**
- FRONTEND REFRESH DOMAINS AUDITED: **7**
- DUPLICATE FETCH PATHS FOUND: **0 verified same-resource paths**
- DUPLICATE FETCH PATHS FIXED: **0**
- QUERY KEY COLLISIONS: **0 found / 0 fixed**
- OLD RESPONSE RACE: **PROTECTED/PARTIAL** — React Query paths use parameterized keys and cancellation; legacy custom interval state paths remain for later page-specific audit
- HEALTH STATES: **PASS** in shared backend contract; legacy page adoption remains partial
- BACKWARD API COMPATIBILITY: **PASS** (additive health fields and preserved raw status)
- PYTHON COMPILE: **PASS**
- FRONTEND BUILD: **PASS** (`npm run build`)
- RUNTIME: **DEFERRED TO ACTUAL HOST**

## P0 issues remaining

- Generic device/detail/topology APIs and several frontend pages can still consume raw `Device.status`; they may not yet display derived STALE/DEGRADED states.

## P1 issues

- Adopt derived health in remaining current-health API responses during page-by-page verification.
- Consolidate refresh ownership per page only after browser/network evidence confirms exact duplicate requests.
- Add focused runtime/browser tests for late responses and stale status rendering.

## Files changed

- `hardik/backend/api/overview_routes.py`
- `HEALTH_REFRESH_FOUNDATION_REPORT.md`

## Safe to start page-by-page audit

**YES.** The shared backend health contract is now used by overview and monitoring-data responses, while untouched pages are clearly identified for controlled subsequent adoption.

