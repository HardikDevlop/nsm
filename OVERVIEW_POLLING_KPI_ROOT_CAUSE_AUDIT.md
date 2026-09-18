# Overview Polling KPI Root-Cause Audit

Read-only source audit. No code, database, frontend, scheduler, Redis, SNMP, or ICMP state was changed.

## Overview contract and flow

`GET /api/v1/overview` is implemented by `hardik/backend/api/overview_routes.py:get_overview()`. It loads `PollingHistory` rows into `polling_rows`, using the requested `hours` window, and constructs the KPI under:

```text
response.normalized.polling
```

The backend does not expose this KPI as a top-level `response.polling` key. The normalized object is nested under the top-level `normalized` key.

The current flow is:

```text
PollingHistory
  -> get_overview() polling_rows query
  -> _classify_polling_rows()
  -> response.normalized.polling
  -> Dashboard.tsx n = data.normalized
  -> n.polling.successful_attempts / failed_attempts / other fields
```

The builder returns counts for successful, unsupported, no-data, failed, and unknown attempts; total attempts; success rate; last outcome timestamps; compatibility fields; and configured job counts. The frontend type in `figma design/src/lib/api.ts` matches this nested shape, and Dashboard reads `n?.polling`.

## Classification semantics

`_classify_polling_rows()` classifies:

- `success` → `successful_attempts`;
- `not_supported` and `oid_not_supported` → `unsupported_attempts`;
- `no_data` → `no_data_attempts`;
- `timeout`, `authentication_failed`, `device_unreachable`, and `error` → `failed_attempts`;
- any unrecognized status → `unknown_attempts`.

`total_attempts` is the sum of all five categories. The historical success-rate denominator is only `successful_attempts + failed_attempts`, so unsupported, no-data, and unknown outcomes do not become genuine polling failures or eligible success-rate attempts. Compatibility `success` and `failure` map to successful and genuine failed attempts.

## Why `{}` can be observed

The current source does construct a non-empty `normalized.polling` object whenever `get_overview()` reaches the aggregation block. There is no intentional `{}` assignment in the backend KPI builder, and the frontend does not read a top-level `polling` key. Therefore an observed `polling={}` is not explained by the current aggregation logic alone.

The most likely contract issue is inspecting `response.polling` instead of `response.normalized.polling`, or an older/cached response shape from before the KPI fields were added. The overview endpoint has Redis cache key `nms:overview:v1:hours:{hours}` and a process-local 10-second cache; a previously cached payload can temporarily preserve an older shape. The frontend API cache also has a 30-second cache layer, but its Dashboard code reads `normalized.polling`.

The exact backend path has no aggregation exception swallowing: query/aggregation exceptions would cause the endpoint request to fail rather than return `{}`. The service-state helper has an exception guard, but it does not construct polling KPI data. No wrong device/config scope is used for the KPI query; it intentionally counts all PollingHistory rows in the time window, not only currently enabled devices.

## Time semantics

The query boundary is:

```python
since_24h = datetime.utcnow() - timedelta(hours=hours)
PollingHistory.created_at >= since_24h
```

The boundary is naive UTC. Scheduler `PollingHistory` timestamps are generated with aware UTC and persisted into a legacy timezone-naive DateTime column, so the database representation is semantically naive UTC. At the SQL comparison level, current scheduler rows and the naive UTC boundary are compatible.

However, historical writers/model defaults in this project have also produced naive IST values. Those historical rows can be excluded or included incorrectly by the naive-UTC boundary. This is a real time-window data-coverage risk, but it would yield zero/partial classification counts, not an empty dictionary, because `_classify_polling_rows([])` returns a populated zero-valued result. The current source’s newer scheduler rows should be queryable in the requested window.

## Read-only host verification

Codex has no live systemd/database access, so runtime counts were not queried. Run this exact read-only command on the host to verify the source rows and normalized statuses for the same window:

```bash
psql "$DATABASE_URL" -x -c "SELECT COALESCE(NULLIF(lower(trim(status)), ''), '<null>') AS normalized_status, COUNT(*) AS count, MIN(created_at) AS oldest, MAX(created_at) AS newest FROM polling_history WHERE created_at >= (CURRENT_TIMESTAMP AT TIME ZONE 'UTC') - INTERVAL '24 hours' GROUP BY 1 ORDER BY 1;"
```

Also inspect the actual response path, not a guessed top-level key:

```bash
curl -sS -H "Authorization: Bearer $TOKEN" "$API_BASE/api/v1/overview?hours=24" | jq '.normalized.polling, .polling'
```

The first expression is the contract used by Dashboard; the second should normally be null/absent under the current backend contract.

## Conclusion

The source currently implements a real PollingHistory query and aggregation. The backend KPI shape is nested at `normalized.polling`, while Dashboard consumes that same nested path. An observed literal `{}` most likely indicates a wrong response-path inspection or stale cached/older response, not that the current builder intentionally returns an empty object. A separate historical timestamp-semantic risk can affect the 24-hour row set, but cannot by itself turn the current populated builder into `{}`.

OVERVIEW KPI RESPONSE PATH: `response.normalized.polling`
KPI BUILDER: `get_overview()` via `_classify_polling_rows(polling_rows)`
POLLING HISTORY SOURCE: `PollingHistory` rows selected by `created_at >= datetime.utcnow() - timedelta(hours=hours)`
EXPECTED KPI SHAPE: Object containing `successful_attempts`, `unsupported_attempts`, `no_data_attempts`, `failed_attempts`, `unknown_attempts`, `total_attempts`, `success_rate`, last-outcome fields, and compatibility fields

REAL DATA QUERY IMPLEMENTED: YES
TIME WINDOW FILTER: `PollingHistory.created_at >= datetime.utcnow() - timedelta(hours=hours)`, default 24 hours
POLLING HISTORY STORAGE SEMANTIC: Scheduler rows are legacy naive DateTime values semantically representing UTC; historical writers may contain naive IST values
TIMEZONE CONTRACT CONSISTENT: NO

SUCCESS CLASSIFICATION: `success` → successful/eligible attempt
FAILURE CLASSIFICATION: timeout/authentication_failed/device_unreachable/error → genuine failure
NOT_SUPPORTED CLASSIFICATION: unsupported, excluded from failure and success-rate denominator
NO_DATA CLASSIFICATION: excluded from failure and success-rate denominator
ELIGIBLE DENOMINATOR: successful attempts + genuine failed attempts

BACKEND RETURNS EMPTY KPI BECAUSE: Not proven from source; current builder returns a populated zero-shaped object, so literal `{}` most likely reflects wrong path (`response.polling`) or stale/older cached response
FRONTEND CONTRACT MATCHES BACKEND: YES
ROOT CAUSE: Response-path/cache mismatch is the source-supported explanation; live response verification is required to distinguish it from deployment/version drift

DATABASE MODIFIED: NO
CODE MODIFIED: NO
FRONTEND MODIFIED: NO
SCHEDULER MODIFIED: NO
REDIS MODIFIED: NO
SNMP MODIFIED: NO
ICMP MODIFIED: NO

RUNTIME/DB EVIDENCE AVAILABLE: NO
HOST VERIFICATION REQUIRED: YES
SAFE FOR SURGICAL FIX: YES
