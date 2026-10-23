from unittest.mock import Mock

from backend.windows_monitoring.sensors import (
    LibreHardwareMonitorProvider,
    NativeCIMSensorProvider,
    normalize_sensor,
)


def test_normalize_sensor_adds_stable_id_and_rejects_invalid_value():
    raw = {"sensor_name": "CPU Package", "sensor_type": "cpu_package_temperature", "value": "nan", "unit": "°C", "source": "test", "status": "ok", "collected_at": "now"}
    reading = normalize_sensor(raw)
    assert reading.sensor_id == normalize_sensor(raw).sensor_id
    assert reading.value is None
    assert reading.status == "unavailable"


def test_native_provider_preserves_missing_sensor_status():
    client = Mock()
    client.native_sensor_discovery.return_value = [{"sensor_name": "Fan", "sensor_type": "fan", "value": None, "unit": "rpm", "source": "native_wmi", "status": "unsupported", "collected_at": "now", "error": "class_not_returned"}]
    result = NativeCIMSensorProvider(client).discover()
    assert result.status == "ok"
    assert result.sensors[0].status == "unsupported"
    assert result.sensors[0].value is None


def test_native_provider_reports_collection_failure():
    client = Mock()
    client.native_sensor_discovery.side_effect = RuntimeError("provider failure")
    result = NativeCIMSensorProvider(client).discover()
    assert result.status == "collection_failed"
    assert result.sensors == ()


def test_librehardwaremonitor_is_explicitly_not_installed():
    result = LibreHardwareMonitorProvider().discover()
    assert result.status == "provider_not_installed"
    assert result.sensors == ()


def test_librehardwaremonitor_normalizes_sensor_types_and_identity():
    client = Mock()
    client.librehardwaremonitor_sensors.return_value = [
        {"Identifier": "/cpu/0/temperature/0", "Name": "CPU Package", "Value": "52.5", "SensorType": "Temperature", "HardwareId": "CPU0"},
        {"Identifier": "/gpu/0/load/0", "Name": "GPU Core", "Value": "41", "SensorType": "Load", "HardwareId": "GPU0"},
    ]
    result = LibreHardwareMonitorProvider(client).discover()
    assert result.status == "ok"
    assert result.sensors[0].unit == "°C"
    assert result.sensors[0].identifier == "/cpu/0/temperature/0"
    assert result.sensors[0].hardware_id == "CPU0"
    assert result.sensors[1].unit == "%"
