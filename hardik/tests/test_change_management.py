from datetime import datetime, timedelta

import pytest

from backend.api.change_routes import ChangeCreatePayload, ChangeUpdatePayload, router


def test_change_request_validates_maintenance_window_and_plans():
    start = datetime(2026, 8, 29, 10, 0)
    payload = ChangeCreatePayload(title="Upgrade core", risk="high", impact="high", maintenance_start=start, maintenance_end=start + timedelta(hours=1), implementation_plan="Apply change", rollback_plan="Restore backup")
    assert payload.rollback_plan == "Restore backup"
    with pytest.raises(ValueError):
        ChangeCreatePayload(title="Invalid", maintenance_start=start, maintenance_end=start)


def test_change_update_restricts_lifecycle_values():
    assert ChangeUpdatePayload(status="rolled_back").status == "rolled_back"
    with pytest.raises(ValueError):
        ChangeUpdatePayload(status="random")


def test_change_routes_cover_request_approval_links_and_audit_workflow():
    paths = {route.path for route in router.routes}
    assert "/api/v1/changes" in paths
    assert "/api/v1/changes/{change_id}/approve" in paths
    assert "/api/v1/changes/{change_id}/cis/{ci_id}" in paths
    assert "/api/v1/changes/{change_id}/incidents/{incident_id}" in paths
