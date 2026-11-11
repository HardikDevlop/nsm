# Test Coverage and Verification

Static counts: 321 backend test files under `hardik` (excluding the vendored test virtual environment) and 61 frontend Node tests under `figma design/tests`. Tests were not executed per the audit rules.

## Evidence by area

- Windows: focused CIM, WinRM diagnostics, CA trust, disk, process, sensor, task-manager and migration tests.
- Frontend regressions: dashboard, availability, device monitoring, SNMP/topology, flow, APM/RCA/ITSM, syslog/configuration and extensive Windows UI tests.
- Backend smoke/API artifacts: `backend_smoke_test.py`, `unified_smoke_test.py`, `MONITORING_API_TESTING.md`, Postman collections.
- Core domains: test files exist across discovery, monitoring, auth/RBAC, reports and feature-specific areas; exact coverage percentages are not available.

## Verification boundary

Repository test presence is not execution evidence. Historical reports or generated artifacts were not treated as current results. No tests, build, import check, migration, service, network connection, or database query was run during this audit.

