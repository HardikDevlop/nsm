# Documentation Gap Analysis

## Scope and method

Compared the existing `01`–`13` audit files and HLD with current repository source on 2026-11-04. Inspection was static only; no tests, imports, migrations, services, database queries, network operations or runtime OpenAPI generation were performed. Existing worktree changes were treated as current source evidence and were not modified.

| Original documented claim | Current source evidence | Path / symbol | Discrepancy | Documentation correction | Verification |
|---|---|---|---|---|---|
| 435 routes across 26 modules | Router registration includes core, discovery, SNMP, topology, monitoring, feature, Linux, Windows and helper routers; route decorators include the current modified helper API | `hardik/backend/main.py` `app.include_router`; `backend/windows_monitoring/helper_api.py` `router` | Inventory can become stale as untracked routes are added | Treat counts as audit-date counts and regenerate from source per release | Static confirmed; runtime unverified |
| Windows monitoring is implemented | Windows API, CIM/WinRM, snapshots, processes, trust, diagnostics and helper files exist; several are user-modified/untracked | `hardik/backend/windows_monitoring/api.py`, `cim.py`, `helper_api.py`, `application_helper.py` | Earlier docs understate current helper/sensor scope | Include helper credential/submission and hardware/application evidence, but do not infer device compatibility | Static confirmed; runtime unverified |
| Remote collectors are partial | No separate collector process/package or collector router was found; flow/syslog are local receivers and scheduler lease is process-local | `main.py` lifespan; `backend/flow/*`; `backend/syslog/*` | Claim is directionally correct but collector terminology is ambiguous | State that distributed remote collector deployment is not source-verified | Static confirmed |
| Deployment supports systemd | Requirements/start scripts contain systemd command references, but no unit file was found | `hardik/backend/requirements.txt`, `hardik/start_*.sh` | Documentation conflates instructions with deployable artifact | Describe systemd as documented intent only | Static confirmed |
| Site isolation is implemented | Core dependencies and several routes call `can_access_site`; route coverage is not uniform by static global claim | `hardik/backend/dependencies.py`, `monitoring_data_routes.py`, `remote_access_routes.py` | Earlier security wording was too broad | Report endpoint-family coverage and unresolved legacy/feature paths | Static partial; runtime unverified |
| Tests count proves coverage | Test files exist, but tests were not executed and no coverage report is current evidence | `hardik/tests`, `figma design/tests` | Presence was correctly caveated but should not be read as pass evidence | Separate inventory, historical artifacts and execution results | Static confirmed; execution unavailable |
| API inventory is complete | Existing `08` is family/count-based, not endpoint/schema/permission-complete | all `hardik/backend/api/*` | Incomplete inventory | Use `16_API_PERMISSION_MATRIX.md` as the source-indexed supplement; regenerate on route changes | Static confirmed |
| Database schema is verified | Models and migrations are present; live DB state was not inspected | `backend/models/*`, `backend/database/migrations.py` | Earlier docs correctly caveat this, but catalog must distinguish model vs migration | Use `18_DATABASE_RELATIONSHIP_CATALOG.md` | Static confirmed |

## Material inconsistencies

1. The existing audit describes a 26-module/435-route snapshot, while current untracked Windows helper files show ongoing changes. Counts are therefore time-bound.
2. `main.py` uses both `Base.metadata.create_all` and custom migrations; documentation must not call this a conventional migration-only deployment.
3. `flow_enabled` and `syslog_enabled` default to false, so source support does not imply active listeners.
4. The frontend has permission guards, while backend permission requirements vary from centralized `require_permission` to explicit permission checks and some legacy/core patterns; UI permission is not a substitute for API authorization.

