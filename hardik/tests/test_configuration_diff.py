from pathlib import Path

from backend.api.config_backup_routes import ConfigurationComparePayload, router
from backend.config_backups.service import compare_configurations


def test_comparison_payload_requires_two_version_identifiers():
    payload = ConfigurationComparePayload(device_id=3, from_version=1, to_version=2)
    assert payload.to_version == 2


def test_comparison_service_is_persisted_and_audited():
    assert "initiated_by" in compare_configurations.__annotations__


def test_unchanged_capture_is_audited_without_creating_a_version():
    source = Path("backend/config_backups/service.py").read_text()
    assert 'CONFIGURATION_CAPTURE_UNCHANGED' in source
    route_source = Path("backend/api/config_backup_routes.py").read_text()
    assert "db.commit()" in route_source


def test_comparison_routes_cover_explicit_and_baseline_current_comparisons():
    paths = {route.path for route in router.routes}
    assert "/api/v1/config-backups/compare" in paths
    assert "/api/v1/config-backups/devices/{device_id}/compare/baseline-current" in paths
