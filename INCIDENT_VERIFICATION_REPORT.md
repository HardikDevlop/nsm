# Incident Management Verification Report

## 1. Executive classification

| Area | Classification | Finding |
|---|---|---|
| Incident schema and persistence | PASS | Incident and child tables/models are registered and persisted. |
| Manual incident creation | PASS | `POST /api/v1/incidents` creates durable incidents. |
| Automatic creation from API-created alerts | PARTIAL | The alert-create route invokes the incident service only for open/acknowledged critical/high alerts. |
| Automatic creation from monitoring alerts | NOT WIRED | Realtime, SNMP threshold, and interface alert producers do not invoke the incident service. |
| Automatic creation from events/status history | NOT WIRED | No event/status-to-Incident path or event foreign key exists. |
| Alert linkage | PARTIAL | Explicit alert IDs and the narrow API-create hook are supported; current monitoring alerts are not linked. |
| Deduplication/correlation | PARTIAL | Existing alert link and a 15-minute device/category correlation query exist, but no incident identity key or concurrency guarantee exists. |
| Assignment | PARTIAL | User assignment is supported; no team/ownership model or assignment history exists. |
| Acknowledgement | NOT WIRED | Incident acknowledgement is absent; only source alerts can be acknowledged. |
| SLA timers | PARTIAL | Policy/timer logic exists, but no real policies are persisted and no independent worker exists. |
| Escalation | PARTIAL | Evaluation can create an alert, but only when a timer is evaluated; it is not independently scheduled. |
| Resolution/closure | PARTIAL | Manual PATCH supports `resolved` and `closed`; alert recovery does not update incidents. |
| Reopen | PARTIAL | PATCH can move a closed incident to an open state, but there is no explicit reopen action or lifecycle event. |
| Audit/history | PARTIAL | Generic AuditLog and SLA history exist; there is no dedicated incident status/assignment history table. |
| Frontend wiring | PASS | The Incident page uses real Incident APIs and renders persisted records. |
| Real-data readiness | PARTIAL | Real qualifying alerts exist, but the current persisted Incident set is unrelated to them. |

## 2. Current architecture

The module consists of:

- SQLAlchemy models in `hardik/backend/models/incident.py`.
- Application-managed migrations `20260829_0016_incident_management` and `20260829_0017_incident_sla`.
- FastAPI routes in `hardik/backend/api/incident_routes.py`, mounted at `/api/v1/incidents`.
- Alert correlation helper in `hardik/backend/incidents/service.py`.
- SLA policy/timer evaluation in `hardik/backend/incidents/sla.py`.
- A React page in `figma design/src/pages/IncidentManagement.tsx` and API functions in `figma design/src/lib/api.ts`.
- The core alert POST route calls `create_incident_from_alert()` after committing an API-created alert. Monitoring alert producers call the alerting helpers directly and do not use that route.

## 3. Real data-flow diagram

```text
Realtime ICMP / SNMP polling / alerting helpers
        |
        +--> alerts (persisted)
        |       |
        |       +--> API-created alert route only --> create_incident_from_alert()
        |                                                |
        |                                                +--> incidents
        |                                                +--> incident_alerts
        |
        +--> device_status_history / events (persisted)
                |
                +--> no Incident creation path

incidents + incident_alerts + SLA tables
        --> /api/v1/incidents
        --> IncidentManagement.tsx
```

## 4. Models and tables

`incidents` contains `id`, title, description, category, priority, status, `assigned_to`, `created_by`, optional RCA and APM service references, `closed_at`, `created_at`, and `updated_at`.

`incident_alerts` links incidents to alerts with a foreign key and unique `(incident_id, alert_id)`. There is no `event_id`, `device_id`, interface ID, or direct topology relationship on the managed Incident model. Device context is available only indirectly through linked Alert rows; service context is an optional `apm_services` foreign key.

Child tables are `incident_comments` and `incident_attachments`.

SLA tables are `incident_sla_configs`, `incident_sla_timers` (one timer per incident), and `incident_sla_history`. Timer fields include start/deadlines, first response, resolved time, pause state/duration, breach flags, escalation flag, and update time.

## 5. Existing incident records

Read-only live API evidence from `/api/v1/incidents?skip=0&limit=100`:

| ID | Title | Category | Priority | Status | Assigned | Alert IDs | Created |
|---:|---|---|---|---|---|---|---|
| 2 | Manual incident | availability | p1 | closed | none | none | 2026-08-31 10:56:38 |
| 1 | Manual incident | availability | p1 | closed | none | none | 2026-08-29 10:29:31 |

Both detail responses contain empty alert, comment, attachment, SLA, and SLA-history collections. The live SLA policy endpoint returns `[]`.

This is `EMPTY-BUT-WORKING` for the persisted Incident store, not evidence that source alerts are absent.

## 6. Alert/Event -> Incident creation

### Alerts

`create_incident_from_alert()` accepts only non-deleted alerts whose status is `open` or `acknowledged` and whose severity is `critical` or `high`. It creates an `open` Incident, links the source alert, and writes a generic `AuditLog` action. Existing linked alerts are reused. An active incident for the same device and derived category within the preceding 15 minutes is reused and the new alert is linked.

The only caller is the normal `POST /api/v1/alerts` route, after `alert_crud.create()` and an initial commit. The realtime offline alert helper, SNMP `create_threshold_alert()` path, and other monitoring producers persist alerts directly. They do not call the Incident service. Therefore existing monitoring-generated alerts cannot currently create managed Incidents automatically.

### Events and status transitions

`events` and `device_status_history` have no Incident foreign key or service call. The existing event endpoint is CRUD-only. Recovery/status transitions do not create, resolve, or update managed Incidents.

### Real source cases

Live read-only API evidence:

- Device-down alert `506`: device `157`, critical, title `Device Down: device-192-168-100-97`, status `open`, no acknowledgement or resolution, created `2026-08-27 18:15:56`. No managed Incident is linked.
- Device 115 has open critical SNMP interface-down alerts `445` through `469`; examples include alert `469`, `Interface Down: TenGigabitEthernet4`, created `2026-08-27 12:19:25`, and alert `468`, `TenGigabitEthernet3`. No managed Incident is linked.
- Device 115 is `online` with persisted status-history transitions, but those transitions have no Incident path.
- The only returned event is event `136`, `SNMP_DISCOVERY` for device `116`; it has no Incident linkage.

Classification: `NOT WIRED` for monitoring/event automation and `PARTIAL` for API-created alert automation.

## 7. Deduplication and correlation

For one alert, the service first searches for an Incident already linked to that exact alert. Repeated processing therefore reuses the Incident and the unique child constraint prevents a duplicate link.

For a new alert, it searches active `open`, `investigating`, or `pending` Incidents with the same derived category and a linked alert for the same device created within 15 minutes. This is a heuristic correlation, not a durable incident key. It does not correlate events, interfaces as separate entities, topology, sites, or service impact. There is no database uniqueness constraint preventing concurrent creation of two otherwise equivalent Incidents.

## 8. Severity and priority mapping

For automatic alert creation, category is derived from title/description:

- CPU, memory, latency, storage, or capacity -> `performance`
- security, attack, firewall, or unauthorized -> `security`
- interface, link, offline, down, or reachability -> `availability`
- otherwise -> `other`

Severity-to-priority mapping is:

| Alert severity | Incident priority |
|---|---|
| critical | p1 |
| high | p2 |
| medium | p3 |
| warning | p3 |
| low | p4 |
| unknown/unmapped | p3 |

Manual creation accepts p1 through p5 and permits the caller to choose category and priority. Device criticality, site criticality, interface state, and service criticality do not alter priority.

## 9. Status lifecycle

The actual API values are `open`, `investigating`, `pending`, `resolved`, and `closed`. The API validates only membership in this set; it does not enforce transition ordering. There is no `new`, `acknowledged`, or `in_progress` Incident status.

The create path starts at `open`. PATCH can set any allowed status. Moving to `resolved` or `closed` sets `closed_at`; moving back to an active status clears `closed_at`. No `resolved_at` column exists on `incidents`; the SLA timer has a separate `resolved_at`.

Incident acknowledgement is not implemented. Alert acknowledgement is separate through `/api/v1/alerts/{id}/acknowledge` and does not change the Incident.

## 10. Assignment workflow

`assigned_to` is an optional foreign key to `users.id`. Manual creation and Incident PATCH accept a user ID. The frontend exposes a numeric Assignee ID field. There is no team/group ownership, validation that a selected user is active, assignment endpoint, or assignment-history table. Unassigned Incidents are supported.

Classification: `PARTIAL`.

## 11. SLA behavior

Policies can be created for a priority and optional APM service, with response and resolution targets, pause states, optional escalation delay/user, and enabled state. Service-specific policy is preferred, then a priority-only policy.

A timer starts from `incident.created_at`. On Incident creation, `start_timer()` is called. However, the automatic alert service does not call `start_timer()` when it creates an Incident. Detail retrieval calls `timer_view()`, which evaluates and may lazily start a timer if a policy exists.

Only `pending` is an accepted pause state. `investigating`, `resolved`, and `closed` mark first response; resolved/closed mark the timer resolved. Breaches and escalation are evaluated during timer evaluation, not by a dedicated background worker. Breach/escalation creates a new high alert. No SLA policies or timers are currently present in the live data, so SLA is presently unavailable for the two existing Incidents.

Classification: `PARTIAL` in code, `EMPTY-BUT-WORKING` in current persisted data, and `NOT WIRED` for independent scheduled evaluation.

## 12. Resolution, closure, and reopen behavior

Only manual Incident PATCH changes status. The frontend exposes a `Close incident` action, which sends `status=closed`; it does not expose a resolve or acknowledge action. Alert resolve endpoints update only the Alert's `status` and `resolved_at`. No alert recovery, device recovery, or event recovery updates the Incident.

Reopening is technically possible by PATCHing an active status after closure, which clears `closed_at`, but there is no explicit reopen endpoint, reopen reason, or dedicated reopen audit action.

Classification: `PARTIAL`.

## 13. Audit and history

Creation, update, comments, attachments, and SLA policy/timer actions create generic `AuditLog` or `IncidentSLAHistory` rows. Incident detail returns comments, attachments, and SLA history.

There is no dedicated immutable Incident status history, assignment history, acknowledgement timestamp, resolution timestamp, transition actor/reason, or alert recovery history. The existing two Incidents have no comments, attachments, or SLA history.

Classification: `PARTIAL`.

## 14. Frontend wiring

`IncidentManagement.tsx` uses `listIncidents()`, `getManagedIncident()`, `createIncident()`, `updateIncident()`, and `addIncidentComment()` from `lib/api.ts`. It is protected by `incidents:read`; create, update, and comment controls are permission-gated.

The page renders persisted Incident ID/title, category, priority, status, assignee, linked alerts, comments, attachments, and SLA deadlines/breach state when an SLA exists. It supports selecting a real Incident and loading its detail, manual creation, comments, and closing.

It has an empty-state message for no persisted Incidents. It does not display a linked device/service field directly beyond the alert list, does not expose acknowledgement/resolution/reopen controls, has no incident-history view, and has no polling loop. The list uses a maximum of 100 by default and the detail query is one request per selected ID.

Classification: `PASS` for current API wiring, `PARTIAL` for full lifecycle presentation.

## 15. Real-device applicability

Device 115 is represented by real persisted device data and real open critical SNMP interface-down alerts. Those alerts are suitable inputs for the existing alert correlation helper, but they are not currently linked to any managed Incident because they were produced by SNMP polling rather than the API alert-creation route.

The device-down alert for device 157 has the same gap. No existing managed Incident can be used to verify alert-to-Incident persistence or recovery propagation from the current database.

Classification: `PARTIAL` for potential API-created alert input; `NOT WIRED` for the actual monitoring paths.

## 16. Performance risks

- Incident list serialization performs separate link, alert, comment, and attachment queries per Incident, creating an N+1 pattern.
- Incident detail performs additional child queries and invokes SLA evaluation, which may write SLA history and new breach/escalation Alerts during a GET.
- Incident list accepts up to 500 records; there is no eager-loading/batched child serialization.
- Frontend performs one list request and one detail request per selected Incident, with no polling loop; it disables refetch-on-mount and window focus refetching.
- Alert correlation uses indexed child alert/device/time concepts but has no durable correlation key or concurrency-safe incident creation lock.
- Monitoring-generated alerts are deduplicated at the alert title/device level by alerting helpers, but that does not deduplicate managed Incidents because those producers bypass Incident creation.

## 17. Exact missing pieces

1. A trusted integration point from realtime ICMP, SNMP/interface alert, and other persisted alert producers into managed Incident creation.
2. Event and device-status transition linkage, including persisted event evidence if required.
3. Automatic recovery handling that resolves or updates linked Incidents when source alerts recover.
4. A durable incident correlation key/constraint covering device/interface/service and active fault identity, with concurrency-safe creation.
5. Explicit Incident acknowledgement and lifecycle transition validation.
6. Dedicated `acknowledged_at`, `resolved_at`, transition actor/reason, and assignment history fields/tables.
7. Team ownership and active-user validation for assignment.
8. A dedicated SLA worker/scheduler or other reliable trigger for timers, breaches, and escalation.
9. Automatic SLA timer initialization for Incidents created by the alert service.
10. Frontend actions and views for resolve, acknowledge, reopen, status history, device/service context, and real linked source evidence.
11. Batched/eager-loaded list serialization for scale.

## 18. Minimum implementation required

The minimum production path is to invoke one Availability/Incident-owned alert-to-Incident adapter from every existing real alert persistence path, while leaving source alert behavior unchanged. The adapter should use a durable correlation key and unique constraint, link the source Alert, map the existing severity/category values, initialize an applicable SLA timer, and atomically persist the Incident/link.

Add a recovery adapter driven by existing alert resolution/status changes to update linked Incident state without fabricating data. Add event/status evidence links only if the product requires event-originated Incidents. Add validated lifecycle timestamps/history and assignment history, then expose the supported actions in the existing frontend. Finally, add an independent SLA evaluation trigger and batch child loading for list responses.

No implementation changes were made during this verification.
