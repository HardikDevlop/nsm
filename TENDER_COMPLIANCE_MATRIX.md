# Tender / ODT Compliance Matrix

**Requirement source:** `/home/agnigate/Downloads/nms SEP.odt`  
**Audit date:** 2026-08-29  
**Repository:** `/home/agnigate/Desktop/NMS`  
**Audit type:** Read-only source, test, wiring and evidence review. No application code was changed for this matrix.

## Status Rules

- **COMPLETED:** The repository contains the requested implementation and a directly relevant automated test or authoritative project document. This does not replace customer acceptance, production operation or external documentary evidence.
- **PARTIAL:** Some implementation, route, model, UI or test foundation exists, but the full tender behavior, integration, coverage or operational proof is missing.
- **NOT IMPLEMENTED:** No adequate implementation was found in the existing NMS.
- **EXTERNAL EVIDENCE REQUIRED:** The requirement is a certification, deployment, warranty, OEM/service, copyright, purchase-order, sign-off or other document claim that source code cannot prove.

## Matrix

| ODT item(s) | Requirement area | Status | Evidence / reason |
|---|---|---|---|
| 1 | Network monitoring/configuration, wired and wireless single pane, future 5,000-device scale | PARTIAL | Core SNMP/device monitoring and wireless collector code exists in `hardik/backend/snmp/`; progressive harness reaches 5,000 **simulated operations**, not 5,000 real devices. See [FINAL_PERFORMANCE_REPORT.md](/home/agnigate/Desktop/NMS/FINAL_PERFORMANCE_REPORT.md). |
| 2 | Deep application visibility using AVC/NetFlow/sFlow/NBAR/packet inspection plus topology | PARTIAL | Flow parsers/model and topology code exist; no AVC/NBAR/packet-inspection implementation and flow runtime is not fully wired. See [FINAL_GAP_ANALYSIS.md](/home/agnigate/Desktop/NMS/FINAL_GAP_ANALYSIS.md#L86). |
| 3 | Two India deployments, PO/signoff, Linux/64-bit/RDBMS/time-series, certifications, IPR and ITIL Gold | EXTERNAL EVIDENCE REQUIRED | The repository cannot prove deployments, purchase orders, completion signoffs, ISO/CERT-In/CIS/CMMI/IPR/Axelos documents or warranty. Runtime platform/database claims also require deployment evidence. |
| 4 | Customizable NOC/browser at-a-glance summary | PARTIAL | Dashboard, overview route and browser UI exist, but secured deployment and NOC acceptance evidence are absent. |
| 5 | Discover/configure/monitor/manage/deploy grouped device configurations | PARTIAL | Discovery, device management and configuration models/routes exist; complete approval-backed group deployment workflow is not proven. |
| 6 | Flexible administrator roles and RBAC | PARTIAL | Permission dependencies and protected routes exist in `hardik/backend/dependencies.py`, `hardik/backend/api/` and `figma design/src/routes.tsx`; live allow/deny and organization scope could not run because PostgreSQL/API were unavailable. |
| 7 | Customizable dashboards and historical performance | PARTIAL | Dashboard pages, metric history models and monitoring routes exist; live data and end-to-end customization were not validated. |
| 8 | Interface utilization and traffic-pattern reports | PARTIAL | Interface collectors, reports and flow analytics foundations exist; complete live report correctness was not demonstrated. |
| 9 | Themes, multilingual UI, state logos and keyboard shortcuts | PARTIAL | Theme, English/Hindi catalogs, branding context and shortcut hook exist; page-by-page hardcoded text remains and state/tenant branding plus browser accessibility proof are incomplete. |
| 10 | Direct OEM 24x7x365 TAC and hardware replacement warranty | EXTERNAL EVIDENCE REQUIRED | Requires contractual OEM support and warranty documents. |
| 11–13 | End-to-end performance/availability/fault/event/impact, heterogeneous resources, helpdesk/asset/incident/RCA/change/configuration suite | PARTIAL | Broad modules and routes exist, but complete integrated resource coverage and production workflow are not proven. |
| 14 | Unified ITSM and common CMDB architecture | PARTIAL | Additive CMDB, incident, problem, change and knowledge models/routes exist; full unified service-management workflow is not proven. |
| 15 | Integrated web network diagram builder comparable to Visio | PARTIAL | Automatic/manual topology UI exists; a complete Visio-like builder with preloaded shapes is not established. |
| 16–17 | Future scale without major redesign; distributed, scalable, third-party integration | PARTIAL | Additive architecture and HA design exist; live multi-instance scalability and integration evidence are absent. |
| 18–19 | All IT assets, agent/agentless event/performance/capacity monitoring without separate collectors | PARTIAL | Device, Linux and SNMP foundations exist; complete all-asset and agent/agentless enterprise coverage is not implemented/proven. |
| 20–22 | Intelligent event identification, probable cause, maintenance suppression | PARTIAL | Alert/RCA/availability foundations exist; end-to-end intelligent correlation and configured outage suppression require live validation. |
| 23 | Searchable knowledge base and known errors | COMPLETED | Implemented in [knowledge_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/knowledge_routes.py#L47) with models/versioning in [knowledge.py](/home/agnigate/Desktop/NMS/hardik/backend/models/knowledge.py#L9); regression coverage in [test_knowledge_base.py](/home/agnigate/Desktop/NMS/hardik/tests/test_knowledge_base.py). |
| 24–25 | Single console/reporting for network/server/app/database and capacity optimization | PARTIAL | Core overview and module pages exist; database/APM/agent coverage and capacity-planning evidence are incomplete. |
| 26–28 | Market-leading database monitoring and application/database collection/analysis | NOT IMPLEMENTED | No complete database vendor monitoring collector and unified database performance workflow were found. |
| 29–32 | Business service levels, KPI/scorecards, consolidated top-down drill-down dashboard | PARTIAL | Availability, APM, CMDB and dashboard foundations exist; KPI scorecard automation and full drill-down service model are incomplete. |
| 33–34 | Configuration rollback and configuration-level task/object/policy control | PARTIAL | Version/diff/compliance foundations exist; actual rollback/execution control is not implemented. |
| 36–37 | Approval-based network changes; Telnet/SSH and troubleshooting toolkit | PARTIAL | Change approval records exist in [change_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/change_routes.py#L116); device configuration execution, remote access and complete ping/telnet/traceroute/SNMP-walk/port-scan workflow are not established. |
| 38–41 | Dynamic baselines, proactive user error detection, end-user view and automated repair | NOT IMPLEMENTED | APM aggregate metrics exist, but dynamic baselines, real-user telemetry, broad/targeted slowdown attribution and automated repair are absent. |
| 42 | Listed application/database monitoring attributes | PARTIAL | APM metric model and ingestion exist in [apm.py](/home/agnigate/Desktop/NMS/hardik/backend/models/apm.py#L9) and [service.py](/home/agnigate/Desktop/NMS/hardik/backend/apm/service.py#L92); the full listed database attribute set and vendor integrations are not implemented. |
| 43, 48 | IP range/IPv6, seed-router, new-device discovery and exclusions | PARTIAL | Multiple discovery routes and chunked scanning exist in [discovery_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/discovery_routes.py#L200); live IPv6/seed-router/database preservation validation is missing. |
| 49–51 | Physical inventory, LAN/WAN mapping, asset model and unused/dormant port reports | PARTIAL | Inventory, interfaces and topology collectors exist; complete unused/dormant-port analysis and report evidence are not present. |
| 52 | Availability with outage exclusion and reason | PARTIAL | Availability calculation exists in [availability.py](/home/agnigate/Desktop/NMS/hardik/backend/services/availability.py#L4) with planned/unplanned fields; maintenance correctness and live historical validation are incomplete. |
| 53–56 | Virtual infrastructure discovery, non-SNMP collection, extensible VMware/Hyper-V/KVM architecture | PARTIAL | Normalized virtualization model/API and adapter protocol exist in [virtualization/__init__.py](/home/agnigate/Desktop/NMS/hardik/backend/virtualization/__init__.py#L2); no registered VMware, Hyper-V or KVM adapters. |
| 54 | ToS, DSCP, PHB, BGP AS and next-hop monitoring | PARTIAL | QoS/BGP models/routes/UI exist; SNMP collection, history/alert integration and end-to-end monitoring are missing. |
| 57 | Out-of-box SNMPv3 discovery and management | PARTIAL | v3 credential/client and collector code plus SNMP unit tests exist; no live v3 device validation or deployment evidence. |
| 58, 60 | Running/startup configuration capture, upload, view, real-time/scheduled capture | PARTIAL | Configuration version/capture APIs exist; secure device retrieval, registered vendor drivers, scheduler/startup capture and upload are not implemented. |
| 59 | Asset/change/alarm/availability/critical-link response reports | PARTIAL | Report and availability routes exist; complete tender report set and live correctness are unverified. |
| 61, 63 | Historical versions, baseline comparison, GUI diff and initiating-user traceability | COMPLETED | Version persistence/deduplication and diff/initiator logic are implemented in [config_backup_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/config_backup_routes.py#L33); regression tests are [test_configuration_versions.py](/home/agnigate/Desktop/NMS/hardik/tests/test_configuration_versions.py) and [test_configuration_diff.py](/home/agnigate/Desktop/NMS/hardik/tests/test_configuration_diff.py). |
| 62 | Compliance rules, reports, violations, remediation and history | PARTIAL | Rule evaluation, severity, recommendations and violation models exist; scheduled evaluation and complete remediation/history workflow are incomplete. |
| 64–69 | Service health, outage/RCA view, service catalog/ownership, SLA definitions/alarms/maintenance exclusion | PARTIAL | CMDB/business-service/availability/SLA foundations exist; full service catalog, SLA scheduler and live breach/impact workflow are not proven. |
| 70, 78 | Flow from non-SNMP devices; NetFlow v5/v9, J-Flow, IPFIX, sFlow, NetStream, sampled flows and all-flow retention | PARTIAL | Parsers normalize supported formats and bounded queue tests pass in [test_flow_ingestion.py](/home/agnigate/Desktop/NMS/hardik/tests/test_flow_ingestion.py); no mounted receiver/lifecycle/retention proof and no sampled-NetFlow guarantee. |
| 71–72 | Scheduled/custom service reports and out-of-box sensitivity policies | PARTIAL | Reporting/UI foundations exist; scheduled customizable service reports and policy defaults are not fully implemented. |
| 73–77 | Real-time end-to-end NMS, live exceptions, configurable polling speeds and network performance reports | PARTIAL | Existing SNMP scheduler/alerts/reports support the foundation; live exception, speed-profile and end-to-end operational proof is unavailable. |
| 79 | Automatic resource-utilization baselines | NOT IMPLEMENTED | No complete baseline engine was found. |
| 80–86 | Web transaction APM, user experience, HTTP error/user attribution, anomaly detection, location attribution and trends | NOT IMPLEMENTED | Current APM is aggregate metric ingestion/overview, not full transaction or real-user monitoring. |
| 87–92 | OS agents, thresholds/escalation, process/NT service restart and log-file monitoring | PARTIAL | Linux monitoring and Syslog foundations exist; agent fleet, Windows service restart, file-tail rules and full escalation workflow are absent. |
| 93–98 | Unified database/server/network view, centralized collection, database thresholds, virtual performance and RBAC | PARTIAL | Core overview, RBAC, Linux and virtualization foundations exist; database and virtual performance integrations are incomplete. |
| 99–108 | Helpdesk lifecycle, activity, assignment/escalation, knowledge/CMDB integration, remote desktop and dynamic workflows | PARTIAL | Incident CRUD/comments/audit, knowledge and CMDB links exist; remote desktop, full request management, dynamic workflow and automatic assignment/escalation are not implemented. |
| 109–114 | Knowledge promotion, incident categorization/priority, KeDB/CMDB, security communication, KPI and control evidence | PARTIAL | Knowledge/incident/RCA/CMDB foundations exist; promotion, security incident process, KPI review and documentary control evidence are not proven. |
| 115–127 | Change/configuration policy, RFC impact/risk/approval, CMDB integrity/audit, baselines, secure master copies and management corrective action | PARTIAL | Change/CMDB/version/compliance foundations and tests exist; policy governance, secure library/master-copy controls, management review and documentary evidence are incomplete. |
| Videowall section | 70-inch laser DLP videowall hardware, resolution, safety, IP6X, warranty and India installations | EXTERNAL EVIDENCE REQUIRED | This is procurement/hardware evidence, not an NMS software capability. Requires technical bid, certificates, warranty and installation/reference documents. |

## Completed Evidence Register

Only the following items are marked **COMPLETED**, and each has direct repository evidence:

| Item | Code evidence | Test/document evidence |
|---|---|---|
| 23 | Knowledge article CRUD/search/version/link routes and models: [knowledge_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/knowledge_routes.py#L47), [knowledge.py](/home/agnigate/Desktop/NMS/hardik/backend/models/knowledge.py#L9) | [test_knowledge_base.py](/home/agnigate/Desktop/NMS/hardik/tests/test_knowledge_base.py) |
| 61, 63 | Configuration version/diff APIs with line comparison and initiator fields: [config_backup_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/config_backup_routes.py#L29) | [test_configuration_versions.py](/home/agnigate/Desktop/NMS/hardik/tests/test_configuration_versions.py), [test_configuration_diff.py](/home/agnigate/Desktop/NMS/hardik/tests/test_configuration_diff.py) |

All other items are intentionally not marked COMPLETED because they require a broader workflow, live integration evidence, or external documents.

## Test and Runtime Boundary

The available focused validation passed **23 backend tests** and **16 frontend tests**, and the frontend production build passed. SNMP/collector unit coverage previously passed **292 tests**. These are not substitutes for live API, PostgreSQL, Redis, scheduler, real-device, receiver, browser E2E or customer acceptance evidence.

At audit time PostgreSQL (`127.0.0.1:5432`), Redis (`127.0.0.1:6379`), backend API (`127.0.0.1:8000`) and frontend dev server (`127.0.0.1:5173`) were unavailable. Therefore login/RBAC runtime, persistence, scheduler ownership, live SNMP, flow/Syslog ingestion, SLA timers and browser workflows remain unverified.

## External Evidence Register

The following must be supplied outside the code repository before tender submission or certification claims:

- two qualifying India deployments with monitored core devices;
- purchase orders, completion/signoff and customer references;
- OEM 24x7x365 TAC commitment and hardware replacement warranty;
- ISO 45001, ISO 27001/27034, CERT-In/CIS/OWASP/SANS, CMMI Level 3, Indian IPR/copyright and ITIL v4 Axelos Gold documents;
- supported-device/OEM compatibility statements and vendor adapter evidence;
- production HA, backup/restore, DR and real-device scalability acceptance records;
- videowall technical compliance, IP6X/laser-safety certificates, warranty and installation evidence.

No certification, deployment, warranty, purchase order, signoff or DR success is claimed by this matrix.

## Highest-Priority Gaps

1. Complete and wire the flow and Syslog receivers, retention and lifecycle startup.
2. Add real SNMP/QoS/BGP/virtualization integrations and vendor compatibility evidence.
3. Complete APM transaction/user-experience and database monitoring scope.
4. Finish ITSM service catalog, SLA timers, automatic correlation/escalation and control evidence.
5. Replace process-local poll protection with distributed per-device/module locking for HA.
6. Run authenticated live API/database/scheduler/receiver/browser tests and progressive real-device capacity validation.
