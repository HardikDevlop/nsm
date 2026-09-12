# SNMP + ICMP Industry Readiness Audit

Audit scope is limited to SNMP and ICMP. Syslog, flow, APM, virtualization,
backup, and other collectors are intentionally excluded.

## Executive summary

Runtime PostgreSQL and live-device verification was not available in this audit
environment. Therefore “real data” counts are **runtime verification pending**,
not zero, and no sample or static production data is treated as evidence.

The application has a substantial SNMP implementation and a reusable ICMP
monitor, but the end-to-end product is **PARTIAL**, principally because several
SNMP modules expose only latest data or have incomplete normalized persistence,
and because the frontend contains at least one legacy ICMP chart with a generic
empty state and the shared SNMP chart had unsafe ordering/null behavior.

Readiness percentages are checklist ratios, not runtime success claims:

| Area | Result | Denominator |
|---|---:|---|
| SNMP | 63% | 27 practical capability items verified in source; 17 implemented/usable, 10 partial or missing |
| ICMP | 78% | 18 practical capability items verified in source; 14 implemented/usable, 4 partial |
| UI data representation | 62% | 21 reviewed representation concerns; 13 pass, 8 partial/fail |
| Overall | 66% | Weighted average of the three areas above |

These figures are source-derived and should be recalculated after a live-device
run. They must not be read as packet/poll success rates.

## What the NMS currently collects

### SNMP

Implemented collectors and persistence paths exist for system identity,
inventory, health, CPU, memory, storage, environment, interfaces, VLAN,
ARP, MAC/FDB, LLDP, CDP, routing, topology, polling history, OID capability
cache, traps, and SNMP credentials. Normalized latest/history tables are
present for CPU, memory, storage, interfaces, environment, and polling
history. Interface history stores rates and counters.

Identity is collected through `system.py`/`inventory.py` and normalized through
the SNMP polling service. Credentials support v2c and v3 fields, including
username, security level, auth protocol/password, and privacy protocol/password;
the UI does not display secret values.

### ICMP

The realtime monitor provides native ICMP with subprocess fallback, bounded
shared executor, configured interval, lifecycle controls, RTT, reachability,
status transitions, persistence to `device_metrics`, status-history persistence,
and batched metric writes. Availability reports and outage records are also
implemented. The source does not establish durable TTL history in the primary
metric model.

## Runtime data status

No PostgreSQL connection, FastAPI process, or live monitored device was
available for this run. All metric rows, capabilities, poll outcomes, chart
samples, and alert transitions are therefore **RUNTIME VERIFICATION PENDING**.
The repository contains tests and runtime-verification reports, but those are
not current runtime evidence.

When runtime access is available, classify each empty result as one of:
device unsupported (capability false), collector failure (poll history error),
not scheduled (monitoring config/job absent), persistence failure (collector
success but latest/history row absent), API omission, or frontend omission.

## Complete data-flow matrix

| Metric/capability | Source/collector | DB latest/history | API | Frontend | Status |
|---|---|---|---|---|---|
| sysName/description/object ID/contact/location/uptime | SNMP system | device identity/inventory; poll history | SNMP device/detail routes | SNMP Devices, Device Details | Implemented; runtime pending |
| vendor/model/serial/firmware/hardware | inventory + identity resolver | `device_inventory`, identity tables | device/detail routes | Device Details/capabilities | Partial; field coverage varies by device |
| SNMP reachability/poll outcome/duration/error | polling service | `polling_history`, monitoring config | polling history/statistics | Polling Monitoring/status badges | Implemented; runtime pending |
| interface identity/status/speed/counters | interfaces collector | `latest_interface`, `interface_statistics` | interface/latest/history routes | Interfaces, Interface Details | Partial; alias/MAC/MTU/IP fields are not all typed in normalized latest model |
| interface rates/utilization/errors/discards | interfaces collector | `latest_interface`, `interface_statistics` | interface history | Interface charts/tables | Implemented with counter-derived rates; runtime pending |
| CPU/core/load | CPU collector | `latest_cpu`, `cpu_statistics` | monitoring data/latest CPU | CPU Monitoring chart/cards | Implemented; unsupported handling exists, runtime pending |
| memory | memory collector | `latest_memory`, `memory_statistics` | monitoring data/latest memory | Memory Monitoring | Implemented; runtime pending |
| storage | storage collector | `latest_storage`, `storage_statistics` | monitoring data/storage | Storage Monitoring | Implemented; runtime pending |
| environment/power | environment collector | `latest_environment`, environment history | monitoring data/environment | Environment Monitoring | Partial; voltage/fan/PSU breadth is vendor/device dependent |
| VLAN membership/tagging | VLAN collector | VLAN normalized records | SNMP module routes | VLAN Monitoring | Partial; current monitoring-data endpoint previously had no DB-backed payload |
| ARP | ARP collector | collector/topology persistence | SNMP topology/module routes | ARP/topology views | Partial; verify dedicated latest/history API at runtime |
| MAC/FDB | MAC table collector | topology/FDB persistence | topology/module routes | topology/MAC views | Partial; adjacency safety depends on evidence type |
| LLDP/CDP | LLDP/CDP collectors | `lldp_neighbors`/topology persistence | topology/module routes | LLDP/Topology | Implemented source path; runtime pending |
| routing | routing collector | `routing_table` | routing route | Routing Monitoring | Partial; metric/interface/protocol field completeness needs runtime confirmation |
| SNMP topology | topology collector using LLDP/CDP/FDB/ARP/interfaces | topology persistence/cache | topology routes | SNMP/Network/Manual Topology | Partial; only explicit physical evidence should form adjacency |
| ICMP reachability/RTT | native/fallback probe | `device_metrics` | monitoring/device metrics routes | Device Monitoring/live history | Implemented; runtime pending |
| ICMP loss | timeout samples/status aggregation | `device_metrics.packet_loss` and availability | overview/monitoring routes | Device Monitoring chart | Partial; verify multi-sample window semantics |
| ICMP TTL | probe implementation | no durable primary TTL field found | no confirmed history API | no confirmed dedicated chart | Missing/partial |
| ICMP availability/outages | realtime monitor + availability service | status history, availability reports/outages | availability routes | Device Monitoring/availability | Implemented; runtime pending |
| ICMP alerts/recovery | monitor transition + alert services | alerts/incidents | alert routes | alert UI | Partial; runtime transition/no-duplicate proof pending |

## SNMP capability matrix

| Category | Status | Notes |
|---|---|---|
| Identity | PARTIAL | Core system identity and inventory paths exist; serial/firmware/hardware are conditional/vendor dependent |
| Availability/health | IMPLEMENTED | Poll status, duration, errors, scheduler and health models exist |
| Interfaces | PARTIAL | Main counters/rates/status are present; alias, MAC, MTU, IP, uptime/state duration are not uniformly normalized |
| CPU | IMPLEMENTED | Per-core support and unsupported capability path exist |
| Memory | IMPLEMENTED | Typed latest/history fields exist |
| Storage | IMPLEMENTED | Volume/type/latest/history models exist |
| Environment | PARTIAL | Temperature/power are typed; voltage/fan/PSU breadth is not uniformly typed |
| VLAN | PARTIAL | Collector supports Q-BRIDGE membership/name parsing; API/UI data path needs DB-backed verification |
| ARP | PARTIAL | Collector exists; dedicated end-to-end latest/history evidence needs runtime check |
| MAC/FDB | PARTIAL | Collector exists; bridge/VLAN/last-observed completeness needs verification |
| Routing | PARTIAL | Collector/model exist, but normalized field coverage is narrower than the checklist |
| LLDP/CDP | IMPLEMENTED source path | Neighbor collector/topology paths exist; runtime pending |
| Topology | PARTIAL | Evidence-aware topology code exists; must verify no MAC-only false adjacency in runtime output |
| Polling history | IMPLEMENTED | Typed status/collector/duration/error model and UI route exist |
| Credentials | IMPLEMENTED | v2c/v3 fields and encrypted secret handling exist; secret exposure audit still required in deployed logs |

## ICMP capability matrix

| Capability | Status | Notes |
|---|---|---|
| Reachability, timeout, error, last seen | IMPLEMENTED | Realtime monitor and device metric routes |
| Current RTT | IMPLEMENTED | Real probe RTT, nullable on timeout |
| Historical RTT | IMPLEMENTED | `device_metrics` and Device Monitoring history |
| Min/max/average | PARTIAL | Aggregation exists in selected reports/windows; single-sample meaning must remain explicit |
| Current/historical loss | IMPLEMENTED | Nullable loss and window aggregation paths exist |
| TTL | PARTIAL | Probe-level support is not represented as a durable typed metric/history path |
| UP/DOWN transitions/outages | IMPLEMENTED | Stable transition handling, status history and availability services exist |
| Availability percentage/downtime | IMPLEMENTED | Availability reports calculate coverage and downtime |
| Alert/recovery/no-duplicate semantics | PARTIAL | Source paths exist; requires runtime transition test against deployed alert store |
| Lifecycle/interval/concurrency/batching/cache | IMPLEMENTED | Shared bounded executor and batch persistence present |

## SNMP/ICMP overlap authority

| Metric | Primary | Secondary | UI label |
|---|---|---|---|
| Basic device reachability | ICMP | SNMP poll reachability | ICMP Reachability |
| SNMP service availability | SNMP | none | SNMP Poll Status |
| Interface state/counters | SNMP | none | SNMP Interface |
| CPU/memory/storage/environment | SNMP | none | SNMP |
| RTT/packet loss | ICMP | none | ICMP RTT / ICMP Loss |
| Overall device status | ICMP for liveness, correlated with SNMP state | both | Device status with source badges |

## Frontend page and chart audit

| Page | Data/cards/tables/graphs | Result |
|---|---|---|
| SNMP Devices / SNMP Monitoring | device list, module cards, capabilities, polling/trap summaries | PARTIAL: real API paths exist; runtime and freshness proof pending |
| Device Details / Device Monitoring | status, availability, latency/loss chart, live ping list, status history | PARTIAL: useful real-backed paths; chart uses dual axes and generic empty state |
| CPU/Memory/Storage/Environment | latest cards, unsupported shells, history charts/tables | PARTIAL: unsupported shells exist; field-key consistency and runtime states need tests |
| Interfaces / Interface Details | status/rates/utilization/error charts and tables | PARTIAL: charts are present; shared chart previously plotted unsorted/null data |
| VLAN/LLDP/Routing | dynamic tables | PARTIAL: UI is wired to module API, but the generic monitoring-data endpoint had sample fallback and no DB payload for several modules |
| Network Topology | graph from SNMP evidence | PARTIAL: evidence-aware source exists; runtime graph audit pending |
| Manual Topology | imported/live SNMP evidence | PARTIAL: source and evidence files exist; runtime verification pending |

The shared `SNMPMetricChart` was fixed in this audit to sort timestamps and
filter non-finite values. This avoids converting missing values to zero and
keeps the time axis truthful. No new chart library or backend metric semantics
were introduced.

## Critical finding: removed sample-data production fallback

`hardik/backend/api/monitoring_data_routes.py` was reading
`/tmp/snmp_sample_data.json` and returning its contents for interfaces, VLAN,
LLDP, routing, ARP, MAC, inventory, and topology. That violated the no-mock
requirement and could make the UI appear populated without collector/database
evidence. The fallback was removed. Those modules now return only data backed
by the actual normalized DB paths; modules without a DB-backed payload remain
empty/unsupported until their real persistence/API path is wired.

## Data quality findings

- Typed nullable metric fields generally allow `NULL` for unsupported values.
- Legacy `Interface` defaults (`traffic_in`, `traffic_out`, errors) can still
  look like zero and should not be used as SNMP support evidence.
- Counter reset/wrap handling must be verified in `interfaces.py` and with a
  two-poll integration test; rates must never be negative or exceed physical
  capacity without an explicit explanation.
- History queries are ordered and bounded in the reviewed SNMP monitoring
  endpoint, but every chart endpoint should enforce an explicit range/limit.
- Timestamps are mixed between UTC and Asia/Kolkata-naive model helpers. The
  deployed DB/API contract should be standardized and documented before SLA
  comparisons.
- Freshness is exposed in several poll payloads, but it is not consistently
  surfaced on every summary card.

## Industry gap matrix

| Gap | Priority | Recommended action |
|---|---|---|
| Sample/static data could enter production API | P0 | Fixed in this audit; add regression test forbidding sample-file reads |
| Unsupported CPU/memory/environment must never render as zero | P0 | Audit all module cards and add nullable/unsupported component tests |
| Runtime SNMP/ICMP transition and persistence proof absent | P0 | Run against PostgreSQL and one reachable/unreachable device; capture poll/alert evidence |
| ICMP TTL not durably modeled | P1 | Add nullable TTL/latest/history only if the probe reliably returns it |
| Interface identity lacks complete alias/MAC/MTU/IP/uptime normalization | P1 | Extend typed normalized model/API where collector data exists |
| VLAN/ARP/MAC/routing module API data paths are incomplete in generic endpoint | P1 | Connect persisted normalized tables to module routes; do not use fallback data |
| Availability and alert recovery need deployed integration proof | P1 | Test UP→DOWN→UP, duplicate suppression, recovery, and outage duration |
| Chart states/freshness are inconsistent | P1 | Standardize loading, unsupported, offline, API error, no samples, and stale states |
| Retention is configured as zero/no cleanup | P1 | Define retention policy and bounded aggregation/downsampling before production |

## Final verdict

| Area | Verdict |
|---|---|
| SNMP | PARTIAL |
| ICMP | PARTIAL |
| Graph representation | PARTIAL |
| Data correctness | PARTIAL (sample fallback fixed; runtime pending) |
| Industry readiness | PARTIAL |

### Ordered next work

1. Run the DB/API/live-device verification and record actual counts/statuses.
2. Add regression tests for no sample-file reads and unsupported-vs-zero UI.
3. Complete normalized/API paths for VLAN, ARP, MAC/FDB, routing, and interface identity fields.
4. Add ICMP TTL persistence only if supported by the actual probe.
5. Execute alert transition/recovery and counter-reset integration tests.

## Console summary

- SNMP industry audit: **PARTIAL**
- ICMP industry audit: **PARTIAL**
- SNMP metrics implemented: **17 source-verified capability groups**
- SNMP metrics with real data: **runtime verification pending**
- SNMP unsupported by current device: **runtime verification pending**
- SNMP missing/partial application capability groups: **10**
- ICMP metrics implemented: **14 source-verified capability groups**
- ICMP metrics with real data: **runtime verification pending**
- ICMP missing/partial capability groups: **4**
- Charts audited: **10 shared/module/detail chart usages plus the Device Monitoring chart family**
- Charts fixed: **1 shared chart component**
- Broken data flows: **1 confirmed (sample-file fallback); several module DB/API paths partial**
- P0 issues remaining: **2 runtime/data-correctness verification items**
- P1 issues: **7**
- Backend semantics changed: **NO** (fallback removal corrects data source; collector semantics preserved)
- Mock data added: **NO**
- Final report: `SNMP_ICMP_INDUSTRY_READINESS_AUDIT.md`

## Live runtime verification override

The live verification attempt on 2026-09-12 was **RUNTIME BLOCKED**:

- PostgreSQL: `localhost:5432` returned no response (`pg_isready`).
- FastAPI: no response on ports 8000/8001.
- Frontend: no response on ports 3000/5173.
- No running scheduler, ICMP monitor, or service process was observed.
- Consequently, no device, credential, poll cycle, sample, API response, alert
  transition, or current frontend payload can be classified as real runtime
  evidence.

All source-level matrix statuses in this report are superseded for this run by
**RUNTIME BLOCKED**. They are not evidence of unsupported devices, collector
failure, or database persistence failure. The correct distinction cannot be
made until PostgreSQL, FastAPI, the schedulers, and at least one monitored
device are available.

### Recovery attempt result

The existing PostgreSQL `14/main` cluster was found in `down` state. Starting
it was attempted with the existing service/cluster commands, but this session
lacks privileged interactive access (`sudo` requires a password and systemd is
restricted). No data, schema, migrations, application code, or optimized
SNMP/ICMP internals were changed.
