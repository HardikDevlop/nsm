# Baseline Test Results

Date: 2026-08-29
Repository: `/home/agnigate/Desktop/NMS`
Branch/commit observed: `29Aug` / `beb29b4`

## Scope

This report records the current NMS validation state without applying fixes.
No application behavior, API contract, model, migration, collector, OID, or
test was changed for this validation.

`PASS` means the requested check executed successfully.
`FAIL` means the test executed and exposed a failure.
`BLOCKED` means the test could not validate the behavior because a required
environment dependency was unavailable.
`UNTESTED` means no reliable runtime validation was possible in this run.

## Executive Result

| Area | Result | Evidence |
|---|---|---|
| Backend collector/SNMP unit tests | PASS | 292 passed |
| Frontend production build | PASS | Vite build completed successfully |
| Backend startup | BLOCKED | PostgreSQL at `127.0.0.1:5432` not responding |
| Backend API smoke tests | BLOCKED | Backend could not complete lifespan startup |
| Database-backed preservation tests | BLOCKED | PostgreSQL connection unavailable |
| SNMPv3 exploration tests | FAIL | 2 failed, 2 passed; stale `_auth()` expectation |
| Full 5,000-device scalability | UNTESTED | No load test executed |
| Live device polling | UNTESTED | No reachable backend/database/device session |

## Commands Executed

### Passing checks

```text
hardik/.venv/bin/python -m pytest hardik/tests/snmp hardik/tests/collectors -q
292 passed in 0.50s

npm run build
Vite production build completed successfully; 782 modules transformed.
```

### Blocked or failing checks

```text
hardik/.venv/bin/python -m pytest hardik/tests -q
Collection interrupted by:
ModuleNotFoundError: No module named 'hypothesis'

hardik/.venv/bin/python -m pytest hardik/backend -q
No tests ran in 0.04s

hardik/.venv/bin/python -m pytest hardik/tests/test_snmpv3_timeout_exploration.py -q
2 failed, 2 passed

hardik/.venv/bin/python -m pytest hardik/tests/test_soft_deleted_device_undelete.py -q
3 failed because PostgreSQL was unavailable

hardik/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
Application startup failed because PostgreSQL was unavailable
```

The standalone preservation scripts for ICMP, mixed discovery, and SNMPv2c
also attempted to run and failed at database setup with:

```text
psycopg.OperationalError: connection is bad: no error details available
```

The direct service probes also confirmed:

```text
127.0.0.1:5432 - no response
curl http://127.0.0.1:8000/api/v1/health -> connection refused
curl http://127.0.0.1:5173/ -> connection refused
```

## Requested Functionality Matrix

| Functionality | Result | What was verified |
|---|---|---|
| Login | BLOCKED | Route/code exists, but backend and database were unavailable |
| JWT authentication | BLOCKED | Static route/dependency exists; no live token flow |
| RBAC and permissions | BLOCKED | Protected routes exist; no live authorization flow |
| Device list and CRUD | BLOCKED | Routes/models/frontend exist; no PostgreSQL-backed API run |
| Device credentials | BLOCKED | Credential routes/models exist; no runtime persistence check |
| SNMP v2c | BLOCKED | Preservation tests could not initialize PostgreSQL |
| SNMP v3 | FAIL/BLOCKED | 2 exploration tests fail on `_auth()` expectation; live SNMP not tested |
| Discovery: ICMP | BLOCKED | Test reached database setup and stopped on PostgreSQL failure |
| Discovery: SNMP v2c | BLOCKED | Test reached database setup and stopped on PostgreSQL failure |
| Discovery: mixed protocol | BLOCKED | Test reached database setup and stopped on PostgreSQL failure |
| Discovery: other probes | UNTESTED | No live backend session |
| SNMP polling | UNTESTED | Scheduler/collector code inspected; no runtime poll |
| Monitoring scheduler | UNTESTED | Startup could not reach scheduler initialization |
| Monitoring latest/history persistence | BLOCKED | Requires PostgreSQL |
| Alerts and thresholds | BLOCKED | API/collector unit code covered; live persistence not tested |
| Events and notifications | BLOCKED | Requires running backend/database |
| Automatic topology | BLOCKED | Collector/API code covered statically; live topology not tested |
| Manual topology | BLOCKED | Requires running backend/database |
| Reports and daily reports | BLOCKED | Routes/frontend build verified; live report data not tested |
| Linux server monitoring | UNTESTED | No runtime backend/database validation |
| Frontend route compilation | PASS | Production Vite build succeeded |
| Frontend API behavior | UNTESTED | Frontend dev server was not running |
| API contract smoke test | BLOCKED | Backend could not start |
| 5,000-device scalability | UNTESTED | No load environment or test result available |

## Test Detail

### PASS: SNMP and collector unit coverage

Command:

```text
hardik/.venv/bin/python -m pytest hardik/tests/snmp hardik/tests/collectors -q
```

Result:

```text
292 passed in 0.50s
```

This covers collector response contracts, empty/unsupported behavior, CPU,
memory, interface, storage, VLAN, routing, ARP, LLDP, CDP, firewall, health,
OID registry, identity resolution, vendor detection, normalization, and
capability discovery tests present in those directories. It does not prove
live vendor/device compatibility or database persistence.

### PASS: Frontend production build

Command:

```text
npm run build
```

Result:

```text
✓ built in 609ms
782 modules transformed
```

This validates TypeScript/Vite module compilation and production bundling. It
does not validate browser API calls, login, routing against a running backend,
or live monitoring displays.

### FAIL: SNMPv3 exploration suite

Result:

```text
2 failed, 2 passed
```

The two failures call `SNMPClient._auth()`, but the current `SNMPClient` has no
such method. The tests therefore do not currently match the implementation's
public/internal shape. The suite also contains diagnostic logic that describes
the historical `privProtocol=None` issue. This result is recorded as a test
failure; no SNMPv3 fix was applied.

### BLOCKED: database-dependent preservation tests

The following tests could not reach their behavior assertions because they
connect to the configured PostgreSQL database during setup:

- `test_snmpv2c_preservation.py`.
- `test_icmp_preservation.py`.
- `test_mixed_protocol_preservation.py`.
- `test_soft_deleted_device_undelete.py`.
- `test_device_deletion_exploration.py`.

The configured local PostgreSQL service at `127.0.0.1:5432` was not
responding. These are environment-blocked results, not proof that the tested
application behavior is correct or incorrect.

### BLOCKED: backend startup and API validation

FastAPI startup reaches `backend.main` lifespan initialization and fails while
creating/verifying database tables because PostgreSQL is unavailable. As a
result, no live validation was possible for:

- Login and JWT token issuance.
- RBAC permission enforcement.
- Device CRUD and credentials.
- SNMP v2c/v3 API flows.
- Discovery and device import.
- Scheduled monitoring.
- Alerts, events, and notifications.
- Automatic/manual topology.
- Reports and exports.

## Untested Functionality

The following remain untested in this baseline run:

- Live SNMP v2c against a real device.
- Live SNMP v3 against a real device for auth-only and authPriv modes.
- Live OID/vendor interoperability.
- Scheduler execution and restart restoration.
- Latest/history database persistence under real polling.
- Alert creation, deduplication, acknowledge, and resolve through the API.
- Topology collection and reconciliation with real neighbors.
- Report contents and export downloads from live data.
- Linux SSH/SNMPv3 collection.
- Browser interaction and frontend-to-backend API integration.
- Load behavior, concurrency, retention, and 5,000-device scalability.
- HA, failover, backup, restore, and disaster recovery.

## Current Baseline Conclusion

The code-level SNMP/collector test surface and frontend build are passing. The
full NMS cannot currently be declared runtime-validated because PostgreSQL is
down and the backend therefore cannot start. The SNMPv3 exploration suite also
contains two implementation/test-shape failures that need to be reviewed
before using that suite as a reliable regression gate.

No fixes were applied in this validation run.
