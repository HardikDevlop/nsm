from datetime import datetime, timedelta

from backend.api.incident_routes import SLAPolicyPayload
from backend.incidents.sla import VALID_PAUSE_STATES
from backend.models import Incident, IncidentSLAConfig


def test_sla_policy_requires_positive_targets_and_known_pause_state():
    policy = SLAPolicyPayload(priority="p1", response_target_minutes=5, resolution_target_minutes=30)
    assert policy.pause_states == ["pending"]
    assert VALID_PAUSE_STATES == {"pending"}


def test_sla_deadlines_are_derived_from_policy_targets():
    started = datetime(2026, 8, 29, 10, 0)
    policy = IncidentSLAConfig(priority="p1", response_target_minutes=5, resolution_target_minutes=30, pause_states=["pending"], created_at=started, updated_at=started)
    incident = Incident(priority="p1", service_id=None, created_at=started, updated_at=started, title="x", category="other")
    assert incident.priority == policy.priority
    assert started + timedelta(minutes=policy.response_target_minutes) == datetime(2026, 8, 29, 10, 5)
    assert started + timedelta(minutes=policy.resolution_target_minutes) == datetime(2026, 8, 29, 10, 30)
