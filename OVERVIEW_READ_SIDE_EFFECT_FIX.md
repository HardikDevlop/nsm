# Overview Read Side-Effect Fix

Removed the Dashboard-only automatic scheduler recovery from `Dashboard.tsx`.

Dashboard loading now performs exactly one `getOverview(hours)` request per load. The conditional `POST /monitoring/polling/start` and its second Overview GET were removed. The existing 30-second refresh interval and range-change behavior remain unchanged. If the backend reports the scheduler stopped, the returned service state remains available to the existing Dashboard presentation; no running state is fabricated.

`startPollingService` remains in `figma design/src/lib/api.ts`; source search found no other consumers, but the helper was not deleted because this task explicitly preserves the API helper.

No backend, database, scheduler, Redis, SNMP, ICMP, KPI, traffic, layout, or styling changes were made.

DASHBOARD AUTO START REMOVED: YES
DASHBOARD START POLLING REFERENCE REMAINS: NO
READ PATH MUTATION REMAINS: NO
CONDITIONAL SECOND OVERVIEW GET REMOVED: YES

INITIAL LOAD OVERVIEW GET COUNT: 1
HEALTHY REFRESH MUTATION COUNT: 0
STOPPED REFRESH MUTATION COUNT: 0
STOPPED STATE STILL DISPLAYED: YES

30 SECOND REFRESH PRESERVED: YES
RANGE REFRESH PRESERVED: YES
START POLLING API HELPER DELETED: NO
OTHER START POLLING CONSUMERS PRESERVED: YES

BACKEND CHANGED: NO
DATABASE CHANGED: NO
SCHEDULER CHANGED: NO
REDIS CHANGED: NO
SNMP CHANGED: NO
ICMP CHANGED: NO
POLLING KPI CHANGED: NO
TRAFFIC LOGIC CHANGED: NO
DASHBOARD UI/STYLING CHANGED: NO

FRONTEND TYPE CHECK: PASS via production build
FRONTEND BUILD: PASS
SAFE FOR FINAL BROWSER ACCEPTANCE: YES
