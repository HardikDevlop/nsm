# Timezone Foundation Fix Report

## Result

The monitoring foundation now has shared aware-UTC creation helpers and the frontend shared parser no longer guesses unknown naive timestamps or manually adds `+05:30`. Existing database rows were not bulk-converted, as required.

## Files changed

- `hardik/backend/utils/time.py` — `utc_now()`, explicit legacy-aware normalization, UTC ISO serialization.
- `hardik/backend/services/snmp_polling.py` — scheduler/persistence calculations use aware UTC; known legacy naive scheduler values are treated as UTC only at the compatibility boundary.
- `hardik/backend/services/monitoring.py` — ICMP status/last-seen writes use aware UTC.
- `figma design/src/time.ts` — unknown naive strings are rejected; explicit-offset instants are formatted once in Asia/Kolkata.
- `figma design/src/pages/Dashboard.tsx` — removed manual `+05:30` conversion from clock/chart processing; charts retain epoch ordering.
- `figma design/tests/time-foundation.test.mjs` — focused parser/refetch/manual-offset tests.

## Canonical contract

- Internal calculations: **UTC aware**.
- New monitoring timestamps: **UTC**; existing PostgreSQL timestamp columns were not blindly migrated.
- API: explicit-offset ISO-8601 is required at the monitoring foundation boundary (`Z` preferred).
- Frontend: parse an explicit instant once, then display using `Asia/Kolkata`.
- Unknown legacy naive values are not silently guessed.

## Legacy DB classification / migration plan

| Affected area | Current evidence | Classification | Migrated |
|---|---|---|---|
| SNMP `MonitoringConfig` scheduling fields | Previously written by naive IST `now_ist()`; new writes are UTC-aware | `IST_NAIVE` historical / `UTC_AWARE` new | NO |
| SNMP latest/history `created_at` and `polled_at` | Model default previously stripped Asia/Kolkata tzinfo | `IST_NAIVE` historical / `UNKNOWN` where provenance is absent | NO |
| Device `last_seen` and status timestamps | Multiple UTC-naive writers | `UTC_NAIVE` where written by `datetime.utcnow()`; otherwise `UNKNOWN_LEGACY` | NO |
| ICMP sample timestamps | Collector emits aware UTC ISO-8601 | `UTC_AWARE` | N/A |

Before any data migration, export and classify rows using writer/version provenance, compare against deployment timezone, then convert only confirmed `IST_NAIVE` rows to UTC. Unknown rows must remain flagged for operator resolution.

## Required summary

- MANUAL `+05:30` CONVERSIONS: **0 in the fixed shared monitoring paths; 0 remaining in `figma design/src` after this change**
- NAIVE/UTC COMPARISONS IN SNMP/ICMP: **0 in the fixed scheduler/status paths; legacy DB values are normalized only with an explicit compatibility semantic**
- LEGACY DATA MIGRATED: **NO**
- REFETCH TIME SHIFT: **FIXED in shared formatter / focused test; full browser runtime proof pending**
- CHART ORDER: **PASS** for the Dashboard path (epoch timestamps; invalid/unknown naive values skipped)
- BACKEND TESTS: **PASS** for `python3 -m py_compile` on changed backend modules; full backend suite not available in this workspace
- FRONTEND BUILD: **PASS** (`npm run build`)
- FOCUSED TIMEZONE TEST: **PASS** (`node --test tests/time-foundation.test.mjs`)
- FULL FRONTEND REGRESSION SUITE: **FAIL**, 17 pre-existing unrelated regression tests failed; 10 passed. The suite was not used as evidence of timezone correctness.
- RUNTIME DB→API→UI PROOF: **PENDING** (no live NMS process/database/browser session available)
- TIMEZONE FOUNDATION: **PARTIAL**

## Remaining limitations

Many unrelated CRUD/incident/knowledge modules still use legacy `datetime.utcnow()` and several pages still call `new Date()` directly. They were intentionally not broadly refactored because this step is limited to the SNMP/ICMP monitoring foundation and must not alter unrelated behavior. Device status/stale-status semantics were not changed.

