# NMS Technology Stack and Module Architecture Audit

Audit date: 2026-09-10  
Scope: current production/runtime repository under `hardik/backend` and `figma design/src`  
Method: static repository inspection. No package, database, migration, or runtime technology changes were made.

## 1. Executive summary

The application is a Python/FastAPI network-management backend with a React/TypeScript SPA and PostgreSQL persistence. SNMP, discovery, ICMP, flow, Syslog, Linux monitoring and most domain workflows are implemented in Python. The frontend uses React Query for server state, a custom authenticated fetch/cache layer, Recharts for charts, and custom SVG for topology. No Go, Rust or Java production service was found.

The architecture is suitable for small-to-medium installations, but the current SNMP polling, ICMP subprocess model, per-message Syslog commits, synchronous SQLAlchemy access, and single-process UDP receivers are the principal scaling constraints. The first optimization target should be SNMP polling and persistence; a language migration is not the first corrective action.

## 2. Project-wide technology stack

### Frontend

| Area | Actual implementation |
|---|---|
| Framework | React 19, React DOM 19 |
| Language | TypeScript/TSX; small JavaScript/MJS test and utility surface |
| Build | Vite 8 with `@vitejs/plugin-react` |
| Routing | React Router 8, route-level lazy loading and permission wrappers |
| Local state | React hooks/context; no application Redux store is declared in the app manifest |
| Server state | TanStack React Query 5 plus custom `requestJson` GET cache/deduplication |
| Charts | Recharts 3 (and its D3 transitive dependencies) |
| Topology | Custom React + SVG graph/layout; no Cytoscape/D3 graph library |
| CSS/UI | Tailwind CSS 4, custom CSS/glass components, SweetAlert2 |
| Realtime | Authenticated fetch-based SSE for monitoring and topology; no frontend WebSocket client found |
| Tests | Node built-in test runner over `.test.mjs`; source-pattern regression tests dominate |
| Export | SheetJS `xlsx`; CSV generation also exists on backend |
| Other | Custom i18n context, custom query provider, route chunk retry helper |

Primary evidence: `figma design/package.json`, `src/routes.tsx`, `src/lib/api.ts`, `src/pages/Topology.tsx`, `src/features/snmp/hooks/useSnmpQueries.ts`.

### Backend

| Area | Actual implementation |
|---|---|
| Language | Python 3; project metadata does not pin one exact minor version |
| Framework | FastAPI |
| ASGI server | Uvicorn |
| ORM | SQLAlchemy 2 synchronous ORM/session API |
| DB driver | psycopg 3 (`psycopg[binary]`) |
| Validation/config | Pydantic 2 and pydantic-settings |
| Authentication | Bearer JWT using python-jose; password hashing with Passlib/bcrypt |
| Authorization | Database roles/permissions and route dependencies such as `require_permission` |
| Scheduler | APScheduler `AsyncIOScheduler`; one job per device/module |
| Background execution | asyncio tasks, `asyncio.to_thread`, thread pools, application lifespan services |
| Realtime | SSE `StreamingResponse`; no backend WebSocket endpoint found |
| Serialization | FastAPI/Pydantic and Python JSON; raw SQL mapping for analytics |
| Logging | Python `logging`, centralized `logging_config`, request/DB timing instrumentation |
| Tests | pytest, Hypothesis, Node frontend regression suite |

### Database

- Primary database: PostgreSQL, configured through `postgresql+psycopg`.
- Connection pool: 20 persistent connections, 20 overflow, 10-second checkout timeout, pre-ping and 1,800-second recycle.
- Migration mechanism: custom idempotent migration registry/runner in `backend/database/migrations.py`; Alembic was not found.
- Time series: ordinary PostgreSQL historical and latest-value tables; TimescaleDB or another time-series extension was not found.
- Main domains: identity/inventory, SNMP samples/latest values, alerts/events, flows, Syslog, Linux metrics, topology, ITSM, CMDB, APM, configuration, availability, BGP, QoS and virtualization.

### Cache, queue and coordination

- Redis client exists and is used for short-lived cache and the scheduler HA lease.
- Scheduler leadership uses a Redis lease; it is not a general distributed job queue.
- No Celery, RQ, Kafka, RabbitMQ or durable message broker was found.
- Flow and Syslog ingestion use bounded in-process `asyncio.Queue` instances.
- Frontend has a 30-second GET cache in memory/sessionStorage plus React Query caching.
- SSE is direct application streaming, not Redis pub/sub.

## 3. Exact language usage

| Language | Verified runtime use |
|---|---|
| Python | FastAPI routes, SQLAlchemy models, SNMP, discovery, scheduling, ICMP, Syslog, flow parsing/ingestion, Linux monitoring, analytics and ITSM services |
| TypeScript/TSX | React UI, routing, API client, hooks, topology SVG/layout and module pages |
| JavaScript/MJS | Node regression tests and limited scripts; main UI remains TypeScript |
| SQL | Custom migrations, reporting/aggregation queries, flow/APM analytics and cleanup paths |
| Bash | Local start/stop/deployment scripts |
| PowerShell | Backend smoke/test helper |
| CSS/HTML | SPA styling and Vite shell |
| JSON/YAML | configuration, Postman collection and data/docs artifacts |
| Go | NOT FOUND in production/runtime code |
| Rust | NOT FOUND |
| Java/Kotlin | NOT FOUND |

## 4. Networking and monitoring implementation

| Capability | Actual implementation |
|---|---|
| ICMP | OS `ping` via `subprocess.run`; thread pools provide host concurrency |
| SNMP v2c | pysnmp 6 asyncio HLAPI behind a synchronous facade |
| SNMP v3 | pysnmp `UsmUserData`, configurable auth/privacy/security level |
| SNMP GET | asyncio `getCmd` executed in a dedicated thread/event loop |
| SNMP WALK/BULK | `bulkCmd`, fallback to `nextCmd`, bounded row count |
| Discovery | Python modules for IP enumeration, ICMP, TCP, DNS, ARP, HTTP, SNMP, SSH and WMI |
| Interfaces | IF-MIB collectors and historical/latest SQL tables |
| ARP | SNMP collector plus OS ARP discovery path |
| MAC/FDB | BRIDGE-MIB/Q-BRIDGE-MIB collector, port grouping and vendor/OUI correlation |
| VLAN | SNMP VLAN collector and persisted VLAN information |
| LLDP | LLDP-MIB collector; confirmed topology evidence |
| CDP | Cisco CDP collector/fallback; confirmed topology evidence when collected |
| Routing | SNMP route collector; routes retained as L3 data, not treated as physical topology proof |
| Automatic topology | LLDP/CDP confirmed links plus MAC/ARP inferred links; cached snapshots in device capabilities |
| Manual topology | Custom React workspace, snapshots/change history, reconciliation and Port Map |
| Syslog | asyncio UDP and TCP receiver, RFC5424 plus legacy/RFC3164-style parsing, DB correlation rules |
| sFlow | Python asyncio UDP receiver and sFlow v5 parser including generic interface counters |
| IPFIX | Python asyncio UDP receiver with template/options-template cache and normalized flow records |
| NetFlow | No active NetFlow v5/v9 receiver was verified; IPFIX v10 and sFlow are active implementations |
| Linux | SSH/Paramiko and SNMP detection/collection, scheduler, current/history metrics and security events |
| HTTP/APM | HTTP discovery plus database-ingested APM applications/services/transactions/metrics/dependencies |
| BGP | Persisted BGP observation API; no standalone BGP protocol speaker/session daemon found |
| QoS | Persisted QoS sample API/UI; no packet scheduler/controller found |
| Virtualization | Provider-independent inventory/topology persistence contract; concrete hypervisor collectors were not found |

## 5. Module inventory and real data flow

The table names the primary files rather than every supporting schema/test.

| Module | Purpose and real flow | Frontend | Backend/services | Tables/protocols |
|---|---|---|---|---|
| Authentication | Credentials → JWT → bearer dependency → protected route | `Login.tsx`, auth context, `api.ts` | `auth/security.py`, `api/routes.py` | `users`, bcrypt/JWT/HTTP |
| Users/RBAC | User → role → permission codes → `withPermission` and backend dependency | User/Role pages, `ProtectedLayout` | routes, seed | `users`, `roles`, `permissions`, association table |
| Organizations/Sites | CRUD and device grouping | Organizations/Sites pages | core routes | `organizations`, `sites` |
| Vendors/Device Types | Classification/reference data | Vendors/DeviceTypes | core routes, identity resolver | `vendors`, `device_types`, `vendor_ouis`, `device_products` |
| Devices/Credentials | Inventory CRUD → credentials → collectors | ISP/SNMP device pages | core and SNMP routes | `devices`, credential tables |
| Discovery/IP scan | CIDR → chunking → parallel ping → protocol probes → candidate persistence | `ISPMonitoring.tsx` | discovery routes, chunked/discovery services and modules | ICMP/TCP/DNS/ARP/HTTP/SNMP/SSH/WMI |
| SNMP identity/capability | Credential → identity GET/walk → vendor detector → OID registry → resolver/capability DB | SNMP detail/capability pages | `snmp/collector.py`, identity package | identity/capability/OUI/product tables |
| SNMP polling | Monitoring config → APScheduler → semaphore/thread worker → domain collector → current/history DB → alerts | SNMP monitoring pages/hooks | `services/snmp_polling.py` | monitoring/polling/latest/history tables, SNMP |
| CPU/Memory/Storage/Environment | Minimal domain walk → normalize → latest/history → API/chart | SNMP module pages | respective collectors and routes | statistics/latest tables, SNMP |
| Interfaces | IF-MIB walk → normalized interfaces → latest/history → alerts/UI | interface pages | interface collector, polling service | interfaces/device_interfaces/latest/history |
| Inventory | ENTITY-MIB/system identity → normalized hardware inventory | SNMP inventory UI | inventory collector/routes | `device_inventory` |
| VLAN | VLAN MIB walk → normalized VLAN rows → API | VLAN page | VLAN collector/routes | `vlan_information` |
| ARP | ARP MIB → normalized rows → monitoring/topology correlation | ARP module/topology | ARP collector | persisted module detail/operational tables |
| MAC/FDB | bridge/Q-bridge walk → port groups → inferred topology | MAC table, Port Map, topology | MAC collector | operational snapshot; MAC/ARP evidence |
| Routing | route MIB → normalized routes → API/UI | routing page | routing collector | `routing_table` |
| LLDP/CDP | neighbor MIB → identity/port correlation → confirmed link | LLDP page/topology | LLDP/CDP/topology collectors | `lldp_neighbors`, SNMP |
| Automatic Topology | collectors → merge/persist capability snapshot → API/SSE → graph build/SVG | `Topology.tsx` | SNMP topology routes/collector | `device_capabilities` JSON; SSE |
| Manual Topology | inventory + observed topology → manual graph edit → snapshot/change history → reconciliation/Port Map | `ManualTopology.tsx`, `DevicePortMap.tsx` | manual topology routes | manual snapshot/change tables |
| ICMP realtime monitoring | selected devices → background thread → parallel OS ping → metric/status DB → SSE | Incidents/device monitoring | `realtime_monitor.py` | device metrics/status history, ICMP |
| Alerts/Thresholds | metric/event → threshold evaluation → alert → notification/incident | alert/threshold pages | alerting service/core routes | alerts, thresholds, notifications |
| Events | normalized operational event CRUD/correlation input | Events | routes/services | `events` |
| Notifications | alert-derived or explicit notification lifecycle | Notifications panel/page | core routes, alerting | `notifications`, SMTP optional |
| Monitoring Jobs | user config → persisted schedule → APScheduler restore | Monitoring Jobs | polling scheduler | `monitoring_jobs`, `monitoring_configs` |
| Syslog | UDP/TCP → bounded queue → parser → record → rules → alert/incident | Syslog page | `backend/syslog`, syslog routes | syslog records/rules, UDP/TCP |
| Flow/sFlow/IPFIX | UDP datagram → parser/template cache → bounded queue → batch SQL → correlation → analytics API | Flow Analytics | flow receiver/parser/service/correlation | flow/counter tables, UDP |
| Packet Analysis | UI consumes packet/flow-facing APIs; no separate packet capture daemon found | `PacketAnalysis.tsx` | flow/discovery APIs | NOT FOUND as independent capture store |
| Linux Monitoring | detect/register → SSH/SNMP credentials → scheduler → metrics/security DB → UI | Linux page | linux package | nine Linux tables, SSH/SNMP |
| Availability | device/status intervals → report calculation → persisted report/outages → export | Availability | availability API/service | availability reports/outages |
| Incident | alerts → correlation/lifecycle/SLA/comments/attachments → API/UI | Incident pages | incident API/service/SLA | incident and SLA tables |
| RCA | alert/topology evidence → scoring/root selection → persisted RCA | RCA | RCA engine/routes | RCA incidents/evidence |
| Problem | incidents → problem lifecycle/history | Problem Management | problem routes | problem tables |
| Change | request → approval/schedule/implementation/rollback → linked CI/incident/problem | Change Management | change routes | change tables |
| Knowledge | article/version/workflow → links and feedback | Knowledge Base | knowledge routes/service | knowledge tables |
| CMDB | device/interface/topology reconciliation → CI relationships/history | CMDB | CMDB routes/service | CI type/item/relationship/history |
| Config Backup | SSH/device driver capture → versions → compare/baseline | Configuration Backups | config backup routes/drivers | configuration version/comparison |
| Config Compliance | policies → evaluation → violations | Compliance | config compliance routes | policy/violation tables |
| Reports/Audit | DB aggregation/export and audit trail | report/audit pages | core/overview routes | reports/audit logs |
| APM | ingested transactions/metrics/dependencies → SQL aggregation → dashboard | APM | APM routes/service | five APM tables, HTTP ingestion API |
| Virtualization | inventory submission → normalized objects → topology API | no dedicated routed page found | virtualization routes/protocol interface | virtualization objects |
| BGP | observation ingestion → time-window neighbor query | BGP | BGP routes | `bgp_observations` |
| QoS | sample ingestion → history query | QoS | QoS routes | `qos_samples` |

## 6. Blocking versus async audit

### High-risk blocking paths

1. `snmp/client.py`: pysnmp asyncio operations are wrapped as synchronous calls by creating event loops in a shared thread pool. This protects the FastAPI loop but limits concurrency to the executor size and adds per-operation loop/engine overhead.
2. `snmp/collector.py`: full collection walks OID roots sequentially per device. A slow device multiplies request timeout across roots.
3. `services/realtime_monitor.py`: every ICMP sample launches the OS `ping` subprocess; at scale this is process-creation and DB-write heavy.
4. `backend/syslog/__init__.py`: queue consumption performs parse, correlation and one DB commit per message in a single consumer.
5. SQLAlchemy uses synchronous psycopg sessions. Sync routes are safely executed by FastAPI's threadpool, but any sync DB call made directly inside an `async def` blocks its event loop.

### Medium-risk paths

- Discovery uses `subprocess.run`, blocking sockets and DNS calls; chunked discovery mitigates ping with a 20-worker pool.
- Linux Paramiko collection is synchronous; scheduler isolation is required to prevent API-loop blocking.
- Topology forced refresh performs live SNMP collections and large frontend correlation; it should remain explicit, not browser polling.
- SSE topology revision checks periodically read shared state per connected client; acceptable at small scale, but a database notification/pub-sub mechanism is preferable at large client counts.
- Config backup performs network/file work through synchronous drivers.

### Good async/bounded patterns already present

- Flow UDP receivers use `create_datagram_endpoint`.
- Flow/Syslog queues are bounded and record drops rather than allowing unbounded memory growth.
- Flow persistence batches up to 500 records or one second per transaction.
- SNMP scheduler uses a semaphore and `asyncio.to_thread` so synchronous collection does not run directly on the API loop.
- SSE responses disable proxy buffering and detect disconnects.

## 7. Scheduler architecture

- Library: APScheduler 3 `AsyncIOScheduler`.
- Job granularity: one persisted `MonitoringConfig` per device/module; scheduled as a one-shot `DateTrigger`, then explicitly rescheduled.
- Concurrency: application semaphore, default worker count 4; SNMP work goes to threads.
- Overlap: job identity is `device_id:module_name`; duplicate jobs are replaced and poll guards skip duplicates.
- Retry: transient errors retain enabled jobs and schedule the next interval; unsupported capability is terminal until reconfiguration/discovery.
- Timeouts: SNMP request default 3 seconds, one retry, 120-second overall operation timeout.
- Misfire: 300-second grace.
- HA: Redis scheduler lease ensures only one application instance starts the scheduler.
- Restart: enabled/running configs reload from PostgreSQL at application startup.
- Scaling limit: four concurrent device/module polls and sequential OID roots make long polling queues likely beyond hundreds of actively monitored modules, especially when devices time out.

## 8. SNMP architecture

- pysnmp constraint: `>=6.0,<7.0`.
- Transport: UDP, configurable port (default 161).
- Credentials: v2c community and v3 username/auth/privacy/security level; production requires credential encryption configuration.
- Operations: identity GET, bulk walk with GETNEXT fallback, full and per-domain minimal collections.
- Concurrency: sync facade over asyncio, shared thread executor, scheduler worker semaphore.
- Bounds: table row cap prevents runaway ARP/FDB walks.
- Processing: raw walk → vendor detection → OID registry/vendor profile → normalization → collector response → identity/capability and latest/history persistence.
- Principal losses: repeated `SnmpEngine`/event-loop construction, sequential root walks, duplicated device/module walks, timeout amplification, and multiple ORM commits.
- Recommendation: first share device poll sessions/results across modules, batch persistence, measure per-root latency, then redesign concurrency. Keep Python until these architectural costs are removed and benchmarked.

## 9. Topology architecture

### Automatic topology

- LLDP and CDP are confirmed physical-neighbor evidence and render as confirmed links.
- MAC/FDB and ARP are inferred port/adjacency evidence; they remain visible but are not LLDP verification.
- Routing next hops are collected as L3 reachability but excluded from physical topology edges.
- Backend persists topology JSON under `DeviceCapabilities.capability_detail`, selects the newest non-empty snapshot and exposes it through `/api/v1/snmp/topology`.
- Frontend combines inventory, stored module data and topology snapshot, deduplicates identity/link pairs, calculates a custom layout and renders SVG.
- Cross-client updates use `/api/v1/snmp/topology/stream`; expensive SNMP rebuilding is manual.
- Risk: a large `Topology.tsx` owns collection, correlation, layout, cache, interaction and rendering. It should later be split by responsibility without changing behavior.

### Manual topology

- `ManualTopology.tsx` is a custom editing workspace with drag/layout, connection and viewport logic.
- Backend stores current snapshots and change history.
- Automatic observations are reconciled with manual nodes/links; link keys are direction-independent.
- Port evidence, occupancy and device Port Map are supported.
- Risk: the frontend module is very large and has independent polling/reconciliation paths; pure graph/evidence/layout helpers should be separated and unit tested.

## 10. Flow ingestion architecture

- Active protocols: sFlow v5 on UDP/6343 and IPFIX v10 on UDP/4739 when enabled.
- IPFIX retains templates/options templates in an in-memory cache keyed by exporter/domain/template.
- Receiver parsing occurs in the asyncio datagram callback path and submits normalized records to a bounded 10,000-item queue.
- One consumer batches 500 records or one second and uses SQLAlchemy executemany-style inserts in one transaction.
- Correlation maps exporter/interface identities to managed devices/interfaces.
- Analytics routes use parameterized raw SQL for filtered records and time buckets.
- NetFlow v5/v9: NOT FOUND as an active receiver/parser.
- High-scale risks: Python packet parsing in the event-loop callback, one process-local template cache, one queue consumer and one DB writer. This is the strongest eventual Go/Rust candidate after observed throughput warrants it.

## 11. Syslog architecture

- asyncio UDP and TCP servers; configurable ports default to 5514/6514.
- Bounded queue size 10,000.
- Parser handles PRI, structured RFC5424 and a legacy/RFC3164-style form.
- Current consumer writes and commits one record at a time, then runs DB-backed correlation.
- Rules can create/link alerts/incidents; management API supports enable/disable and filtering.
- Retention is explicit batched cleanup, disabled when retention days is zero.
- High-risk areas: single consumer, per-message transaction, rule queries/correlation per record and no durable broker. First fix with batch insert/correlation and backpressure metrics; a separate Go receiver is a P1 option for sustained high event rates.

## 12. Database write path

- SNMP polling writes collector-specific historical rows, latest-value projections, polling history, monitoring config timestamps and alert state.
- ICMP realtime monitoring creates a metric row per ping and updates device/status history.
- Flow is correctly batch-inserted; Syslog is currently single-row/transaction.
- Latest CPU/memory/storage/interface/environment tables reduce read-side historical scans.
- Numerous indexes exist through model declarations and custom migrations, but query plans should be rechecked against production cardinality.
- Retention exists for Syslog/APM/Linux areas; a single consistent retention/partitioning policy is not evident for every historical SNMP/metric table.
- Pool ceiling is 40 connections per process. Four Uvicorn workers can theoretically request up to 160 DB connections, before other services.
- Likely bottlenecks: ICMP write frequency, Syslog commits, SNMP transaction count, unpartitioned historical growth, large JSON capability snapshots and ORM loops in reporting/ITSM serializers.

## 13. Frontend performance

### Positive

- Route-level code splitting.
- React Query caching and request deduplication.
- Deferred search for expensive lists/graphs.
- Pagination hooks and server-side filters in several modules.
- Topology now listens for shared changes rather than launching a forced SNMP walk every 30 seconds.

### Risks

- `Topology.tsx` performs multiple per-device monitoring requests, identity correlation, graph construction and custom layout in one component.
- `ManualTopology.tsx` has multiple timers and a very large interaction/state surface.
- Some monitoring pages retain intervals alongside SSE/React Query and should be checked for duplicate data paths.
- Knowledge/Change pages request several supporting collections at once; some endpoints return up to 500 items.
- Custom API sessionStorage cache plus React Query creates two cache layers and can complicate invalidation.
- SVG topology is acceptable for tens/hundreds of nodes but lacks virtualization for thousands.
- Recharts and large tables should receive bounded windows/pagination rather than entire histories.

## 14. Current scalability estimate

These are architecture bands, not benchmark claims.

| Managed devices | Assessment | Reason |
|---:|---|---|
| 100 | COMFORTABLE | Four scheduler workers and current PostgreSQL model are workable if intervals are moderate |
| 500 | NEEDS OPTIMIZATION | SNMP timeout queues, subprocess ICMP and historical writes become visible constraints |
| 1,000 | HIGH RISK | Per-device/module job count, four workers, DB write amplification and UI graph/table payloads require redesign |
| 5,000 | NOT SUITABLE | Current in-process schedulers/receivers and synchronous collection cannot provide predictable intervals |
| 10,000 | NOT SUITABLE | Requires distributed poll workers, partitioned retention, ingestion services and capacity-tested messaging/storage |

## 15. Language suitability matrix

| Module group | Current | I/O/CPU/concurrency | Suitability | Direction |
|---|---|---|---|---|
| CRUD/RBAC/ITSM/CMDB | Python/FastAPI | DB I/O, low CPU | Good | Keep Python |
| Reports/availability/RCA | Python | DB aggregation, moderate CPU | Good with query tuning | Keep Python; optimize SQL |
| SNMP collectors | Python/pysnmp | high network I/O/concurrency | Appropriate but architecture-limited | P0 Python redesign; Go only after benchmark |
| ICMP monitoring | Python + subprocess | high process/concurrency overhead | Weak at scale | Replace subprocess model; Go candidate |
| Discovery | Python + subprocess/sockets | bursty I/O | Adequate through hundreds | Improve async/bounds; Go optional |
| Syslog receiver | Python asyncio | very high I/O, light parse | Adequate at modest rate | Batch first; Go P1 at high EPS |
| sFlow/IPFIX | Python asyncio parser | high packet rate and CPU parse | Medium/high risk | Go or Rust P1 candidate |
| Linux SSH/SNMP | Python/Paramiko | network I/O | Good | Keep Python |
| APM/analytics | Python + SQL | DB aggregation | Good | Keep Python, optimize SQL/retention |
| Frontend | TypeScript/React | rendering/client I/O | Good | Keep TypeScript; modularize/virtualize |
| Topology algorithms | TypeScript + Python | graph correlation/layout | Good for current size | Keep; extract/test pure functions |
| Config backup | Python/Paramiko | network/file I/O | Good | Keep Python |
| Virtualization/BGP/QoS APIs | Python | low/moderate I/O | Good | Keep Python |

Java is not justified by the present module shapes. Rust is most relevant only to a future exceptionally high-rate packet parser. Go is the more pragmatic candidate for a future distributed poll/ICMP/Syslog/flow edge service, not for CRUD or ITSM migration.

## 16. Optimization and migration priority

### P0 — architecture/performance without language migration

1. SNMP: reuse collection results across modules, avoid sequential duplicate walks, instrument OID-root latency and batch DB writes.
2. ICMP: stop spawning one OS process per sample; use a bounded native/raw-socket or managed probe service.
3. Syslog: batch inserts and correlation, expose queue depth/drop metrics, define retention defaults.
4. Database: production query plans, connection budget per worker, retention/partition strategy and write batching.
5. Frontend: separate topology data/correlation/layout/render hooks; remove redundant polling where SSE/server state exists.

### P1 — components that may strongly benefit from Go

- High-rate sFlow/IPFIX receiver/parser.
- High-rate Syslog edge receiver.
- Distributed ICMP probe worker.
- Distributed SNMP poll worker only if optimized Python still misses measured targets.

### P2 — optional migration

- Discovery probe agent for remote sites.
- Rust packet decoding only when profiling proves parser CPU dominates.

### P3 — keep as-is technologically

- FastAPI CRUD, RBAC, ITSM, CMDB, configuration, availability, RCA and reporting orchestration.
- React/TypeScript frontend.
- PostgreSQL and SQLAlchemy domain persistence.

## 17. Infrastructure

- Actual local execution: shell/Python scripts start Uvicorn and Vite.
- Deployment guide documents Uvicorn workers, Nginx, systemd and example Docker/Compose configuration.
- Dockerfile/Compose/systemd unit files were not found as committed runtime artifacts in the inspected file search; documentation examples are not equivalent to deployed assets.
- Nginx is documented, not implemented in the repository as an active config file.
- PM2: NOT FOUND.
- Environment management: pydantic-settings reads `backend/.env`; production validates secret and credential encryption keys.
- Service lifecycle: FastAPI lifespan starts migrations/seeding, leader-elected polling, Linux scheduler, optional flow and Syslog receivers.

## 18. Key source references

- Frontend manifest: `figma design/package.json`
- Frontend routes/RBAC: `figma design/src/routes.tsx`
- API cache and SSE parser: `figma design/src/lib/api.ts`
- Automatic topology: `figma design/src/pages/Topology.tsx`
- Manual topology: `figma design/src/pages/ManualTopology.tsx`
- SNMP UI queries: `figma design/src/features/snmp/hooks/useSnmpQueries.ts`
- Backend composition/lifespan: `hardik/backend/main.py`
- Settings: `hardik/backend/config/settings.py`
- DB pool: `hardik/backend/database/session.py`
- Migrations: `hardik/backend/database/migrations.py`
- Core models: `hardik/backend/models/__init__.py`
- SNMP models: `hardik/backend/models/snmp.py`, `identity.py`
- SNMP client/orchestration: `hardik/backend/snmp/client.py`, `collector.py`
- SNMP collectors: `hardik/backend/snmp/collectors/`
- Poll scheduler: `hardik/backend/services/snmp_polling.py`
- HA lease/cache: `hardik/backend/services/ha_scheduler.py`, `backend/cache/redis_cache.py`
- Discovery: `hardik/backend/api/discovery_routes.py`, `backend/services/chunked_discovery.py`, `hardik/discovery_modules/`
- ICMP realtime: `hardik/backend/services/realtime_monitor.py`
- Flow: `hardik/backend/flow/`
- Syslog: `hardik/backend/syslog/__init__.py`
- Linux monitoring: `hardik/backend/linux_monitoring/`
- ITSM/CMDB/APM/config APIs: `hardik/backend/api/*_routes.py`

## Console summary

TECH STACK AUDIT: COMPLETE

TOTAL MODULES FOUND: 43 functional areas

PYTHON MODULES: FastAPI/RBAC, discovery, SNMP, polling, ICMP, topology backend, alerts/events, Syslog, flow, Linux, availability, Incident/RCA/Problem/Change/Knowledge, CMDB, configuration, reports, APM, virtualization, BGP and QoS

FRONTEND STACK: React 19 + TypeScript + Vite 8 + React Router 8 + TanStack React Query 5 + Tailwind 4 + Recharts + custom SVG topology

DATABASE: PostgreSQL + psycopg 3 + synchronous SQLAlchemy 2 + custom migrations

CACHE/QUEUE: Redis cache/HA lease; in-process bounded asyncio queues; no Celery/RQ/Kafka/RabbitMQ

HIGH-RISK PERFORMANCE MODULES: SNMP polling, subprocess ICMP, Syslog persistence, sFlow/IPFIX ingestion, historical database writes

BEST GO MIGRATION CANDIDATES: flow receiver/parser, Syslog edge receiver, ICMP probe worker, later distributed SNMP worker

KEEP IN PYTHON: FastAPI CRUD/RBAC, ITSM, CMDB, configuration, availability, RCA, reports, Linux orchestration and APM APIs

FIRST MODULE TO OPTIMIZE: SNMP polling and persistence

REPORT: NMS_TECH_STACK_AUDIT.md
