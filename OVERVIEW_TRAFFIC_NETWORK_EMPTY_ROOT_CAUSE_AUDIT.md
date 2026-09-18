# Overview Traffic and Network Empty-State Root-Cause Audit

Read-only source audit. No application code, database row, frontend behavior, collector, scheduler, cache, or device configuration was changed.

## Scope and contract

`GET /api/v1/overview` is the sole Dashboard data request. `Dashboard.tsx` reads `response.normalized` and maps:

- `normalized.traffic.rx_mbps` / `tx_mbps` to Live Traffic and Network Traffic.
- `normalized.traffic.top_devices` / `top_interfaces` to rankings (the current page visibly renders top devices; `top_interfaces` is still returned by the API).
- `normalized.traffic_history` to the minute-bucketed Traffic Trend.
- `normalized.network.*` to Network Information.

The endpoint is PostgreSQL/read-only from the Dashboard perspective and is cached by Redis plus a 10-second in-process cache. No live SNMP request is made by the endpoint.

## A. Traffic current path

The source path is:

`SNMP interfaces collector` -> `SNMPPoller._persist_results()` -> `_persist_interfaces()` -> `latest_interface` (`LatestInterface`) and `interface_statistics` (`InterfaceStatistic`) -> `overview_routes.get_overview()` -> `_select_current_interfaces()` -> `_aggregate_current_traffic()` -> `normalized.traffic` -> `Dashboard.tsx`.

`LatestInterface` supplies `rx_mbps`, `tx_mbps`, `utilization_percent`, counters, status, and `polled_at`. Rates are calculated during persistence from raw cumulative octets and elapsed time; Overview does not recalculate rates.

Selection is deterministic by `(device_id, interface_id)` after sorting `polled_at DESC, id DESC`. The current reader does not filter to operationally-up interfaces. A row is fresh when its normalized timestamp exists, an enabled `interfaces` MonitoringConfig interval exists, and `age <= interval_seconds * 3`. Stale or missing rows remain in the returned interface list but are excluded from current traffic aggregation.

`_aggregate_current_traffic()` sums non-NULL RX and TX values independently across fresh rows. A direction is `null` when no fresh row has a non-NULL value. A valid zero is distinguishable from NULL and is included in the sum.

The SNMP writer calls `now_utc()` and stores it in legacy SQLAlchemy `DateTime` columns. The Overview helper `_overview_timestamp()` interprets a naive database timestamp as `Asia/Kolkata`, not UTC. Therefore a naive value that semantically represents UTC is shifted by 5:30 hours during freshness checks. This is a proven source-level timezone risk for current traffic, but live row values and ages were not available in this environment to prove which exact rows caused the screenshot.

Current RX/TX can legitimately be NULL even with 36 interface identities when all latest rows are stale, all calculated rates are NULL (first sample, counter decrease/reset, invalid elapsed, or capacity rejection), or rows are absent. The source does not convert missing rates to zero.

## B. Traffic history path

`normalized.traffic_history` is read directly from `interface_statistics`, using `created_at >= datetime.utcnow() - timedelta(hours=hours)`, ordered newest-first and capped at 5,000 rows before reversing. It returns persisted `rx_mbps`, `tx_mbps`, and `utilization_percent`; it does not require a non-NULL rate in SQL.

`InterfaceStatistic` is written by `_persist_interfaces()` for every valid interface sample, including rows whose calculated RX/TX rates are NULL. Thus the phrase “No interface history stored for the selected period” is produced by the frontend when its chart builder finds no sample with either usable RX or usable TX after timestamp parsing; it does not prove that the database has zero rows. The source permits at least three causes: zero rows in the requested window, rows with both rates NULL, or a UTC/IST mismatch in the query boundary and/or frontend `parseISTDate()` handling. Runtime DB evidence is required to distinguish them.

The frontend intentionally skips samples where both rates are NULL and initializes missing direction values to zero only inside a bucket that has some usable direction. That is presentation aggregation, not persisted-data fabrication.

## C. Top devices and top interfaces

Both are derived from the same current `interface_rows` selected from `LatestInterface` and classified by the same freshness rule. `top_devices` includes only fresh rows and accumulates non-NULL directions. `top_interfaces` sorts the selected rows by `(rx_mbps or 0) + (tx_mbps or 0)` and returns the first eight.

Consequently, if there are no fresh usable current rates, the top-device accumulator is empty and the frontend shows “No stored data available.” A valid fresh rate for device 283 would make it eligible. If only one direction is NULL, the top-device summation retains the available direction, but the current `top_devices` sort expression adds the two stored values directly and can be unsafe when one side remains NULL; this is an aggregation robustness issue, not proven from the unavailable runtime snapshot.

## D. Network Information paths

| Dashboard field | API field | Overview DB source | Scheduler persistence source | Source match |
|---|---|---|---|---|
| LLDP/CDP | `network.lldp_neighbors` | `COUNT(lldp_neighbors.id)` | `DeviceCapabilities.capability_detail['lldp']` / collector payload; no `_persist_results()` domain-table branch for LLDP | No |
| VLAN | `network.vlan_count` | `COUNT(vlan_information.id)` | `DeviceCapabilities.capability_detail['vlan']` / collector payload; no VLAN domain-table persistence branch | No |
| Routes | `network.routing_entries` | `COUNT(routing_table.id)` | `DeviceCapabilities.capability_detail['routing']` / collector payload; no routing domain-table persistence branch | No |
| ARP | `network.arp_entries` | hard-coded `None` | `DeviceCapabilities.capability_detail['arp']` / collector payload; no ARP Overview table query | No usable Overview source |
| MAC | `network.mac_entries` | hard-coded `None` | `DeviceCapabilities.capability_detail['mac_table']` / collector payload; no MAC Overview table query | No usable Overview source |
| Topology nodes | `network.topology_nodes` | `len(device_rows)` | topology capability/detail can contain topology nodes, but Overview does not read it | Not a topology-row count |

The three SQL counts are global counts: they have no device filter, freshness filter, latest-snapshot selection, or status predicate. ARP and MAC are explicitly returned as null by the backend, then `Dashboard.tsx` renders any null network metric as numeric `0` (`metric == null ? 0 : metric`). That makes those two screenshot zeros an expected frontend fallback for missing API fields, not evidence of zero persisted ARP/MAC rows.

Topology showing 11 is explained directly by `len(device_rows)` for non-deleted devices. It is not evidence that topology collector nodes were persisted or counted.

## E. Collector success versus domain data

`SNMPPoller._persist_results()` always calls `_persist_history()` and records `SUCCESS` when the collector is marked supported, regardless of whether the returned payload is empty. In this scheduler persistence path, only CPU, memory, storage, interfaces, and environment have dedicated persistence branches. VLAN, LLDP, routing, ARP, MAC, and topology are retained in `DeviceCapabilities.capability_detail` by the capability update, but are not inserted into the `vlan_information`, `lldp_neighbors`, or `routing_table` tables used by Overview; ARP/MAC are not queried by Overview at all.

Therefore PollingHistory `success` proves the scheduled collector operation was classified successful, not that non-empty rows exist in every legacy normalized domain table.

## F. Timestamp and freshness audit

Affected table timestamp semantics:

- `latest_interface.polled_at`: written with application `now_utc()`; SQLAlchemy model column is legacy naive `DateTime`.
- `interface_statistics.created_at`: written with the same aware UTC `now_utc()` value; model column is legacy naive `DateTime`.
- `vlan_information`, `lldp_neighbors`, and `routing_table.created_at`: model default `SNMPBase.now()` creates naive Asia/Kolkata values, but the scheduler path currently does not insert these rows.
- Overview current-interface reader: `_overview_timestamp()` treats naive values as Asia/Kolkata and aware values as UTC.
- Overview history boundary: `datetime.utcnow()` is naive UTC and is compared directly to a legacy DateTime column.
- Dashboard history parser: calls `parseISTDate()` on API timestamps.

This is not a globally uniform timestamp contract. It is a source-level timezone filter risk for both current traffic and history. No live query was run, so the report does not claim the exact screenshot was caused by the time filter rather than NULL rates or absent rows.

## G. Read-only host verification

The Codex environment has no verified access to the production PostgreSQL/runtime, so the following is the single read-only host-side command to distinguish the remaining runtime alternatives. Run it from the project environment with the normal database settings:

```bash
cd /home/agnigate/Desktop/NMS/hardik && python - <<'PY'
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from backend.database.session import SessionLocal
from backend.models import Device, Interface
from backend.models.snmp import (
    LatestInterface, InterfaceStatistic, VLANInformation, LLDPNeighbor,
    RoutingEntry, DeviceCapabilities,
)

db = SessionLocal()
try:
    d = db.query(Device).filter(Device.id == 283).one()
    print('DEVICE', d.id, d.ip_address)
    print('interface identities', db.query(func.count(Interface.id)).filter(Interface.device_id == 283).scalar())
    latest = db.query(LatestInterface).filter(LatestInterface.device_id == 283).order_by(LatestInterface.polled_at.desc(), LatestInterface.id.desc()).all()
    print('latest_interface rows', len(latest))
    for r in latest:
        print('latest', r.id, r.interface_id, r.name, r.polled_at, r.rx_mbps, r.tx_mbps)
    now = datetime.now(timezone.utc)
    usable = [r for r in latest if r.rx_mbps is not None or r.tx_mbps is not None]
    print('usable latest rates', len(usable))
    print('fresh-by-source-UTC-3x-interval cannot be proven without config join; latest timestamps above are required evidence')
    since = datetime.utcnow() - timedelta(hours=12)
    hist = db.query(InterfaceStatistic).filter(InterfaceStatistic.created_at >= since).all()
    print('history rows last12h', len(hist), 'usable', sum(r.rx_mbps is not None or r.tx_mbps is not None for r in hist), 'newest', max((r.created_at for r in hist), default=None))
    for label, model in [('vlan', VLANInformation), ('lldp', LLDPNeighbor), ('routing', RoutingEntry)]:
        print(label, 'device283 rows', db.query(func.count(model.id)).filter(model.device_id == 283).scalar(), 'global rows', db.query(func.count(model.id)).scalar())
    cap = db.query(DeviceCapabilities).filter(DeviceCapabilities.device_id == 283).one_or_none()
    print('capability modules', sorted((cap.capability_detail or {}).keys()) if cap else None)
    for name in ('lldp','vlan','routing','arp','mac_table','topology'):
        item = (cap.capability_detail or {}).get(name, {}) if cap else {}
        data = item.get('data') if isinstance(item, dict) else {}
        print('capability', name, 'status=', item.get('collection_status') if isinstance(item, dict) else None, 'data_counts=', {k: len(v) if isinstance(v, list) else None for k,v in (data or {}).items()} if isinstance(data, dict) else None)
finally:
    db.close()
PY
```

## Classification of screenshot symptoms

| Field | Source-level classification | Evidence status |
|---|---|---|
| Live RX | Freshness filter / NULL rate data / timezone risk | Runtime evidence required for primary cause |
| Live TX | Freshness filter / NULL rate data / timezone risk | Runtime evidence required for primary cause |
| Top Devices | Same current fresh-rate dependency | Empty is explained if no fresh usable rows; runtime required |
| Top Interfaces | Same `LatestInterface` dependency | Runtime evidence required |
| Traffic Trend | NULL history rows, window/timezone filter, or zero rows | Runtime evidence required |
| LLDP/CDP | Source table mismatch | Proven source mismatch |
| VLAN | Source table mismatch | Proven source mismatch |
| Routes | Source table mismatch | Proven source mismatch |
| ARP | Backend field intentionally null plus frontend null-to-zero fallback | Proven |
| MAC | Backend field intentionally null plus frontend null-to-zero fallback | Proven |
| Topology Nodes | Expected device-count implementation, not topology row count | Proven |

LIVE RX SOURCE: `normalized.traffic.rx_mbps` from fresh non-NULL `LatestInterface.rx_mbps` rows
LIVE TX SOURCE: `normalized.traffic.tx_mbps` from fresh non-NULL `LatestInterface.tx_mbps` rows
CURRENT TRAFFIC TABLE: `latest_interface` (`LatestInterface`)
CURRENT TRAFFIC TIMESTAMP: `LatestInterface.polled_at`
CURRENT TRAFFIC FRESHNESS RULE: `age <= enabled interfaces interval_seconds * 3`, with naive timestamps interpreted as Asia/Kolkata
CURRENT TRAFFIC NULL REASON PROVEN: NO
CURRENT TRAFFIC ROOT CAUSE: Fresh usable runtime rows versus NULL rates versus timezone filtering remains runtime-unproven; timezone semantics are a proven risk

TRAFFIC HISTORY TABLE: `interface_statistics` (`InterfaceStatistic`)
TRAFFIC HISTORY WRITER: `SNMPPoller._persist_interfaces()`
TRAFFIC HISTORY 12H QUERY: `created_at >= datetime.utcnow() - timedelta(hours=hours)`, newest-first, max 5000, then reversed
TRAFFIC HISTORY ROOT CAUSE: Runtime-unproven between zero rows, both-rate-NULL rows, and timezone/window filtering

TOP DEVICES SOURCE: fresh `LatestInterface` rows aggregated by device
TOP INTERFACES SOURCE: selected `LatestInterface` rows sorted by RX+TX with NULL treated as zero for ranking
TOP DEVICES EMPTY BECAUSE: no fresh row with a non-NULL rate, or runtime data/query issue; exact runtime cause unproven
TOP INTERFACES EMPTY BECAUSE: frontend only visibly exposes top devices; API returns the same current-interface dependency

LLDP OVERVIEW TABLE: `lldp_neighbors`
LLDP COLLECTOR TABLE: `DeviceCapabilities.capability_detail['lldp']` in the scheduler path
LLDP TABLE MATCH: NO
LLDP ZERO ROOT CAUSE: Overview counts a legacy normalized table not populated by the scheduler persistence branch

VLAN OVERVIEW TABLE: `vlan_information`
VLAN COLLECTOR TABLE: `DeviceCapabilities.capability_detail['vlan']` in the scheduler path
VLAN TABLE MATCH: NO
VLAN ZERO ROOT CAUSE: Overview counts a legacy normalized table not populated by the scheduler persistence branch

ROUTING OVERVIEW TABLE: `routing_table`
ROUTING COLLECTOR TABLE: `DeviceCapabilities.capability_detail['routing']` in the scheduler path
ROUTING TABLE MATCH: NO
ROUTING ZERO ROOT CAUSE: Overview counts a legacy normalized table not populated by the scheduler persistence branch

ARP OVERVIEW TABLE: none; API returns `None`
ARP COLLECTOR TABLE: `DeviceCapabilities.capability_detail['arp']`
ARP TABLE MATCH: NO
ARP ZERO ROOT CAUSE: Backend does not expose a persisted ARP count; frontend converts null to 0

MAC OVERVIEW TABLE: none; API returns `None`
MAC COLLECTOR TABLE: `DeviceCapabilities.capability_detail['mac_table']`
MAC TABLE MATCH: NO
MAC ZERO ROOT CAUSE: Backend does not expose a persisted MAC count; frontend converts null to 0

TOPOLOGY NODE SOURCE: `len(device_rows)` in Overview
TOPOLOGY NODE COUNT EXPLAINED: YES

POLLING SUCCESS GUARANTEES DOMAIN ROWS: NO

TIMEZONE ISSUE PROVEN: YES (source-level semantic mismatch/risk; exact screenshot causality needs runtime rows)
FRESHNESS ISSUE PROVEN: NO (rule exists; affected-row age is unavailable)
SOURCE TABLE MISMATCH PROVEN: YES
FRONTEND CONTRACT ISSUE PROVEN: YES for null ARP/MAC presentation as 0; no traffic API-key mismatch found

LIVE DB EVIDENCE AVAILABLE: NO
HOST READ-ONLY VERIFICATION REQUIRED: YES
HOST VERIFICATION SCRIPT PROVIDED: YES

CODE CHANGED: NO
DATABASE CHANGED: NO
FRONTEND CHANGED: NO
SNMP CHANGED: NO
SCHEDULER CHANGED: NO
REDIS CHANGED: NO
ICMP CHANGED: NO

SAFE FOR SURGICAL FIX AFTER RUNTIME EVIDENCE: YES
