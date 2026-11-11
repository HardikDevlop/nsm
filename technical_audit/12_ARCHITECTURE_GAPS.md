# Architecture Gaps and Technical Risks

| Severity | Area | Evidence/impact | Recommended action |
|---|---|---|---|
| High | Secrets/config | Development settings contain placeholder/default secret/database values | Require deployment-time secret injection and fail-fast validation for all environments |
| High | Schema lifecycle | Startup combines `create_all` and custom migrations | Establish one versioned migration authority and test upgrade/rollback paths |
| High | Runtime verification | Large surface is source-present but no current runtime/test execution was authorized | Add controlled CI/API integration evidence and publish versioned verification reports |
| Medium | Deployment | No checked-in Docker/Nginx/systemd artifact; only scripts/docs references | Define reproducible production packaging, service units, TLS termination and health checks |
| Medium | Data growth | SNMP/syslog retention defaults are zero/disabled; history tables are broad | Define retention, partitions/rollups, indexes and capacity alarms |
| Medium | Process coupling | Polling, receivers, reports and remote sessions share backend lifecycle | Separate failure domains or document capacity/HA limits |
| Medium | API surface | 435 route declarations and legacy router coexist | Generate OpenAPI inventory, deprecate duplicates, enforce consistent dependency policy |
| Medium | Site isolation | Helpers exist, but every feature/resource path was not proven scoped | Perform endpoint-level tenant/site authorization review and tests |
| Medium | Protocol security | Telnet adapter exists | Restrict by policy and prioritize SSH/WinRM/HTTPS alternatives |
| Low | Frontend API access | Most calls use `lib/api.ts`, but some feature components use direct fetch | Consolidate client behavior, error handling, auth and caching |
| Low | Documentation | Feature docs, generated reports and code can diverge | Treat source/OpenAPI/schema evidence as release artifacts |

