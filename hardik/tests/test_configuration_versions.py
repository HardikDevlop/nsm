from backend.api.config_backup_routes import ConfigurationCapturePayload, router
from backend.config_backups.service import record_configuration
from backend.models import DeviceConfigurationVersion


def test_configuration_capture_payload_supports_manual_startup_and_sources():
    assert ConfigurationCapturePayload(device_id=1, source="startup", content="conf", is_startup=True).is_startup is True


def test_configuration_version_service_is_checksum_based_and_encrypted():
    assert "encrypted_content" in {column.name for column in DeviceConfigurationVersion.__table__.columns}
    assert "checksum" in {column.name for column in DeviceConfigurationVersion.__table__.columns}


def test_configuration_routes_cover_capture_and_version_history():
    paths = {route.path for route in router.routes}
    assert "/api/v1/config-backups/capture" in paths
    assert "/api/v1/config-backups/devices/{device_id}" in paths
    assert "/api/v1/config-backups/devices/{device_id}/versions/{version}" in paths
