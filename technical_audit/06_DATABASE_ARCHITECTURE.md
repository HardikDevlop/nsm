# Database Architecture

## Engine and schema management

SQLAlchemy 2 targets PostgreSQL through `psycopg`. `database/session.py` configures a pooled engine (pool size 20, max overflow 20, pre-ping, recycle 1800 seconds). `main.py` invokes metadata creation and custom idempotent migrations at startup. This is intended schema evidence, not confirmation of the live database.

## Logical model groups

- Identity/tenancy: users, roles, permissions, organizations, sites, user-site assignments, sessions.
- Inventory: devices, device types, vendors, credentials, interfaces.
- Monitoring: jobs, metrics, thresholds, alerts, events, notifications, status history.
- SNMP: device inventory/credentials, performance/statistics, interfaces, traps, OID/vendor/capability data, latest-value tables and polling history.
- Windows/Linux: system/metric snapshots, history, processes/events/thresholds; Linux server and security/threshold records; Windows CA bundles/assignments and helper submissions.
- Operations: reports/schedules/generated reports, audit logs, configuration backups/compliance, availability, QoS, BGP, syslog, flow/sFlow.
- ITSM/knowledge: incidents/SLA, problems, changes, RCA, CMDB, APM, knowledge articles/versions/links/feedback.

Migrations explicitly show tables for flow, sFlow, APM, CMDB, RCA, incidents, problems, changes, knowledge, availability, virtualization, QoS, BGP, syslog, reports, sessions, Windows snapshots/events/history and Linux thresholds. Foreign-key relationships generally connect devices/sites/users and use cascade or set-null behavior as appropriate.

## Data movement

Protocol adapters produce normalized observations; services write current snapshots/history and evaluate thresholds; alerts/notifications and dashboards read persisted records. Retention is configurable for selected domains, but defaults such as `snmp_history_retention_days=0` and `syslog_retention_days=0` indicate cleanup is disabled/proposal-only by default. Live row counts, indexes in the deployed database, and actual retention jobs are **UNVERIFIED**.

