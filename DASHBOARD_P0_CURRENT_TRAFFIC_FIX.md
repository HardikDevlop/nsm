# Dashboard P0.2 — Current Interface / Traffic Real-Data Authority

## Existing storage semantics

`LatestInterface` is intended as a current snapshot table, not a historical table:

- Table: `latest_interface`
- Identity: `device_id + interface_id`
- Existing constraint: `uq_latest_interface_device_interface`
- Measurement timestamp: `polled_at`
- Stable row tie-breaker: inherited row `id`
- Historical samples remain in `interface_statistics` and were not changed.

The SNMP polling writer updates an existing `LatestInterface` row for the canonical `Interface` record, or creates it when absent. It separately inserts `InterfaceStatistic` history rows. No writer, schema, or existing database row was changed.

## Implemented read authority

The `/overview` current-interface read now:

1. Fetches current interface rows in one bulk query.
2. Orders by `polled_at DESC, id DESC`.
3. Deduplicates defensively by `(device_id, interface_id)` without merging names or inventing interfaces.
4. Uses the existing configured `MonitoringConfig` interval for module `interfaces`.
5. Applies the established `3 × configured interval` freshness convention.
6. Returns per-row `freshness`, `freshness_age_seconds`, `freshness_interval_seconds`, and normalized UTC `polled_at`.
7. Excludes stale/missing rows from current aggregate traffic.

Current aggregate semantics:

- A genuine measured `0` remains `0.0`.
- NULL RX/TX remains NULL.
- RX and TX are aggregated independently, so missing TX is not reported as zero.
- If no fresh measurement exists for a direction, that aggregate is NULL and the frontend renders `N/A`.
- Fresh interface coverage and total selected interface count are included.

Historical `traffic_history` and `InterfaceStatistic` behavior was not changed.

## Frontend scope

Only current/live traffic presentation was changed. Dashboard live RX/TX cards and throughput bars now retain nullable values and render `N/A` when the API has no fresh value. Genuine zero remains displayable as `0.0 Kbps`/equivalent. Historical chart processing remains unchanged.

## Files changed

- `hardik/backend/api/overview_routes.py`
  - Added deterministic current-interface selection and timestamp normalization.
  - Added configured-interval freshness classification.
  - Added NULL-preserving current traffic aggregation.
- `figma design/src/pages/Dashboard.tsx`
  - Removed missing-current-traffic coercion to zero from live traffic cards/bars and related live radar input.
- `hardik/tests/test_dashboard_current_traffic.py`
  - Added focused selection, tie-break, stale, NULL, zero, and multi-interface tests.

## Tests and validation

- Python compile validation passed for changed backend code and focused tests.
- Frontend production build passed: `npm run build`.
- Relevant existing frontend tests passed: cache and time-foundation tests.
- Focused backend tests were added but could not be executed because `pytest` is unavailable in the environment.
- No live PostgreSQL/API query was performed; runtime freshness and actual duplicate-row counts remain pending.

## Explicit non-changes

- ICMP unchanged.
- SNMP collector/writer unchanged.
- Health semantics unchanged.
- Scheduler, topology, alerts/events, polling KPI history, and systemd unchanged.
- Historical traffic logic unchanged.
- No database rows deleted or rewritten.
- No mock/static/random data added.

CURRENT INTERFACE AUTHORITY: PASS
ONE ROW PER DEVICE/INTERFACE READ: YES
DETERMINISTIC LATEST SELECTION: YES
STALE TRAFFIC EXCLUDED FROM CURRENT TOTALS: YES
MISSING TRAFFIC PRESERVED AS NULL: YES
HISTORICAL TRAFFIC CHANGED: NO
DB ROWS DELETED/REWRITTEN: NO
RUNTIME VERIFICATION: PENDING
SAFE TO PROCEED TO P0 POLLING KPI FIX: YES
