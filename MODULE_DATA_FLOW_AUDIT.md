# Recent NMS Module Data-Flow Audit

**Audit date:** 2026-08-29  
**Scope:** Recently added frontend module pages currently present in `figma design/src/routes.tsx`.  
**Method:** Read-only inspection of frontend components, API client functions, FastAPI routers, services/collectors, models, migrations and tests. No application code was changed.

## Status Meaning

- **WORKING WITH DATA:** The full source-to-page path is wired and data is available in the inspected runtime/database.
- **WORKING BUT NO SOURCE DATA:** The page/read path is wired and its empty state is intentional, but no records are produced or available in the current project state.
- **PARTIAL:** The page and some persistence/API path exist, but an important producer, lifecycle integration, collector, or workflow is missing.
- **BROKEN:** A verified code/contract/wiring defect prevents the page from loading or using its declared data path.

Because PostgreSQL (`127.0.0.1:5432`), backend API (`127.0.0.1:8000`) and frontend dev server (`127.0.0.1:5173`) were unavailable during this audit, no page can be certified as **WORKING WITH DATA** from live observation. The statuses below describe static data-flow completeness; the runtime gate is recorded separately.

## Summary

| Page | Route | Status |
|---|---|---|
| APM | `/apm` | PARTIAL |
| Availability | `/availability` | WORKING BUT NO SOURCE DATA |
| BGP | `/bgp` | PARTIAL |
| CMDB | `/cmdb` | WORKING BUT NO SOURCE DATA |
| Change Management | `/change-management` | WORKING BUT NO SOURCE DATA |
| Configuration Backups | `/configuration-backups` | PARTIAL |
| Configuration Compliance | `/configuration-compliance` | WORKING BUT NO SOURCE DATA |
| Flow Analytics | `/flow-analytics` | PARTIAL |
| Incident Management | `/incident-management` | WORKING BUT NO SOURCE DATA |
| Knowledge Base | `/knowledge-base` | WORKING BUT NO SOURCE DATA |
| Problem Management | `/problem-management` | WORKING BUT NO SOURCE DATA |
| QoS | `/qos` | PARTIAL |
| RCA | `/rca` | WORKING BUT NO SOURCE DATA |

**BROKEN pages found:** none by static route/API contract inspection.  
**WORKING WITH DATA pages verified live:** none, because the database and application services were unavailable.

## Detailed Data Flows

### 1. APM

- **Frontend component:** [APM.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/pages/APM.tsx#L30)
- **Route:** `/apm`, permission `apm:read`, registered in [routes.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/routes.tsx#L82)
- **Data source:** External APM metric producer must POST metric batches; the page itself does not generate metrics. The expected producer/agent/OTel bridge is not present.
- **Collector/service:** [apm/service.py](/home/agnigate/Desktop/NMS/hardik/backend/apm/service.py#L15) validates and batch-inserts `APMMetric`; no scheduled or application-managed producer was found.
- **Database tables:** `apm_applications`, `apm_services`, `apm_transactions`, `apm_metric_samples`, `apm_dependencies`; metric insertion is in [service.py](/home/agnigate/Desktop/NMS/hardik/backend/apm/service.py#L92).
- **API endpoints:** `GET /api/v1/apm/applications`, `/services`, `/overview`, `/services/{service_id}/metrics`, `/dependencies`; ingestion is `POST /api/v1/apm/metrics`, in [apm_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/apm_routes.py#L53).
- **Frontend API calls:** `listAPMApplications`, `listAPMServices`, `getAPMOverview`, `getAPMServiceMetrics`, `getAPMDependencies` in [api.ts](/home/agnigate/Desktop/NMS/figma%20design/src/lib/api.ts#L371).
- **Status:** **PARTIAL**.
- **Exact empty reason:** If `apm_metric_samples` has no rows in the selected time window, `/overview` returns `items: []`, and the page renders “No stored APM metrics for these filters.” Applications/services/dependencies are also empty unless separately seeded. There is no active agent/OTel/transaction source feeding `POST /apm/metrics`; the page subtitle explicitly says “no automatic polling.”

### 2. Enterprise Availability

- **Frontend component:** [Availability.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/pages/Availability.tsx#L5)
- **Route:** `/availability`, permission `availability:read`, registered in [routes.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/routes.tsx#L93)
- **Data source:** Existing device/interface/site/business-service status history and maintenance windows, processed on report generation.
- **Collector/service:** [services/availability.py](/home/agnigate/Desktop/NMS/hardik/backend/services/availability.py#L4) calculates planned/unplanned downtime and reasons. It is not a continuously running collector.
- **Database tables:** `availability_reports` plus source status/history and maintenance-window records.
- **API endpoints:** `POST /api/v1/availability/reports` generates a report; `GET /api/v1/availability/reports` reads history; CSV export is also available in [availability_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/availability_routes.py#L12).
- **Frontend API call:** `listAvailabilityReports` in [api.ts](/home/agnigate/Desktop/NMS/figma%20design/src/lib/api.ts#L3351).
- **Status:** **WORKING BUT NO SOURCE DATA**.
- **Exact empty reason:** The page only calls `GET /availability/reports`; it does not call the report-generation POST endpoint. `availability_reports` remains empty until a user or external workflow generates reports. If no rows exist, the component intentionally renders “No historical availability reports.”

### 3. BGP

- **Frontend component:** [BGP.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/pages/BGP.tsx#L1)
- **Route:** `/bgp`, permission `bgp:read`, registered in [routes.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/routes.tsx#L94)
- **Data source:** Intended BGP observations from network devices.
- **Collector/service:** No BGP SNMP collector or scheduler integration was found. The only producer is the API payload accepted by `POST /observations`.
- **Database table:** `bgp_observations` via [models/bgp.py](/home/agnigate/Desktop/NMS/hardik/backend/models/bgp.py#L5).
- **API endpoints:** `POST /api/v1/bgp/observations` and `GET /api/v1/bgp/neighbors` in [bgp_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/bgp_routes.py#L8).
- **Frontend API call:** `listBGPNeighbors` in [api.ts](/home/agnigate/Desktop/NMS/figma%20design/src/lib/api.ts#L3355).
- **Status:** **PARTIAL**.
- **Exact empty reason:** `GET /bgp/neighbors` reads only `bgp_observations`; no SNMP poll or background job inserts observations. Until an authorized caller posts observations, the page maps an empty response to an empty table.

### 4. CMDB

- **Frontend component:** [CMDB.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/pages/CMDB.tsx#L24)
- **Route:** `/cmdb`, permission `cmdb:read`, registered in [routes.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/routes.tsx#L84)
- **Data source:** Manual CI creation and explicit inventory/topology synchronization from existing devices, interfaces, sites and applications.
- **Collector/service:** [cmdb/service.py](/home/agnigate/Desktop/NMS/hardik/backend/cmdb/service.py#L86) provides inventory/topology synchronization, but `main.py` does not run a startup/periodic CMDB sync.
- **Database tables:** `cmdb_configuration_items`, `cmdb_ci_types`, `cmdb_ci_relationships`, `cmdb_ci_history`.
- **API endpoints:** `GET /api/v1/cmdb/types`, `/items`, `/items/{id}/relationships`, `/items/{id}/history`; creation and explicit sync endpoints are in [cmdb_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/cmdb_routes.py#L61).
- **Frontend API calls:** `listCMDBTypes`, `listCMDBItems`, `getCMDBRelationships`, `getCMDBHistory` in [api.ts](/home/agnigate/Desktop/NMS/figma%20design/src/lib/api.ts#L383).
- **Status:** **WORKING BUT NO SOURCE DATA**.
- **Exact empty reason:** The page reads `cmdb_configuration_items`, but no automatic synchronization is invoked by the application lifecycle. With no manually created CIs and no prior `/relationships/sync` or `/relationships/sync/topology` workflow, `/cmdb/items` returns an empty list and the page renders “No configuration items match these filters.”

### 5. Change Management

- **Frontend component:** [ChangeManagement.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/pages/ChangeManagement.tsx#L10)
- **Route:** `/change-management`, permission `changes:read`, registered in [routes.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/routes.tsx#L87)
- **Data source:** User-created change requests; linked CMDB items and incidents are supplied during creation/link workflows.
- **Collector/service:** No collector. Creation/approval/history logic is in [change_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/change_routes.py#L75).
- **Database tables:** `change_requests`, `change_cis`, `change_incidents`, `change_history`, plus `audit_logs`.
- **API endpoints:** `GET/POST/PATCH /api/v1/changes`, `POST /{id}/approve`, CI/incident link endpoints.
- **Frontend API calls:** `listChanges`, `createChange`, `approveChange`, `updateChange` in [api.ts](/home/agnigate/Desktop/NMS/figma%20design/src/lib/api.ts#L3324).
- **Status:** **WORKING BUT NO SOURCE DATA**.
- **Exact empty reason:** There is no seed data and no automatic change creation. The page list calls `GET /changes`; it becomes non-empty only after a user with `changes:create` submits a change request.

### 6. Configuration Backups

- **Frontend component:** [ConfigurationBackups.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/pages/ConfigurationBackups.tsx#L26)
- **Route:** `/configuration-backups`, permission `config_backups:read`, registered in [routes.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/routes.tsx#L90)
- **Data source:** Manual configuration content submitted by a user. A real device/vendor capture source is not wired.
- **Collector/service:** [config_backups/service.py](/home/agnigate/Desktop/NMS/hardik/config_backups/service.py) encrypts, checksums and versions supplied content; [config_backups/drivers.py](/home/agnigate/Desktop/NMS/hardik/config_backups/drivers.py) has no registered vendor drivers.
- **Database tables:** `device_configuration_versions`, `configuration_comparisons`.
- **API endpoints:** `POST /api/v1/config-backups/capture`, `GET /devices/{device_id}`, `GET /devices/{device_id}/versions/{version}`, `POST /compare`, baseline/current compare, in [config_backup_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/config_backup_routes.py#L39).
- **Frontend API calls:** `listConfigurationVersions`, `captureConfiguration`, `compareConfigurationVersions`, `compareBaselineCurrent` in [api.ts](/home/agnigate/Desktop/NMS/figma%20design/src/lib/api.ts#L3339).
- **Status:** **PARTIAL**.
- **Exact empty reason:** The page requires a manually entered numeric device ID and configuration content. No device selector, scheduled capture, startup capture, registered driver or SNMP/SSH retrieval feeds `POST /capture`; therefore the history table is empty for devices with no manually submitted version and displays “Enter a device ID to inspect configuration history.”

### 7. Configuration Compliance

- **Frontend component:** [ConfigurationCompliance.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/pages/ConfigurationCompliance.tsx#L6)
- **Route:** `/configuration-compliance`, permission `config_compliance:read`, registered in [routes.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/routes.tsx#L91)
- **Data source:** Compliance policies and explicit evaluation against configuration versions.
- **Collector/service:** [config_backups/compliance.py](/home/agnigate/Desktop/NMS/hardik/config_backups/compliance.py) evaluates a policy only when `POST /evaluate` is called; no scheduled evaluator was found.
- **Database tables:** `configuration_compliance_policies`, `configuration_compliance_violations`, and `device_configuration_versions`.
- **API endpoints:** `GET/POST /api/v1/config-compliance/policies`, `POST /evaluate`, `GET /violations` in [config_compliance_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/config_compliance_routes.py#L17).
- **Frontend API calls:** `listConfigurationCompliancePolicies` and `listConfigurationComplianceViolations('open')` in [api.ts](/home/agnigate/Desktop/NMS/figma%20design/src/lib/api.ts#L3346).
- **Status:** **WORKING BUT NO SOURCE DATA**.
- **Exact empty reason:** The page is read-only and does not create policies or run evaluations. Without manually created policies and an explicit evaluation against an existing configuration version, both endpoint lists are empty; the page correctly shows no policies and “No open violations.”

### 8. Flow Analytics

- **Frontend component:** [FlowAnalytics.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/pages/FlowAnalytics.tsx#L51)
- **Route:** `/flow-analytics`, permission `flows:read`, registered in [routes.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/routes.tsx#L82)
- **Data source:** NetFlow/IPFIX/sFlow/J-Flow/NetStream packets should be received, parsed and persisted as normalized flows.
- **Collector/service:** Parsers exist in [flow/parsers.py](/home/agnigate/Desktop/NMS/hardik/flow/parsers.py); [flow/service.py](/home/agnigate/Desktop/NMS/hardik/flow/service.py#L38) provides bounded queue and batch writes, but no flow receiver is instantiated by `main.py` and no FastAPI packet-ingestion endpoint was found.
- **Database table:** `flow_records`.
- **API endpoints:** `GET /api/v1/flows/analytics/{talkers|sources|destinations|applications|protocols|conversations|interfaces}` and `/trends` in [flow_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/flow_routes.py#L13).
- **Frontend API calls:** `getFlowAnalytics` and `getFlowTrends` in [api.ts](/home/agnigate/Desktop/NMS/figma%20design/src/lib/api.ts#L299).
- **Status:** **PARTIAL**.
- **Exact empty reason:** Analytics queries read `flow_records` only. The parser/queue tests do not create production rows, and the receiver/lifecycle ingestion path is absent. With no externally inserted rows, every dimension and trend returns an empty result and the page renders empty analytics tables.

### 9. Incident Management

- **Frontend component:** [IncidentManagement.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/pages/IncidentManagement.tsx#L10)
- **Route:** `/incident-management`, permission `incidents:read`, registered in [routes.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/routes.tsx#L86)
- **Data source:** Manually created incidents and linked existing alerts/RCA/services; automatic qualifying-alert creation is not wired.
- **Collector/service:** [incidents/service.py](/home/agnigate/Desktop/NMS/hardik/incidents/service.py) links RCA and [incidents/sla.py](/home/agnigate/Desktop/NMS/hardik/incidents/sla.py) evaluates timers on request paths; no incident producer worker was found.
- **Database tables:** `incidents`, `incident_alerts`, `incident_comments`, `incident_attachments`, `incident_sla_configs`, `incident_sla_timers`, `incident_sla_history`, plus `alerts` and `rca_incidents`.
- **API endpoints:** `GET/POST/PATCH /api/v1/incidents`, detail/comments/attachments, and SLA policy endpoints in [incident_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/incident_routes.py#L70).
- **Frontend API calls:** `listIncidents`, `createIncident`, `getManagedIncident`, `updateIncident`, `addIncidentComment` in [api.ts](/home/agnigate/Desktop/NMS/figma%20design/src/lib/api.ts#L3308).
- **Status:** **WORKING BUT NO SOURCE DATA**.
- **Exact empty reason:** No incident is seeded and no automatic alert-to-incident worker creates one. The page list is empty until a user creates an incident through `POST /incidents`; it then displays linked data if alert/RCA IDs are supplied.

### 10. Knowledge Base

- **Frontend component:** [KnowledgeBase.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/pages/KnowledgeBase.tsx#L10)
- **Route:** `/knowledge-base`, permission `knowledge:read`, registered in [routes.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/routes.tsx#L89)
- **Data source:** User-created published articles/known errors/runbooks.
- **Collector/service:** No collector; CRUD/version/audit logic is in [knowledge_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/knowledge_routes.py#L47).
- **Database tables:** `knowledge_articles`, `knowledge_article_versions`, and typed incident/problem/device/service link tables.
- **API endpoints:** `GET/POST/PATCH /api/v1/knowledge`, article detail and versions.
- **Frontend API calls:** `listKnowledge`, `createKnowledge`, `getKnowledge`, `updateKnowledge` in [api.ts](/home/agnigate/Desktop/NMS/figma%20design/src/lib/api.ts#L3332).
- **Status:** **WORKING BUT NO SOURCE DATA**.
- **Exact empty reason:** The listing defaults to `status=published`, while there is no seeded article. Until a user creates/publishes an article, `GET /knowledge` returns no items and the page shows “No published articles found.”

### 11. Problem Management

- **Frontend component:** [ProblemManagement.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/pages/ProblemManagement.tsx#L10)
- **Route:** `/problem-management`, permission `problems:read`, registered in [routes.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/routes.tsx#L88)
- **Data source:** User-created problems linked to recurring incidents; no recurrence detector/automatic promotion was found.
- **Collector/service:** CRUD/history/link logic is in [problem_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/problem_routes.py#L53); no automated problem source.
- **Database tables:** `problems`, `problem_incidents`, `problem_history`.
- **API endpoints:** `GET/POST/PATCH /api/v1/problems`, incident link and history endpoints.
- **Frontend API calls:** `listProblems`, `createProblem`, `getProblem`, `updateProblem` in [api.ts](/home/agnigate/Desktop/NMS/figma%20design/src/lib/api.ts#L3317).
- **Status:** **WORKING BUT NO SOURCE DATA**.
- **Exact empty reason:** No problems are seeded and recurring incidents are not automatically promoted. `GET /problems` therefore returns an empty `items` list until the create action is used.

### 12. QoS

- **Frontend component:** [QoS.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/pages/QoS.tsx#L1)
- **Route:** `/qos`, permission `qos:read`, registered in [routes.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/routes.tsx#L93)
- **Data source:** ToS/DSCP/PHB/class/queue samples from standard or vendor QoS collectors.
- **Collector/service:** No QoS SNMP collector, vendor adapter, scheduler feed, threshold evaluation or alert producer was found. The only writer is `POST /samples`.
- **Database table:** `qos_samples` via [models/qos.py](/home/agnigate/Desktop/NMS/hardik/backend/models/qos.py#L5).
- **API endpoints:** `POST /api/v1/qos/samples` and `GET /api/v1/qos/samples` in [qos_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/qos_routes.py#L8).
- **Frontend API call:** `listQoSSamples` in [api.ts](/home/agnigate/Desktop/NMS/figma%20design/src/lib/api.ts#L3353).
- **Status:** **PARTIAL**.
- **Exact empty reason:** The read endpoint has no collector-backed writer. Without externally posted sample rows, `GET /qos/samples` returns `[]` and the table has no rows. The UI also has no device/filter or sample-ingestion action.

### 13. Root Cause Analysis

- **Frontend component:** [RCA.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/pages/RCA.tsx#L11)
- **Route:** `/rca`, permission `rca:read`, registered in [routes.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/routes.tsx#L85)
- **Data source:** Existing `alerts`, `events`, CMDB relationships and topology links within the selected time window.
- **Collector/service:** [rca/engine.py](/home/agnigate/Desktop/NMS/hardik/rca/engine.py) correlates alert evidence. Analysis runs only when the user invokes `POST /analyze`; no continuous RCA worker was found.
- **Database tables:** `rca_incidents`, `rca_evidence`, linked `alerts`, `events`, `cmdb_ci_relationships`.
- **API endpoints:** `POST /api/v1/rca/analyze`, `GET /api/v1/rca/incidents`, `GET /api/v1/rca/incidents/{id}` in [rca_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/rca_routes.py#L29).
- **Frontend API calls:** `listRCAIncidents`, `getRCAIncident`, `analyzeRCA` in [api.ts](/home/agnigate/Desktop/NMS/figma%20design/src/lib/api.ts#L3303).
- **Status:** **WORKING BUT NO SOURCE DATA**.
- **Exact empty reason:** If no correlated alerts exist in the selected window, `correlate_alerts` returns no incident and `GET /rca/incidents` returns an empty `items` list. RCA is not pre-populated and analysis is not scheduled; the page correctly prompts the operator to run analysis.

## Backend-Only Recent Modules With No Current Frontend Page

These modules have backend routes/models but are not represented as current frontend pages in the audited route tree:

| Module | Backend data flow | Page status |
|---|---|---|
| Syslog | UDP/TCP receiver code → `SyslogRecord` → `syslog_records` → `GET /api/v1/syslog/records`; receiver is not started by FastAPI lifespan | No current page |
| Virtualization | External normalized inventory POST → `VirtualObject` → `virtualization_objects` → `GET /api/v1/virtualization/objects`/`topology`; adapter registry is empty | No current page |

Their absence is not marked BROKEN because there is no current page component to load; it is a missing frontend surface.

## Runtime Verification

The following checks were performed during the audit:

- `pg_isready -h 127.0.0.1 -p 5432`: no response.
- `curl --max-time 3 http://127.0.0.1:8000/api/v1/health`: connection refused.
- `curl --max-time 3 http://127.0.0.1:5173/`: connection refused.
- Frontend route/API source inspection: all 13 audited routes are present and mounted in [main.py](/home/agnigate/Desktop/NMS/hardik/backend/main.py#L108) and [routes.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/routes.tsx#L63).

Therefore the observed browser state is **unavailable service**, not an observed empty response. The exact empty reasons above are derived from the source data producers and read paths.

## Priority Actions

1. Start PostgreSQL, Redis, backend and frontend in an isolated validation environment, then capture authenticated page/API responses.
2. Add application-managed APM, flow, Syslog, QoS and BGP producers or explicitly expose their external-ingestion contracts and health state.
3. Add lifecycle-managed report generation, CMDB synchronization, configuration capture and compliance evaluation where automatic data is required.
4. Add browser E2E tests that assert loading, empty, error and populated states for every audited page.
