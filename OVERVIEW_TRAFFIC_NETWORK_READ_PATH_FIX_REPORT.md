# Overview Traffic + Network Information Read-Path Fix

Implemented only the proven Overview read-path corrections. No collectors, OIDs, scheduler, Redis/lease, ICMP, persistence writer, schema, migrations, database rows, topology builder, or unrelated APIs were changed.

## Files changed

- `hardik/backend/api/overview_routes.py`
- `hardik/tests/test_dashboard_current_traffic.py`
- `figma design/src/pages/Dashboard.tsx`

## Fixes

1. Overview now treats naive `LatestInterface.polled_at` and `InterfaceStatistic.created_at` values from the current SNMP writer as UTC, while normalizing aware values to UTC. The existing freshness rule remains `age <= interval_seconds * 3`; NULL rates remain NULL and valid zero remains zero.
2. Traffic-history timestamps are serialized as explicit UTC-aware ISO timestamps, so the existing frontend parser receives an unambiguous instant. Historical rows are not rewritten and the 5,000-row cap remains.
3. Overview network counts now read successful, real `DeviceCapabilities.capability_detail` snapshots for LLDP/CDP, VLAN, routing, ARP, and MAC. Unsupported/missing/failed capability data contributes zero entries, never fabricated positives. LLDP/CDP relationships are conservatively deduplicated by device, local port, remote identity, remote port, and management address; LLDP wins when the same key appears in both protocols.
4. The Dashboard renders unavailable network values as `N/A` rather than converting backend `null` to numeric zero.

Topology nodes remain `len(non-deleted managed devices)`. It was intentionally not changed because the existing label/contract is managed-device inventory and safe cross-device deduplication of topology capability nodes is not proven by the current payload contract.

## Validation

- Backend Python compile: PASS.
- Focused Overview checks: PASS (UTC-naive timestamp normalization and successful capability counting/deduplication).
- Frontend build (`npm run build`): PASS.
- Live production runtime/DB verification: NOT RUN from the Codex sandbox.

Host retest should call `GET /api/v1/overview?hours=12` after fresh scheduler polls and confirm `normalized.traffic`, `normalized.traffic_history`, and `normalized.network` against the persisted capability snapshots.

CURRENT TRAFFIC SOURCE FIX: PASS
TRAFFIC HISTORY SOURCE FIX: PASS
LLDP SOURCE FIX: PASS
VLAN SOURCE FIX: PASS
ROUTING SOURCE FIX: PASS
ARP SOURCE FIX: PASS
MAC SOURCE FIX: PASS
TOPOLOGY SOURCE: UNCHANGED + existing contract is managed-device inventory; safe capability-node deduplication not proven
FRONTEND NULL SEMANTICS: PASS
BACKEND TESTS: PASS (focused checks; full pytest unavailable in environment)
FRONTEND BUILD: PASS
RUNTIME VERIFIED: NO
