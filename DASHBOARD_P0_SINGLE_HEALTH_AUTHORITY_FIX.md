# Dashboard P0.1 — Single Health Authority Fix

## Change

`GET /api/v1/dashboard/summary` now derives every device state through the existing `derive_device_health()` contract. It returns additive `health_counts` for `online`, `offline`, `degraded`, `stale`, and `unknown`; legacy `online_devices` and `offline_devices` remain and are derived from those counts.

Only non-deleted devices contribute to `total_devices`.

The Sidebar no longer falls back to `/snmp/devices` or raw `status` values. If `/dashboard/summary` fails, it retains only the clearly marked sessionStorage last-known summary while loading, and displays `Health unavailable` when no usable summary exists.

`Dashboard.tsx` continues to use `/overview` and its existing derived `health_counts`; no duplicate health algorithm was added.

## Files changed

- `hardik/backend/api/routes.py`
  - Added shared summary counting through `derive_device_health()`.
  - Changed `/dashboard/summary` online/offline counts to derived counts.
  - Added `health_counts` response data.
- `hardik/backend/schemas/nms.py`
  - Added `health_counts: dict[str, int]` to `DashboardSummary`.
- `figma design/src/lib/api.ts`
  - Added the typed `health_counts` response field.
- `figma design/src/components/Sidebar.tsx`
  - Removed raw `/snmp/devices` health fallback.
  - Added fresh/stale/unavailable summary presentation.
- `hardik/tests/test_dashboard_health_authority.py`
  - Added focused derived-count and Sidebar raw-fallback assertions.

## Authority behavior

Old authority:

- `/overview`: derived health.
- `/dashboard/summary`: raw `Device.status`.
- Sidebar fallback: raw SNMP-device `status`.

New authority:

- `/overview`: existing `derive_device_health()` contract.
- `/dashboard/summary`: same `derive_device_health()` contract.
- Sidebar: `/dashboard/summary` only; cached values are explicitly stale last-known state, never a second calculation authority.

The backend does not write or mutate `Device.status`, and `derive_device_health()` semantics were not changed.

## API response compatibility

Existing fields remain:

- `total_devices`
- `online_devices`
- `offline_devices`
- `active_alerts`
- `critical_alerts`
- `recent_events`

Added:

```json
{
  "health_counts": {
    "online": 0,
    "offline": 0,
    "degraded": 0,
    "stale": 0,
    "unknown": 0
  }
}
```

The total of `health_counts` equals the eligible non-deleted device count.

## Tests and validation

- Focused Python test added for raw-status contradiction, stale/failed evidence, all derived states, and total-count conservation.
- Focused static Sidebar assertion passed: no `/snmp/devices` raw-status fallback remains.
- Python syntax validation passed for changed backend files.
- Frontend production build passed: `npm run build`.
- Existing frontend suite was run; 12 passed and 16 unrelated existing suites failed in the current workspace.
- `pytest` could not be executed because `pytest` is not installed in the environment.

No runtime DB/API verification was performed in this change.

SINGLE HEALTH AUTHORITY: PASS
RAW Device.status DASHBOARD AUTHORITY: NO
SIDEBAR RAW STATUS FALLBACK: NO
DERIVED HEALTH SEMANTICS CHANGED: NO
SAFE TO PROCEED TO P0 TRAFFIC FIX: YES
