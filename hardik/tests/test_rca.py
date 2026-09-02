from datetime import datetime, timedelta

from backend.api.rca_routes import AnalyzePayload, router
from backend.database.session import Base
from backend.models import Alert, ConfigurationItem, Device, Incident, IncidentAlert, Interface
from backend.models.cmdb import CIType
from backend.rca.engine import analyze_alerts, analyze_incident_rca, correlate_alerts
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def _alert(alert_id, device_id, created_at, severity="high"):
    return {"id": alert_id, "device_id": device_id, "created_at": created_at, "severity": severity}


def test_rca_selects_earliest_upstream_ci_and_reports_downstream_alerts():
    now = datetime(2026, 8, 29, 10, 0)
    result = analyze_alerts(
        [_alert(1, 10, now, "critical"), _alert(2, 20, now + timedelta(seconds=30), "warning")],
        [{"id": 7, "source_ci_id": 100, "target_ci_id": 200, "relationship_type": "depends_on"}],
        {10: {"id": 100, "name": "Core router"}, 20: {"id": 200, "name": "App server"}},
        {},
    )
    assert result["root"].label == "Core router"
    assert result["root"].ci_id == 100
    assert result["impact_alert_ids"] == [2]
    assert {item["evidence_type"] for item in result["evidence"]} == {"alert", "cmdb"}


def test_rca_groups_only_alerts_inside_time_window():
    now = datetime(2026, 8, 29, 10, 0)
    result = analyze_alerts([_alert(1, 10, now), _alert(2, 20, now + timedelta(minutes=6))], [], {}, {}, window_seconds=300)
    assert result["grouped_alert_ids"] == [1]
    assert result["impact_alert_ids"] == []


def test_rca_payload_limits_window_and_alert_selection():
    assert AnalyzePayload(hours=720, alert_ids=[1, 2]).hours == 720
    assert {route.path for route in router.routes} == {"/api/v1/rca/analyze", "/api/v1/rca/incidents", "/api/v1/rca/incidents/{incident_id}"}


def test_incident_scoped_rca_uses_linked_alerts_and_reconciles_evidence():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Device(id=115, hostname="Core-switch", ip_address="192.168.100.2", created_at=datetime.utcnow()))
    source = Incident(title="Device down", category="availability", priority="p1", status="open", created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    db.add(source)
    db.flush()
    first = Alert(device_id=115, title="Device Down: Core-switch", description="real alert", severity="critical", status="open", created_at=datetime(2030, 1, 1, 0, 0))
    db.add(first)
    db.flush()
    db.add(IncidentAlert(incident_id=source.id, alert_id=first.id, linked_at=datetime.utcnow()))
    db.flush()

    rca = analyze_incident_rca(db, source.id)
    db.commit()
    assert rca is not None
    assert source.rca_incident_id == rca.id
    assert {row.alert_id for row in rca.evidence} == {first.id}

    second = Alert(device_id=115, title="Device Down: Core-switch", description="second real alert", severity="critical", status="open", created_at=datetime(2030, 1, 1, 0, 1))
    db.add(second)
    db.flush()
    link = IncidentAlert(incident_id=source.id, alert_id=second.id, linked_at=datetime.utcnow())
    db.add(link)
    db.flush()
    same = analyze_incident_rca(db, source.id)
    db.commit()
    assert same.id == rca.id
    assert {row.alert_id for row in same.evidence} == {first.id, second.id}

    db.delete(link)
    db.flush()
    reconciled = analyze_incident_rca(db, source.id)
    db.commit()
    assert reconciled.id == rca.id
    assert {row.alert_id for row in reconciled.evidence} == {first.id}


def _persisted_rca_db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_device_down_selects_device_root_even_when_description_mentions_interface():
    db = _persisted_rca_db()
    device = Device(id=201, hostname="Core-switch", ip_address="192.0.2.201", created_at=datetime.utcnow())
    interface = Interface(id=301, device_id=201, interface_name="TenGigabitEthernet4")
    db.add_all([device, interface])
    db.add(Alert(device_id=201, title="Device Down: Core-switch", description="Device down on TenGigabitEthernet4", severity="critical", created_at=datetime(2030, 1, 1)))
    db.commit()

    result = correlate_alerts(db, datetime(2029, 12, 31), datetime(2030, 1, 2))

    assert result.root_kind == "device"
    assert result.root_device_id == 201
    assert result.root_interface_id is None


def test_interface_down_selects_matching_interface_root():
    db = _persisted_rca_db()
    device = Device(id=202, hostname="Core-switch", ip_address="192.0.2.202", created_at=datetime.utcnow())
    interface = Interface(id=302, device_id=202, interface_name="TenGigabitEthernet4")
    db.add_all([device, interface])
    db.add(Alert(device_id=202, title="Interface Down: TenGigabitEthernet4", description="SNMP reports interface is down", severity="critical", created_at=datetime(2030, 1, 1)))
    db.commit()

    result = correlate_alerts(db, datetime(2029, 12, 31), datetime(2030, 1, 2))

    assert result.root_kind == "interface"
    assert result.root_device_id == 202
    assert result.root_interface_id == 302


def test_cmdb_interface_child_cannot_override_device_down_root():
    db = _persisted_rca_db()
    device = Device(id=203, hostname="Core-switch", ip_address="192.0.2.203", created_at=datetime.utcnow())
    interface = Interface(id=303, device_id=203, interface_name="TenGigabitEthernet4")
    ci_type = CIType(id=401, name="Interface", category="infrastructure", created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    child_ci = ConfigurationItem(id=402, ci_type_id=401, name="TenGigabitEthernet4", interface_id=303, created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    db.add_all([device, interface, ci_type, child_ci])
    db.add(Alert(device_id=203, title="Device Down: Core-switch", description="Device failure observed on TenGigabitEthernet4", severity="critical", created_at=datetime(2030, 1, 1)))
    db.commit()

    result = correlate_alerts(db, datetime(2029, 12, 31), datetime(2030, 1, 2))

    assert result.root_kind == "device"
    assert result.root_device_id == 203
    assert result.root_interface_id is None
