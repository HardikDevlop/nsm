# RCA Verification Report

## 1. Executive Classification

Overall RCA classification: **PARTIAL**.

| Area | Classification | Finding |
|---|---|---|
| RCA tables/models | PASS | `rca_incidents` and `rca_evidence` are modeled and persisted. |
| RCA API | PASS | Analyze, list, and detail routes are registered under `/api/v1/rca`. |
| Alert-window analysis | PASS | Real persisted alerts are read and correlated on demand. |
| Incident -> RCA linkage | NOT WIRED | RCA does not load `Incident` or `IncidentAlert`; automatic Incident creation does not trigger RCA. |
| Alert -> RCA linkage | PARTIAL | Alerts are stored as RCA evidence, but only through the manual/request analysis path. |
| Device context | PASS | Alert-linked devices and device hostnames are used. |
| Interface context | PASS | Interface names are inferred from persisted `interfaces` rows and alert text. |
| CMDB context | PARTIAL | CMDB CIs and relationships are read, but this is not a complete NMS topology/evidence model. |
| Topology reasoning | PARTIAL | Only persisted CMDB relationships can affect scoring; no topology/LLDP/CDP source is read directly. |
| Metrics/status/history evidence | NOT WIRED | Device status history, metrics, SNMP history, and monitoring history are not read by RCA. |
| Event correlation | NOT WIRED | `Event` is imported in the engine but never queried or emitted as evidence. |
| Root-cause confidence | PARTIAL | Deterministic heuristic score, not probabilistic or ML inference. |
| Recommendations/actions | NOT WIRED | No recommendation or remediation output exists. |
| RCA history | PARTIAL | Current result and evidence are persisted, but no analysis-version/history records exist. |
| Frontend | PARTIAL | Uses real RCA APIs and data, but only supports alert-window analysis, not selecting a real Incident. |
| Core-switch Device-Down applicability | NOT WIRED | The automatic Device-Down Incident exists, but it is not linked to RCA and was not automatically analyzed. |

## 2. Current Architecture

RCA consists of:

- `RCAIncident`: persisted root candidate, confidence, impact summary, and time window.
- `RCAEvidence`: persisted alert or relationship evidence attached to an RCA result.
- `correlate_alerts()`: loads a bounded time window of non-deleted alerts, enriches them with devices/interfaces/CMDB, runs the heuristic, and persists the result.
- `/api/v1/rca/analyze`: manual/request-triggered analysis endpoint.
- `/api/v1/rca/incidents` and `/api/v1/rca/incidents/{id}`: persisted result list/detail endpoints.
- `RCA.tsx`: real API list/detail/analyze page.

There is no RCA worker, startup hook, scheduler hook, or Incident-created callback.

## 3. Data Flow

```text
Persisted alerts
    -> optional alert_ids and selected time window
    -> alert/device/interface/CMDB relationship enrichment
    -> 5-minute alert grouping and heuristic candidate scoring
    -> RCAIncident + RCAEvidence PostgreSQL rows
    -> RCA API serialization
    -> RCA.tsx list/detail display
```

The requested Incident path is not present:

```text
Incident -> IncidentAlert -> linked Alert -> RCA
                                      X
                         no automatic adapter/callback
```

## 4. RCA Database Models/Tables

### `rca_incidents`

Defined in [models/rca.py](/home/agnigate/Desktop/NMS/hardik/backend/models/rca.py) and created by migration `20260829_0015_rca` in [migrations.py](/home/agnigate/Desktop/NMS/hardik/backend/database/migrations.py).

Fields include:

- unique `correlation_key`
- `root_kind`, `root_label`
- nullable `root_device_id`, `root_interface_id`, `root_ci_id`
- non-null `confidence`
- `impact_summary`
- `window_start`, `window_end`
- `created_at`, `updated_at`

### `rca_evidence`

Evidence has:

- `incident_id` foreign key to `rca_incidents`
- nullable `alert_id` foreign key to `alerts`
- nullable `event_id` foreign key to `events`
- nullable `relationship_id` foreign key to `cmdb_ci_relationships`
- `evidence_type`, `score`, `reason`, optional JSON `payload`, `created_at`
- unique constraint over `(incident_id, evidence_type, alert_id, relationship_id)`

The schema permits event evidence, but the current engine never creates it.

## 5. Real Source Data Used

| Existing source | Code reads it? | How it is used |
|---|---:|---|
| `alerts` | Yes | Filters non-deleted alerts by `created_at`, severity, title, device, and optional IDs. |
| `devices` | Yes | Uses `alert.device` to obtain hostname and device context. |
| `interfaces` | Yes | Queries all interfaces for each alert device and matches interface name in title/description. |
| `cmdb_configuration_items` | Yes | Loads all active CIs and maps by `device_id` and `interface_id`. |
| `cmdb_ci_relationships` | Yes | Loads all active relationships and uses their source/target CI IDs in scoring/evidence. |
| `events` | No | Imported in `engine.py`, but never queried and never persisted as RCA evidence. |
| `incidents` | No | RCA has no Incident query or incident ID field. |
| `incident_alerts` | No | RCA does not traverse Incident -> IncidentAlert -> Alert. |
| `device_status_history` | No | No query or status evidence. |
| `device_metrics` | No | No query or metric evidence. |
| SNMP polling history | No | No polling-history query. Interface-down alerts are consumed only as alert rows. |
| LLDP/CDP relationships | No direct query | Only a pre-existing CMDB relationship can influence RCA; LLDP/CDP is not read directly. |
| monitoring history | No | No monitoring coverage or observation query. |

## 6. Incident -> RCA Path

The automatic Incident adapter creates and links Incident records to qualifying alerts, but it does not call `correlate_alerts()`. The RCA engine starts with:

```python
db.query(Alert).filter(
    Alert.deleted_at.is_(None),
    Alert.created_at >= start,
    Alert.created_at <= end,
)
```

The Incident model has nullable `rca_incident_id`, and the Incident PATCH route can set it after validating that an RCA row exists. This is a manual linkage mechanism, not automatic analysis or automatic linkage.

### Real persisted Device-Down case

The current database contains an automatically created Core-switch incident:

- Incident `8`: `CRITICAL incident: Device Down: Core-switch`
- status: `resolved`
- correlation key: `device:115:availability:device_down`
- linked alert: `513`
- alert title: `Device Down: Core-switch`
- alert device: `115`
- device: `Core-switch`, `192.168.100.2`
- alert created: `2026-08-31T17:26:09.572388`
- alert resolved: `2026-08-31T12:48:55.835111`
- Incident `rca_incident_id`: `null`

Therefore this real automatically created Device-Down Incident is not available through an Incident-aware RCA path. At verification time the runtime analysis endpoint used `datetime.utcnow()` as its upper bound; the persisted alert timestamp was later than that bound, so the current time-window query would also exclude it unless the timestamps are normalized or the record becomes eligible by the actual runtime clock. This is an evidence/time-data limitation, not proof of a root cause.

## 7. Alert Correlation

`POST /api/v1/rca/analyze` accepts:

- `hours`: 1 to 720, default 1
- optional `alert_ids`, maximum 500

The API computes `end = datetime.utcnow()` and passes `[end - hours, end]` to the engine. If IDs are provided, they are added to the same time-window query; they do not bypass the window.

The engine sorts matching alerts by creation time and groups only alerts whose timestamp is within 300 seconds of the earliest alert in the selected set. The persisted correlation key is a hash of grouped alert IDs plus the minute-normalized grouping start. Repeating the same logical grouping can update the same RCA row.

The existing real RCA row `1` contains 25 persisted alerts (`445` through `469`) from `2026-08-27T12:15:06.904950` through `2026-08-27T12:19:25.286787`, a 4-minute-18-second burst. It was persisted as:

- root kind: `ci`
- root label: `GigabitEthernet2`
- root device: `115`
- root interface: `579`
- root CI: `12`
- confidence: `0.7`
- impact summary: `24 downstream/correlated alert(s) potentially impacted`

This is an older interface-alert RCA result, not an RCA result linked to the automatic Device-Down Incident.

## 8. Device, Interface, and Metric Evidence

Device enrichment is real and works for the alert row. The persisted device endpoint confirms:

- device `115`: `Core-switch`
- IP: `192.168.100.2`
- MAC: `98:A8:78:00:CF:3B`
- status: `online`
- monitoring status: `true`
- last seen: `2026-08-31T12:41:06.310919`

RCA uses the device hostname only for candidate labeling. It does not use the device’s status, last-seen timestamp, uptime/downtime values, status transitions, metrics, or SNMP observations to validate a root cause.

For interfaces, `_infer_interface()` performs a per-alert query of all interfaces for the alert’s device and matches the persisted interface name against alert title/description. This is why the real RCA result could identify interface `579`/`GigabitEthernet2`.

## 9. Topology Usage

The engine reads active `CIRelationship` rows and builds directed source-to-target adjacency. For a CI candidate, it adds up to `0.6` score for reachable outgoing targets at `0.12` each. It also records a relationship evidence item when a relationship touches the selected root CI.

This is CMDB relationship usage, not direct topology discovery. The current real relationship read for CI `12` returned:

- relationship `2`
- type `contains`
- source CI `1`
- target CI `12`
- `managed_by`: `nms_reconciliation`
- `source_key`: `contains:1:12`

No direct topology-link, LLDP, or CDP record was read by RCA in this verification. The algorithm does not query topology tables or topology services and does not prove an upstream router/switch failure from downstream device alerts. Its `outgoing` traversal can reward a candidate with downstream relationships, but it does not establish causal direction from real network observations.

## 10. Root-Cause Algorithm

For each grouped alert, RCA chooses a candidate in this order:

1. Interface-linked CI, if the inferred interface maps to a CI.
2. Device-linked CI, if the alert device maps to a CI.
3. Persisted interface candidate.
4. Persisted device candidate.
5. `Unmapped service` when no device context exists.

Candidate score is:

```text
max severity score among related alerts
+ max(0, 1 - earliest_related_alert_offset / 300) * 0.4
+ min(reachable outgoing CI count * 0.12, 0.6)
```

Severity scores are hardcoded deterministic weights:

```text
critical 1.0, high 0.8, warning/medium 0.5,
low 0.25, info 0.1, unknown 0.3
```

The maximum-scoring candidate becomes the probable root. Impacted alert IDs are grouped alerts other than the first alert found for the selected root device.

This is a transparent heuristic based mainly on alert timing, severity, device/interface identity, CMDB mapping, and CMDB relationship count. It is not AI/ML inference and does not consume status, metric, event, polling, or monitoring evidence.

## 11. Confidence Calculation

Confidence is exactly:

```text
min(0.99, max(0.10, selected_candidate_score / 2))
```

It is rounded to four decimal places before persistence. It is not calibrated against historical outcomes, evidence completeness, alert recovery, or a probability of correctness. The real stored RCA `1` confidence `0.7` is the persisted heuristic output.

## 12. Persistence and History

Analysis persists an RCA row and commits it in `correlate_alerts()`. The correlation hash allows an equivalent grouped alert set to update the existing RCA row rather than create a second row.

Evidence behavior is incomplete:

- Evidence is inserted only when the RCA row has no evidence.
- If a later recalculation changes the grouped alerts or relationships but the row already has evidence, old evidence is not reconciled or removed.
- `event_id` is supported by the table but remains null for current generated evidence.
- There is no RCA analysis history/version table, actor, input snapshot, or change audit trail. `created_at` and `updated_at` only identify row creation/update.

There is no recommendation/action output field, table, or API response member.

## 13. API and Frontend Wiring

### API

Routes in [rca_routes.py](/home/agnigate/Desktop/NMS/hardik/backend/api/rca_routes.py):

- `POST /api/v1/rca/analyze`
- `GET /api/v1/rca/incidents`
- `GET /api/v1/rca/incidents/{incident_id}`

The serializer returns root IDs/labels, confidence, impact summary, windows, evidence, and raw alerts. It does not return an Incident ID, recommendations, contributing factors, topology entities, device details, events, metrics, or monitoring evidence.

The analyze response reports `alerts_considered` as the length of explicitly supplied `alert_ids`; when no IDs are supplied, it returns `0` even though the engine may analyze all alerts in the requested time window.

### Frontend

[RCA.tsx](/home/agnigate/Desktop/NMS/figma%20design/src/pages/RCA.tsx) uses real `listRCAIncidents`, `getRCAIncident`, and `analyzeRCA` functions from [api.ts](/home/agnigate/Desktop/NMS/figma%20design/src/lib/api.ts).

It provides real time filters of 1 hour, 24 hours, 7 days, and 30 days and an `Analyze alerts` action. It displays:

- root kind and root label
- confidence
- impact summary
- persisted evidence
- raw alert ID, severity, title, and status
- loading through React Query state and list/detail error/empty states

It does not allow selecting an Incident or device as an RCA input, does not show a linked Incident, does not show device/IP context, does not show topology entities or metrics/events, and does not display recommendations. There is no frontend polling loop (`refetchInterval` is absent).

## 14. Real Incident Applicability

The real Device-Down Incident path is currently:

```text
realtime monitor
 -> Alert 513 (device 115)
 -> Incident 8 and IncidentAlert link
 -> no RCA invocation
 -> no Incident.rca_incident_id
 -> no RCA display from Incident Management
```

The older real RCA row is separately reachable:

```text
Alerts 445-469
 -> RCA heuristic
 -> RCAIncident 1
 -> RCAEvidence rows 1-25
 -> RCA frontend
```

This demonstrates that persisted alert-based RCA can produce and display a result, but it does not demonstrate automatic analysis of the currently verified Device-Down Incident.

## 15. Performance Risks

- `correlate_alerts()` loads all active CMDB CIs and all active CMDB relationships for every analysis request, regardless of the selected alert devices.
- `_infer_interface()` performs one interface query per alert, creating an N+1 query pattern.
- RCA serialization iterates all evidence and then performs a separate alert query; list responses serialize evidence/raw alerts for every returned RCA row.
- Evidence and history are not bounded in the detail serializer; the list route is bounded to 200 RCA rows but not to evidence per row.
- The engine groups only the selected alert window and limits explicit IDs to 500, but it does not impose a database-side alert result limit when no IDs are provided.
- Frontend requests are React Query cached with 30-second stale time and no polling loop; repeated analysis is user-triggered.

## 16. Exact Missing Pieces

1. No central Incident -> RCA adapter after automatic Incident creation.
2. No traversal from `Incident` through `incident_alerts` to select the incident’s real evidence.
3. No Incident ID on `RCAIncident` and no automatic update of `Incident.rca_incident_id`.
4. No automatic, scheduled, or startup RCA processing.
5. No use of `device_status_history`, `device_metrics`, SNMP history, monitoring history, or `events`.
6. No direct topology, LLDP, or CDP reads; only existing CMDB relationship rows are considered.
7. No proof-oriented root-cause model that distinguishes correlation from causation or handles upstream/downstream alert propagation from actual topology observations.
8. No contributing-factor model separate from the selected root.
9. No persisted impacted device/CI relationship set beyond alert IDs in evidence payload.
10. No recommendations or safe action output.
11. No RCA version/history/audit records and no evidence reconciliation on recalculation.
12. No frontend Incident/device selector or Incident Management RCA display.
13. `alerts_considered` is inaccurate when analysis is time-window based without explicit IDs.
14. Time handling is inconsistent in the observed real records: the Device-Down alert creation timestamps are later than the current runtime UTC bound while resolved timestamps are earlier. RCA currently uses naive UTC comparisons and does not normalize or explain this condition.

## 17. Minimum Implementation Required

No implementation was performed during this verification.

The minimum production path would be:

1. Add one Incident-scoped RCA entry point that receives a persisted Incident ID and resolves its linked real alerts through `incident_alerts`.
2. Preserve the existing alert-window analyzer as a reusable calculation component, but constrain its inputs to the selected Incident’s evidence plus explicitly selected related alerts.
3. Persist the RCA-to-Incident association and reconcile RCA evidence atomically on repeat analysis.
4. Add real event/status/metric/topology evidence only from existing persisted tables and define deterministic evidence precedence before changing the score.
5. Add persisted contributing factors, impacted entities, and recommendations only if backed by actual source evidence and an explicit safe policy.
6. Add RCA history/version records and expose the linked RCA from Incident detail/frontend.
7. Bound source queries and serialize only the selected result’s evidence to control request cost.
8. Add regression coverage for the real Incident -> linked alert -> RCA linkage, repeat analysis, stale evidence reconciliation, absent evidence, and time-boundary behavior.

No code, database records, polling, or other modules were modified.
