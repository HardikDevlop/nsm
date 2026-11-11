# Database Model and Relationship Catalog

## Catalog basis

Models were read from `hardik/backend/models`, `backend/windows_monitoring/models.py`, `backend/linux_monitoring/models.py`, and `backend/flow/models.py`; migration references were read from `backend/database/migrations.py` and current `migrate_0075.py`. This is intended/model-plus-migration evidence, not live schema evidence.

| Domain | Tables/models | Key relationships | Migration evidence |
|---|---|---|---|
| Identity/tenancy | users, roles, permissions, organizations, sites, user_sites, user_sessions | users→roles; users↔sites; devices→sites/organizations | `migrations.py` identity/session sections |
| Inventory | devices, vendors, device_types, interfaces, credentials, identity/capabilities/products/OUI | device→site/org/type/vendor; interfaces→devices; credentials→devices | metadata models plus migration tables |
| Monitoring | monitoring_jobs, device_metrics, thresholds, alerts, events, notifications, status history | metrics/alerts/events→device; thresholds→device/metric domains | `migrations.py` monitoring sections |
| SNMP | device inventory/credential/performance/statistic/latest/history/trap/OID/vendor/interface tables | device-keyed records; interface/device relationships | imported model metadata and SNMP migrations |
| Windows | system/metric snapshots, events, thresholds, notification states, metric history, process snapshots/items, CA bundles/assignments | Windows records→devices; process items→snapshots; CA assignments→devices/bundles | `migrations.py` Windows section; `migrate_0075.py` helper tables |
| Linux | Linux servers, metrics/history/security/threshold tables | server/device/site relationships | Linux models and migrations |
| Flow/syslog | flow_records, sflow_counter_samples, syslog_records, correlation_rules | records→devices/interfaces/alerts/incidents where defined | migration entries around flow/syslog |
| Reports | report_schedules, generated_reports, report data | generated report→schedule | migration report section |
| ITSM | incidents/alerts/comments/attachments/history/SLA; problems; changes/history/link tables | incident/problem/change links to devices/users and each other | migration ITSM sections |
| CMDB/APM/RCA | CI types/items/relationships/history; applications/services/dependencies/metrics; RCA incidents/evidence | CI→device/interface/site/app/user; RCA evidence→alerts/events/CIs | migration sections and model FKs |
| Knowledge | articles/versions/history/feedback and incident/problem/change/CI/device/service/related links | link tables→target domain entities | migration knowledge section |

## Explicit FK examples

`RemoteAccessCredential.device_id → devices.id`, `SSHHostKey.device_id → devices.id`, `RemoteAccessSession.user_id/device_id/credential_id` are defined in `models/remote_access.py`. `RCAEvidence` links to RCA incident, alert, event and CMDB relationship in `models/rca.py`. `ConfigurationItem` links to organization, device, interface, site and APM application in `models/cmdb.py`. These demonstrate the catalog’s relationship pattern; live constraints/indexes still require database inspection.

