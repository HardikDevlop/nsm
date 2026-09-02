from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.incident_routes import IncidentCreatePayload, IncidentUpdatePayload, router
from backend.database.session import Base
from backend.incidents.service import _category, _priority, process_alert_for_incident, process_alert_recovery
from backend.models import Alert, Device, Incident, IncidentAlert, IncidentHistory, IncidentSLAConfig, IncidentSLATimer


def test_incident_payloads_validate_workflow_fields():
    payload = IncidentCreatePayload(title="Router outage", category="availability", priority="p1", alert_ids=[3])
    assert payload.alert_ids == [3]
    assert IncidentUpdatePayload(status="closed").status == "closed"


def test_qualifying_alerts_map_to_category_and_priority():
    alert = Alert(title="Interface down", description="uplink unavailable", severity="critical", status="open", created_at=datetime.utcnow())
    assert _category(alert) == "availability"
    assert _priority(alert) == "p1"


def test_incident_routes_cover_crud_comments_and_attachments():
    paths = {route.path for route in router.routes}
    assert "/api/v1/incidents" in paths
    assert "/api/v1/incidents/{incident_id}" in paths
    assert "/api/v1/incidents/{incident_id}/comments" in paths
    assert "/api/v1/incidents/{incident_id}/attachments" in paths
    assert "/api/v1/incidents/{incident_id}/acknowledge" in paths
    assert "/api/v1/incidents/{incident_id}/resolve" in paths
    assert "/api/v1/incidents/{incident_id}/reopen" in paths
    assert "/api/v1/incidents/{incident_id}/history" in paths


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _alert(db, device_id, title, severity="critical", status="open"):
    item = Alert(device_id=device_id, title=title, description=title, severity=severity, status=status, created_at=datetime.utcnow())
    db.add(item); db.flush()
    return item


def test_alert_adapter_is_idempotent_and_separates_interfaces():
    db = _db(); db.add(Device(id=115, hostname="Core-switch", ip_address="192.0.2.115", created_at=datetime.utcnow())); db.flush()
    first = _alert(db, 115, "Interface Down: GigabitEthernet1")
    second = _alert(db, 115, "Interface Down: GigabitEthernet1")
    other = _alert(db, 115, "Interface Down: GigabitEthernet2")
    assert process_alert_for_incident(db, first.id).id == process_alert_for_incident(db, first.id).id
    assert process_alert_for_incident(db, second.id).id == process_alert_for_incident(db, first.id).id
    assert process_alert_for_incident(db, other.id).id != process_alert_for_incident(db, first.id).id
    assert db.query(Incident).count() == 2
    assert db.query(IncidentAlert).count() == 3


def test_adapter_rejects_unsupported_severity_and_exposes_device_context():
    db = _db(); db.add(Device(id=157, hostname="Edge", ip_address="192.0.2.157", created_at=datetime.utcnow())); db.flush()
    medium = _alert(db, 157, "Device Down: Edge", severity="medium")
    assert process_alert_for_incident(db, medium.id) is None
    critical = _alert(db, 157, "Device Down: Edge")
    incident = process_alert_for_incident(db, critical.id)
    assert incident.correlation_key == "device:157:availability:device_down"


def test_recovery_resolves_only_when_no_linked_active_alert_remains():
    db = _db(); db.add(Device(id=115, hostname="Core-switch", ip_address="192.0.2.115", created_at=datetime.utcnow())); db.flush()
    first = _alert(db, 115, "Interface Down: Gi1"); second = _alert(db, 115, "Interface Down: Gi1")
    incident = process_alert_for_incident(db, first.id); process_alert_for_incident(db, second.id)
    first.status = "resolved"; first.resolved_at = datetime.utcnow(); db.flush()
    assert process_alert_recovery(db, first.id) == []
    assert incident.status == "open"
    second.status = "resolved"; second.resolved_at = datetime.utcnow(); db.flush()
    assert process_alert_recovery(db, second.id) == [incident]
    assert incident.status == "resolved" and incident.resolved_at is not None


def test_resolved_recurrence_reopens_and_closed_recurrence_creates_new_incident():
    db = _db(); db.add(Device(id=115, hostname="Core-switch", ip_address="192.0.2.115", created_at=datetime.utcnow())); db.flush()
    first = _alert(db, 115, "Device Down: Core-switch"); incident = process_alert_for_incident(db, first.id)
    first.status = "resolved"; first.resolved_at = datetime.utcnow(); db.flush(); process_alert_recovery(db, first.id)
    recurrence = _alert(db, 115, "Device Down: Core-switch"); reopened = process_alert_for_incident(db, recurrence.id)
    assert reopened.id == incident.id and reopened.status == "open"
    reopened.status = "closed"; reopened.closed_at = datetime.utcnow(); db.flush()
    fresh = _alert(db, 115, "Device Down: Core-switch"); new_incident = process_alert_for_incident(db, fresh.id)
    assert new_incident.id != reopened.id
    assert {row.action for row in db.query(IncidentHistory).all()} >= {"created", "alert_linked", "alert_recovered", "reopened"}


def test_sla_timer_starts_only_when_policy_exists():
    db = _db(); db.add(Device(id=115, hostname="Core-switch", ip_address="192.0.2.115", created_at=datetime.utcnow())); db.add(IncidentSLAConfig(priority="p1", response_target_minutes=5, resolution_target_minutes=30, pause_states=["pending"], created_at=datetime.utcnow(), updated_at=datetime.utcnow())); db.flush()
    alert = _alert(db, 115, "Device Down: Core-switch")
    process_alert_for_incident(db, alert.id)
    assert db.query(IncidentSLATimer).count() == 1
