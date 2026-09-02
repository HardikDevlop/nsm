from backend.api.config_backup_routes import ConfigurationCapturePayload, router
from backend.config_backups.drivers import UnsupportedDriver, get_driver


def test_configuration_capture_payload_is_bounded_and_source_tagged():
    payload = ConfigurationCapturePayload(device_id=7, source="manual", content="hostname edge-1")
    assert payload.source == "manual"
    assert payload.is_startup is False


def test_unsupported_vendor_driver_fails_explicitly_without_fake_config():
    driver = get_driver("unknown-vendor")
    assert isinstance(driver, UnsupportedDriver)
    try:
        driver.capture(7)
    except RuntimeError as exc:
        assert "No configuration driver" in str(exc)
    else:
        raise AssertionError("unsupported driver returned configuration")


def test_configuration_routes_cover_capture_and_history():
    paths = {route.path for route in router.routes}
    assert "/api/v1/config-backups/capture" in paths
    assert "/api/v1/config-backups/devices/{device_id}" in paths
    assert "/api/v1/config-backups/devices/{device_id}/versions/{version}" in paths
