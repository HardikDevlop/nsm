from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.models import Alert, CIRelationship, ConfigurationItem, Event, Incident, IncidentAlert, Interface
from backend.models.rca import RCAEvidence, RCAIncident


@dataclass(frozen=True)
class Candidate:
    kind: str
    label: str
    device_id: int | None = None
    interface_id: int | None = None
    ci_id: int | None = None


def _utc_naive(value: datetime) -> datetime:
    """Normalize DB timestamps to the project's naive-UTC persistence form."""
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def analyze_alerts(alerts: list[dict[str, Any]], relationships: list[dict[str, Any]],
                  ci_by_device: dict[int, dict[str, Any]], ci_by_interface: dict[int, dict[str, Any]],
                  window_seconds: int = 300) -> dict[str, Any] | None:
    if not alerts:
        return None
    ordered = sorted(alerts, key=lambda item: item["created_at"])
    start = ordered[0]["created_at"]
    grouped = [item for item in ordered if (item["created_at"] - start).total_seconds() <= window_seconds]
    candidates: dict[tuple[str, int], Candidate] = {}
    for alert in grouped:
        interface_id = alert.get("interface_id")
        device_id = alert.get("device_id")
        ci = ci_by_interface.get(interface_id) if interface_id else None
        ci = ci or (ci_by_device.get(device_id) if device_id else None)
        if ci:
            candidate = Candidate("ci", ci["name"], device_id, interface_id, ci["id"])
        elif interface_id:
            candidate = Candidate("interface", alert.get("interface_name", f"Interface {interface_id}"), device_id, interface_id)
        elif device_id:
            candidate = Candidate("device", alert.get("device_name", f"Device {device_id}"), device_id)
        else:
            candidate = Candidate("service", "Unmapped service")
        key = (candidate.kind, candidate.ci_id or candidate.interface_id or candidate.device_id or 0)
        candidates[key] = candidate

    outgoing: defaultdict[int, set[int]] = defaultdict(set)
    incoming: defaultdict[int, set[int]] = defaultdict(set)
    for relation in relationships:
        source, target = relation["source_ci_id"], relation["target_ci_id"]
        outgoing[source].add(target)
        incoming[target].add(source)

    def downstream_count(ci_id: int | None) -> int:
        if not ci_id:
            return 0
        seen: set[int] = set()
        stack = list(outgoing.get(ci_id, ()))
        while stack:
            node = stack.pop()
            if node not in seen:
                seen.add(node)
                stack.extend(outgoing.get(node, ()))
        return len(seen)

    scores: dict[tuple[str, int], float] = {}
    for key, candidate in candidates.items():
        related = [a for a in grouped if (ci_by_interface.get(a.get("interface_id")) or ci_by_device.get(a.get("device_id")) or {}).get("id") == candidate.ci_id] if candidate.ci_id else [a for a in grouped if a.get("device_id") == candidate.device_id]
        severity = {"critical": 1.0, "high": .8, "warning": .5, "medium": .5, "low": .25, "info": .1}
        score = max((severity.get(str(a.get("severity", "warning")).lower(), .3) for a in related), default=.2)
        score += max(0, 1 - ((min((a["created_at"] for a in related), default=start) - start).total_seconds() / max(window_seconds, 1))) * .4
        score += min(downstream_count(candidate.ci_id) * .12, .6)
        scores[key] = score
    root_key = max(scores, key=scores.get)
    root = candidates[root_key]
    impacted = sorted({a["id"] for a in grouped if a["id"] != next((x["id"] for x in grouped if x.get("device_id") == root.device_id), None)})
    evidence = [{"evidence_type": "alert", "alert_id": a["id"], "score": .8, "reason": "Alert occurred within the correlated RCA time window"} for a in grouped]
    for relation in relationships:
        if root.ci_id == relation["source_ci_id"] or root.ci_id == relation["target_ci_id"]:
            evidence.append({"evidence_type": "topology" if relation.get("relationship_type") == "topology_link" else "cmdb", "relationship_id": relation["id"], "score": .7, "reason": f"CMDB relationship {relation['relationship_type']} links the root to impacted CIs"})
    confidence = min(.99, max(.1, scores[root_key] / 2))
    return {"root": root, "confidence": round(confidence, 4), "impact_alert_ids": impacted, "evidence": evidence, "grouped_alert_ids": [a["id"] for a in grouped], "window_start": start, "window_end": grouped[-1]["created_at"]}


def _infer_interface(db: Session, alert: Alert) -> Interface | None:
    if not alert.device_id:
        return None
    # Only an explicitly interface-scoped alert may create an interface
    # candidate. Device-level alerts can mention an interface in their
    # description, but that does not make the interface the fault root.
    title = (alert.title or "").strip()
    if not title.lower().startswith("interface down:"):
        return None
    interface_label = title.split(":", 1)[1].strip() if ":" in title else ""
    if not interface_label:
        return None
    interfaces = db.query(Interface).filter(Interface.device_id == alert.device_id).all()
    return next((item for item in interfaces if item.interface_name and item.interface_name.casefold() == interface_label.casefold()), None)


def correlate_alerts(db: Session, start: datetime, end: datetime, alert_ids: list[int] | None = None) -> RCAIncident | None:
    query = db.query(Alert).filter(Alert.deleted_at.is_(None), Alert.created_at >= start, Alert.created_at <= end)
    if alert_ids:
        query = query.filter(Alert.id.in_(alert_ids[:500]))
    alerts = query.order_by(Alert.created_at.asc(), Alert.id.asc()).all()
    if not alerts:
        return None
    devices = {a.device_id: a.device for a in alerts if a.device_id and a.device}
    ci_rows = db.query(ConfigurationItem).filter(ConfigurationItem.deleted_at.is_(None)).all()
    ci_by_device = {ci.device_id: {"id": ci.id, "name": ci.name} for ci in ci_rows if ci.device_id}
    ci_by_interface = {ci.interface_id: {"id": ci.id, "name": ci.name} for ci in ci_rows if ci.interface_id}
    relations = [{"id": r.id, "source_ci_id": r.source_ci_id, "target_ci_id": r.target_ci_id, "relationship_type": r.relationship_type} for r in db.query(CIRelationship).filter(CIRelationship.deleted_at.is_(None)).all()]
    normalized = []
    for alert in alerts:
        interface = _infer_interface(db, alert)
        normalized.append({"id": alert.id, "device_id": alert.device_id, "device_name": devices.get(alert.device_id).hostname if devices.get(alert.device_id) else None, "interface_id": interface.id if interface else None, "interface_name": interface.interface_name if interface else None, "severity": alert.severity, "title": alert.title, "created_at": alert.created_at})
    result = analyze_alerts(normalized, relations, ci_by_device, ci_by_interface)
    if result is None:
        return None
    root: Candidate = result["root"]
    key = hashlib.sha256((":".join(map(str, sorted(result["grouped_alert_ids"]))) + f":{result['window_start'].replace(second=0, microsecond=0).isoformat()}" ).encode()).hexdigest()
    incident = db.query(RCAIncident).filter(RCAIncident.correlation_key == key).first()
    if incident is None:
        incident = RCAIncident(correlation_key=key, created_at=datetime.utcnow())
        db.add(incident)
    incident.root_kind, incident.root_label = root.kind, root.label
    incident.root_device_id, incident.root_interface_id, incident.root_ci_id = root.device_id, root.interface_id, root.ci_id
    incident.confidence = result["confidence"]
    incident.impact_summary = f"{len(result['impact_alert_ids'])} downstream/correlated alert(s) potentially impacted"
    incident.window_start, incident.window_end, incident.updated_at = result["window_start"], result["window_end"], datetime.utcnow()
    db.flush()
    # Re-analysis may change the eligible root or correlated alert window.
    # Reconcile evidence in place so stale rows are removed and current rows
    # are updated without replacing the persisted RCA incident.
    _reconcile_incident_evidence(db, incident, result)
    db.commit()
    db.refresh(incident)
    return incident


class IncidentRCAError(ValueError):
    """Raised when an Incident cannot provide usable persisted RCA evidence."""


def _incident_context(db: Session, alerts: list[Alert]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[int, dict[str, Any]], dict[int, dict[str, Any]]]:
    devices = {a.device_id: a.device for a in alerts if a.device_id and a.device}
    ci_rows = db.query(ConfigurationItem).filter(ConfigurationItem.deleted_at.is_(None)).all()
    ci_by_device = {ci.device_id: {"id": ci.id, "name": ci.name} for ci in ci_rows if ci.device_id}
    ci_by_interface = {ci.interface_id: {"id": ci.id, "name": ci.name} for ci in ci_rows if ci.interface_id}
    relations = [{"id": r.id, "source_ci_id": r.source_ci_id, "target_ci_id": r.target_ci_id, "relationship_type": r.relationship_type} for r in db.query(CIRelationship).filter(CIRelationship.deleted_at.is_(None)).all()]
    normalized = []
    for alert in alerts:
        interface = _infer_interface(db, alert)
        device = devices.get(alert.device_id)
        normalized.append({"id": alert.id, "device_id": alert.device_id, "device_name": device.hostname if device else None, "interface_id": interface.id if interface else None, "interface_name": interface.interface_name if interface else None, "severity": alert.severity, "title": alert.title, "created_at": _utc_naive(alert.created_at)})
    return normalized, relations, ci_by_device, ci_by_interface


def _reconcile_incident_evidence(db: Session, incident: RCAIncident, result: dict[str, Any]) -> None:
    current: dict[tuple[str, int | None, int | None], dict[str, Any]] = {}
    for item in result["evidence"]:
        key = (item["evidence_type"], item.get("alert_id"), item.get("relationship_id"))
        current[key] = item

    existing = {(row.evidence_type, row.alert_id, row.relationship_id): row for row in list(incident.evidence)}
    for key, row in existing.items():
        item = current.get(key)
        if item is None:
            db.delete(row)
            continue
        row.event_id = item.get("event_id")
        row.score = item["score"]
        row.reason = item["reason"]
        row.payload = {"raw_alert_ids": result["grouped_alert_ids"]}

    for key, item in current.items():
        if key not in existing:
            db.add(RCAEvidence(incident_id=incident.id, evidence_type=item["evidence_type"], alert_id=item.get("alert_id"), event_id=item.get("event_id"), relationship_id=item.get("relationship_id"), score=item["score"], reason=item["reason"], payload={"raw_alert_ids": result["grouped_alert_ids"]}))


def analyze_incident_rca(db: Session, incident_id: int) -> RCAIncident | None:
    """Analyze only the persisted alerts linked to one Incident.

    The existing alert-window entry point remains unchanged. Direct IncidentAlert
    links are authoritative and therefore are not filtered by the current clock.
    """
    source = db.get(Incident, incident_id)
    if source is None:
        raise IncidentRCAError("Incident not found")
    links = db.query(IncidentAlert).filter(IncidentAlert.incident_id == incident_id).order_by(IncidentAlert.linked_at.asc(), IncidentAlert.id.asc()).all()
    alert_ids = [link.alert_id for link in links]
    if not alert_ids:
        raise IncidentRCAError("Incident has no linked alerts for RCA analysis")
    alerts = db.query(Alert).filter(Alert.id.in_(alert_ids), Alert.deleted_at.is_(None)).order_by(Alert.created_at.asc(), Alert.id.asc()).all()
    if not alerts:
        raise IncidentRCAError("Incident has no non-deleted linked alerts for RCA analysis")

    normalized, relations, ci_by_device, ci_by_interface = _incident_context(db, alerts)
    timestamps = [item["created_at"] for item in normalized]
    span = max(0, int((max(timestamps) - min(timestamps)).total_seconds()))
    result = analyze_alerts(normalized, relations, ci_by_device, ci_by_interface, window_seconds=max(300, span + 1))
    if result is None:
        raise IncidentRCAError("Incident linked alerts did not produce RCA evidence")

    correlation_key = f"incident:{incident_id}"
    with db.begin_nested():
        rca = db.get(RCAIncident, source.rca_incident_id) if source.rca_incident_id else None
        if rca is not None and rca.correlation_key != correlation_key:
            rca = None
        if rca is None:
            rca = db.query(RCAIncident).filter(RCAIncident.correlation_key == correlation_key).first()
        if rca is None:
            rca = RCAIncident(correlation_key=correlation_key, created_at=datetime.utcnow())
            db.add(rca)
        rca.root_kind, rca.root_label = result["root"].kind, result["root"].label
        rca.root_device_id, rca.root_interface_id, rca.root_ci_id = result["root"].device_id, result["root"].interface_id, result["root"].ci_id
        rca.confidence = result["confidence"]
        rca.impact_summary = f"{len(result['impact_alert_ids'])} downstream/correlated alert(s) potentially impacted"
        rca.window_start, rca.window_end, rca.updated_at = result["window_start"], result["window_end"], datetime.utcnow()
        db.flush()
        source.rca_incident_id = rca.id
        _reconcile_incident_evidence(db, rca, result)
        db.flush()
    return rca
