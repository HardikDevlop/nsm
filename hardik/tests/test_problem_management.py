from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.api.problem_routes import ALLOWED_TRANSITIONS, ProblemCreatePayload, ProblemUpdatePayload, _now, _serialize, _validate_owner, router
from backend.database.session import Base
from backend.models import Incident, Problem, ProblemIncident, RCAIncident, User


def test_problem_payload_covers_root_cause_workaround_known_error_and_fix():
    payload = ProblemCreatePayload(title="Recurring uplink failure", category="availability", priority="p1", root_cause="Firmware defect", workaround="Fail over link", known_error="Vendor issue", permanent_fix="Upgrade firmware", incident_ids=[1, 2])
    assert payload.incident_ids == [1, 2]
    assert payload.priority == "p1"
    assert ProblemUpdatePayload(status="known_error", root_cause="Documented").status == "known_error"


def test_problem_model_keeps_auditable_lifecycle_fields():
    item = Problem(number="PRB-000001", title="p", category="other", status="open", created_at=datetime.utcnow(), updated_at=datetime.utcnow())
    assert item.closed_at is None
    assert item.status == "open"


def test_problem_routes_cover_lifecycle_link_and_history():
    paths = {route.path for route in router.routes}
    assert "/api/v1/problems" in paths
    assert "/api/v1/problems/{problem_id}" in paths
    assert "/api/v1/problems/{problem_id}/incidents/{incident_id}" in paths
    assert "/api/v1/problems/{problem_id}/history" in paths


def test_problem_lifecycle_allows_only_controlled_transitions():
    assert ALLOWED_TRANSITIONS["open"] == {"open", "in_progress"}
    assert ALLOWED_TRANSITIONS["in_progress"] == {"in_progress", "known_error", "resolved"}
    assert ALLOWED_TRANSITIONS["known_error"] == {"known_error", "resolved"}
    assert ALLOWED_TRANSITIONS["resolved"] == {"resolved", "closed", "in_progress"}
    assert ALLOWED_TRANSITIONS["closed"] == {"closed"}


def test_problem_owner_must_be_active_user():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add_all([
        User(id=901, name="Active", email="active@example.com", password_hash="x", status="active"),
        User(id=902, name="Disabled", email="disabled@example.com", password_hash="x", status="inactive"),
    ])
    db.flush()
    _validate_owner(db, 901)
    with pytest.raises(Exception, match="inactive"):
        _validate_owner(db, 902)


def test_problem_detail_exposes_linked_incident_rca_summary():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    now = datetime.utcnow()
    rca = RCAIncident(correlation_key="problem-test-rca", root_kind="device", root_label="Core", confidence=88.0, impact_summary="Downstream service impact", window_start=now, window_end=now)
    db.add(rca); db.flush()
    incident = Incident(title="Core down", category="availability", priority="p1", status="open", rca_incident_id=rca.id, created_at=now, updated_at=now)
    problem = Problem(number="PRB-000900", title="Core recurrence", category="availability", priority="p1", status="open", created_at=now, updated_at=now)
    db.add_all([incident, problem]); db.flush()
    db.add(ProblemIncident(problem_id=problem.id, incident_id=incident.id, linked_at=now)); db.flush()
    result = _serialize(db, problem)
    assert result["incidents"][0]["rca"] == {"id": rca.id, "root_kind": "device", "root_label": "Core", "confidence": 88.0, "impact_summary": "Downstream service impact", "updated_at": rca.updated_at}


def test_problem_timestamps_use_application_timezone_convention():
    now = _now()
    assert now.utcoffset() is None
    assert now.hour == datetime.now().hour
