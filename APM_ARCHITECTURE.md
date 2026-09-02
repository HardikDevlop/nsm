# NMS APM Architecture

## 1. Purpose and Boundaries

This document defines an additive Application Performance Monitoring (APM)
module for the existing NMS. The architecture was created before
implementation; the metric-ingestion foundation described below is now
implemented without changing SNMP collector, OID, discovery, scheduler,
existing API or UI behavior.

APM remains separate from SNMP collection:

- SNMP continues to provide device, interface, platform and network telemetry.
- APM receives application telemetry from instrumented applications, agents or
  an OpenTelemetry-compatible gateway.
- Correlation uses existing NMS `device_id`, site and service identity; APM
  does not create a second device inventory.
- Existing JWT/RBAC, PostgreSQL, alerts, reports and API conventions remain
  the integration boundaries.

The first implementation should be additive and production-safe. It must not
require an application to expose SNMP credentials or change existing polling.

## 2. Goals and Non-Goals

### Goals

- Model applications, services, transactions, response times, errors and
  dependencies in a normalized form.
- Accept traces, spans, metrics and structured errors through a bounded,
  cancellable ingestion pipeline.
- Correlate application services with existing NMS devices, interfaces and
  sites when identity is known, while retaining unresolved telemetry for later
  mapping.
- Provide efficient time-window queries for service health, latency, error
  rate, throughput and dependency views.
- Reuse existing alert, report, observability and RBAC patterns without making
  APM data part of SNMP polling.

### Non-goals

- Replacing SNMP v2c/v3, discovery, monitoring scheduler, topology or flow
  ingestion.
- Implementing browser UI in the architecture phase.
- Supporting unlimited raw payload retention or unbounded in-memory queues.
- Guessing vendor-specific or application-specific fields that cannot be
  normalized safely.

## 3. Existing NMS Integration Points

The module should fit the current project rather than introduce a parallel
application architecture:

```text
APM SDK / OTel Collector / Agent
        |
        v
APM ingest API or OTLP gateway
        |
bounded queue + parser/normalizer
        |
APM storage and rollups  ----->  existing PostgreSQL
        |                                  |
        +--> service/device resolver       +--> existing Device, Interface, Site
        |
        +--> APM read APIs --> alerts / reports / future UI
```

The resolver reads existing inventory records and must not create duplicate
devices. A service may be linked to a device, site, or multiple candidate
devices. Ambiguous mappings are recorded as unresolved rather than silently
assigned.

## 4. Domain Model

### 4.1 `apm_applications`

Represents a deployable or business-facing application.

- `id`, `organization_id`, `name`, `slug`, `environment`
- `team`, `version`, `owner`, `enabled`
- `created_at`, `updated_at`, `deleted_at`

Unique identity should be scoped to organization, name, environment and slug.
Soft deletion follows the existing inventory convention.

### 4.2 `apm_services`

Represents a runtime component such as an API, worker, database adapter or
message consumer.

- `id`, `application_id`, `name`, `service_key`
- `runtime`, `language`, `version`, `environment`
- optional `device_id` and `site_id` for infrastructure correlation
- `enabled`, `created_at`, `updated_at`, `deleted_at`

`service_key` is the stable telemetry identity. `device_id` is nullable because
containers, serverless workloads and external services may not map to one NMS
device.

### 4.3 `apm_transactions`

Represents a normalized operation or route observed for a service.

- `id`, `service_id`, `name`, `operation_type`
- normalized route/template, not unbounded raw URLs
- `status`, `created_at`, `updated_at`

Transaction identity should use a route template or operation name. Raw query
parameters and secrets must never become a transaction key.

### 4.4 `apm_spans`

Append-oriented trace/span facts used for latency and dependency analysis.

- trace and span IDs, parent span ID
- application, service and transaction IDs when resolved
- start/end timestamps and duration in microseconds
- status, kind, peer service, peer host and optional `device_id`
- sampled flag, trace flags, attributes/resource attributes JSON
- receive timestamp and bounded `record_hash` for idempotency

Attribute values need size and key-count limits. Sensitive headers, tokens,
credentials and payload bodies are excluded by default and redacted before
storage.

### 4.5 `apm_errors`

Normalized error events, linked to a span or transaction where available.

- service/application/transaction IDs
- timestamp, error type, normalized message fingerprint
- status code, handled flag, trace/span IDs
- stack trace only when configured and redacted
- occurrence count in rollups and bounded raw evidence

The stable fingerprint should not include request IDs, user data or dynamic
values.

### 4.6 `apm_dependencies`

Observed service-to-service, service-to-database, service-to-cache or
service-to-external dependency edges.

- caller service ID and target identity/name
- resolved target service ID when known
- dependency type and protocol
- optional target `device_id`/`site_id`
- first seen, last seen, call count, error count, bytes where available

Edges are derived from spans and upserted into a bounded identity table. Raw
span facts remain the source of truth.

### 4.7 Rollups

Time-bucketed tables should hold derived aggregates rather than replacing raw
facts:

- `apm_service_rollups_1m` and `apm_service_rollups_5m`
- `apm_transaction_rollups_5m`
- `apm_dependency_rollups_5m`
- `apm_error_rollups_5m`

Each rollup includes request count, error count, duration count, sum, min,
max, and histogram/quantile-friendly buckets. p50/p95/p99 should be computed
from a bounded histogram or t-digest-compatible representation, not by loading
all raw durations into an API request.

## 5. Common Telemetry Schema

All supported inputs are normalized to an internal `NormalizedAPMEvent`:

```text
event_type: span | error | metric
received_at: UTC timestamp
observed_at: UTC timestamp
application_key: string
service_key: string
transaction_key: optional string
trace_id: optional string
span_id: optional string
parent_span_id: optional string
duration_us: optional non-negative integer
status: optional string
error_fingerprint: optional string
peer_service: optional string
peer_host: optional string
device_id: optional integer
site_id: optional integer
attributes: bounded JSON object
source: otlp | agent | api
record_hash: stable deduplication key
```

Required validation includes timestamp sanity, maximum event size, bounded
attribute keys/values, valid IDs, non-negative duration and a supported event
type. Invalid events are counted and sent to a bounded dead-letter/evidence
path; one malformed event must not stop ingestion.

## 6. Ingestion and Processing

```text
HTTP/OTLP receiver
  -> authentication and tenant limits
  -> bounded receive queue
  -> decoder (OTLP/JSON initially)
  -> normalizer and redaction
  -> identity resolver
  -> bounded batch writer
  -> raw facts + rollups + dependency upserts
```

### Receiver

- Prefer an OpenTelemetry Collector deployment for production fan-in; the NMS
  can expose a narrow authenticated ingestion endpoint for controlled agents.
- Apply request body, batch size, exporter and tenant limits before parsing.
- Never hold a database connection while reading or decoding a request.
- Require a per-tenant ingest token or mTLS at the deployment boundary; do not
  reuse device SNMP credentials.

### Queue and writer

- Use separate bounded queues for accepted events and database batches.
- Keep parser concurrency and writer concurrency configurable and finite.
- Flush by batch size or short interval in one transaction per bounded batch.
- Use PostgreSQL bulk inserts/upserts; avoid one commit per span/error.
- On full queues, return an explicit backpressure response where possible and
  increment dropped-event counters. Never allocate unbounded memory.
- Graceful shutdown stops receivers, cancels parsing, drains a bounded number
  of batches, commits successful batches, then closes the writer.

No request handler or scheduled job should call `asyncio.run()`. The existing
application-managed async lifecycle owns APM workers, just as it owns other
long-running services.

## 7. Device and Service Correlation

Resolution order:

1. Explicit configured `service_key` and application/environment.
2. Existing service mapping for exporter resource attributes.
3. Explicit `device_id` supplied by a trusted collector integration.
4. Existing device identity by hostname/IP/site when the match is unique.
5. Leave the event unresolved with a reason when no safe match exists.

APM must not infer a device from an arbitrary peer IP if multiple devices,
NAT, proxies or load balancers make the mapping ambiguous. Mapping changes are
auditable and must not rewrite historical raw telemetry.

SNMP metrics can enrich an APM service view through `device_id` and interface
links, but SNMP polling never waits on APM ingestion. APM availability must
not affect discovery or monitoring scheduler execution.

## 8. Storage, Retention and Privacy

Use additive SQLAlchemy models and an application-managed migration. Do not
change existing SNMP, flow or device tables beyond optional foreign-key
references that are proven safe.

Recommended retention tiers, configurable per organization/site:

- Raw spans: short operational window.
- Raw errors: longer than spans when required for incident investigation.
- Service/transaction/dependency rollups: medium to long term.
- Application/service mappings and audit records: longest practical window.

Prefer time partitions and bounded partition drops for large raw tables. A
retention worker must run in bounded transactions and record duration/failure.
It must not compete with the receive loop for an unbounded lock.

Privacy controls are mandatory:

- redact authorization headers, cookies, tokens, secrets and configured PII
  keys before persistence;
- do not store request/response bodies by default;
- hash or normalize error messages containing dynamic identifiers;
- restrict raw attribute access with RBAC and audit administrative access.

## 9. APIs and Permissions

Additive routes should live under `/api/v1/apm` and follow existing FastAPI
dependency and response conventions. Existing API contracts remain unchanged.

### Read APIs

- `GET /api/v1/apm/overview`
- `GET /api/v1/apm/applications`
- `GET /api/v1/apm/applications/{id}/services`
- `GET /api/v1/apm/services/{id}/transactions`
- `GET /api/v1/apm/services/{id}/latency`
- `GET /api/v1/apm/services/{id}/errors`
- `GET /api/v1/apm/dependencies`
- `GET /api/v1/apm/traces/{trace_id}`
- `GET /api/v1/apm/ingestion/status`

All time-series routes require bounded `from`, `to`, bucket and page-size
parameters. Filters should include application, service, environment, site,
device, transaction and status where relevant. Responses should expose
`data_quality` counts for unresolved mappings, dropped events and parse errors.

### Administrative APIs

- application/service registration and mapping;
- ingestion token/endpoint configuration;
- retention and sampling configuration;
- explicit replay/rebuild of rollups by authorized operators.

Suggested permissions are `apm:read`, `apm:ingest`, `apm:manage` and
`apm:raw:read`. The final codes must be added through the existing RBAC seed
and migration/compatibility path, with least privilege as the default.

## 10. Alerts, Reports and Topology Correlation

APM alert rules should be evaluated from rollups, not by scanning raw spans in
each request. Initial rule families:

- error-rate threshold;
- p95/p99 latency threshold;
- request-throughput anomaly;
- dependency failure rate;
- service health degradation.

Alert events retain application/service/transaction IDs and optional existing
`device_id`/`site_id`. Existing alert delivery remains the delivery mechanism;
APM adds facts and rule metadata rather than a second notification system.

Reports can query rollups with the same time, device and site filters used by
existing reports. Topology can show an optional service/dependency overlay,
but SNMP network topology remains authoritative for network links. APM edges
must be marked as observed application dependencies, not physical links.

## 11. Scheduler Integration

APM background work is limited to:

- batch writing;
- rollup materialization;
- retention;
- mapping refresh;
- alert evaluation.

These jobs must be registered in the existing application-managed scheduler,
have stable job IDs, and be safe to restart without duplicate workers. A
single-flight guard should prevent duplicate rollup/retention work per scope,
while different applications/sites can proceed independently. Persisted
monitoring jobs and SNMP polling intervals remain untouched.

## 12. Observability and Capacity Controls

Important APM APIs and workers should emit the existing observability fields:

- `request_id`, `total_ms`, `db_ms`, `query_count`;
- queue depth, accepted/dropped events and batch size;
- parse, redaction, resolution and persistence errors;
- rollup lag and scheduler backlog;
- raw/rollup retention duration.

Metrics must distinguish exporter/agent failure from database backpressure.
Never log raw credentials, tokens, full attributes or request bodies.

Capacity validation should use simulated telemetry only in a dedicated test
environment and measure p50/p95/p99 API latency, ingestion throughput, queue
depth, database connections and rollup lag. Production code must not be
modified to fake load-test results.

## 13. Implementation Sequence

1. Confirm retention, privacy, tenant and ingestion authentication policy.
2. Add schemas/models and an idempotent migration for application/service
   identity and raw APM facts.
3. Implement pure normalizer/redaction and parser tests with no live agents.
4. Implement bounded ingestion and bulk persistence tests, including malformed
   events, cancellation, duplicate delivery and backpressure.
5. Add rollups, query plans and read-only APIs with RBAC and pagination tests.
6. Add scheduler registration, restart and single-flight tests.
7. Integrate alert/report/topology correlation behind additive feature flags.
8. Build UI only after API contracts, retention behavior and regression tests
   are stable.

## 14. Risks and Decisions Required Before Coding

- Whether the NMS itself accepts OTLP or an external collector is mandatory.
- Tenant isolation and ingestion authentication model.
- Raw span/error retention and PII redaction policy.
- Sampling policy and whether unsampled errors are always retained.
- Container/Kubernetes identity mapping to existing devices and sites.
- PostgreSQL partitioning/rollup strategy based on expected event volume.
- Whether topology should display APM edges by default or only on demand.

Until these decisions are confirmed, implementation should remain behind
additive routes and configuration and must not alter existing NMS behavior.
