# Dashboard P0 Polling KPI Fix

Implemented only the Dashboard polling KPI semantics fix.

The overview now classifies persisted `PollingHistory` rows into successful, unsupported, no-data, genuine failed, and unknown attempts. Unsupported and no-data outcomes are not failures. Success rate is calculated only as successful attempts divided by successful plus genuine failed attempts, and is null when that denominator is zero. Last-outcome timestamps are selected deterministically by `created_at DESC, id DESC`.

Legacy `success`, `failure`, `active_jobs`, and `collector_failures` fields remain for compatibility; they now map to truthful semantics. Enabled MonitoringConfig count is also exposed as configured/enabled polling jobs and is presented with a non-active-job label.

The Dashboard polling panel uses the new fields and displays `N/A` when no eligible success-rate attempts exist. No collector, scheduler, health, traffic, topology, alert, event, or historical row behavior was changed. PollingHistory rows were not modified.

Tests added: `hardik/tests/test_dashboard_polling_kpi.py`.

Validation: Python compile validation and frontend build are required after this change; live runtime verification was not performed.

POLLING KPI SEMANTICS: PASS
UNSUPPORTED COUNTED AS FAILURE: NO
NO_DATA COUNTED AS FAILURE: NO
UNKNOWN COUNTED AS FAILURE: NO
SUCCESS RATE EXCLUDES NON-FAILURE OUTCOMES: YES
CURRENT HEALTH KEPT SEPARATE: YES
HISTORICAL ROWS MODIFIED: NO
DETERMINISTIC LAST OUTCOME: YES
RUNTIME VERIFICATION: PENDING
DASHBOARD P0 SOURCE FIXES COMPLETE: NO
SAFE TO START LIVE DASHBOARD VERIFICATION: YES
