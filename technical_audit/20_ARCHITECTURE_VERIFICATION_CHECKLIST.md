# Architecture Verification Checklist

| Area | Static evidence | Runtime validation still required | Result |
|---|---|---|---|
| Router mounts and endpoint count | `main.py`, all `api/*`, Windows/Linux APIs | live OpenAPI and smoke requests | Static complete / runtime pending |
| Request/response contracts | Pydantic classes and function signatures | response serialization and validation | Static partial / runtime pending |
| Authentication/RBAC | `dependencies.py`, auth modules, route dependencies | 401/403 matrix with seeded roles | Static confirmed / runtime pending |
| Site isolation | `can_access_site`, router checks, selected endpoint guards | cross-site positive/negative tests for every family | Static partial / runtime pending |
| Database design | models/FKs/migrations | live schema diff, indexes, constraints, row counts | Static confirmed / runtime pending |
| Scheduler startup | `main.py` lifespan and scheduler modules | startup under production config, lease behavior | Static confirmed / runtime pending |
| SNMP/ICMP/OS polling | adapters and collectors | device-compatible polling with safe fixtures | Static confirmed / runtime pending |
| Windows PC/server support | WinRM/CIM classes, native sensor/helper code, tests | Windows editions, namespaces, permissions and returned values | Static partial / runtime pending |
| Alert lifecycle | threshold/alerting/incident services | duplicate/recovery/email behavior over time | Static partial / runtime pending |
| Reports/email | report services/settings | generated files, SMTP delivery and schedule execution | Static confirmed / runtime pending |
| Flow/syslog | receivers/settings | enabled listener bind and ingestion | Static confirmed / runtime pending |
| WebSocket remote access | route/session manager/frontend | authenticated terminal session and restart reconciliation | Static confirmed / runtime pending |
| Deployment | scripts/settings/requirements | actual service units, proxy, TLS, backup/restore | Static partial / runtime pending |
| HLD consistency | HLD compared to `01`–`20` | release-level architecture review | Corrections documented |

## Priority order

1. Validate security/site isolation and endpoint contracts.
2. Validate startup/migrations/scheduler behavior in a disposable environment.
3. Validate Windows compatibility across PC/server editions and native sensor availability.
4. Validate alert deduplication, recovery, notifications and report scheduling.
5. Validate deployment artifacts, TLS, backups and HA/collector behavior.

