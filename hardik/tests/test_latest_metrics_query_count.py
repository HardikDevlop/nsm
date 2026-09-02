from datetime import datetime

from backend.api import snmp_device_routes


class _Result:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def one(self):
        return self.row


class _CountingSession:
    def __init__(self, row):
        self.row = row
        self.execute_count = 0
        self.parameters = None

    def execute(self, statement, parameters=None):
        self.execute_count += 1
        self.parameters = parameters
        return _Result(self.row)


def test_latest_metrics_uses_one_round_trip_and_preserves_json(monkeypatch):
    polled_at = datetime(2026, 8, 29, 10, 0, 0)
    row = {
        "cpu": {"utilization_percent": 12.5, "per_core": {}, "load_avg": {}, "polled_at": polled_at},
        "memory": {
            "total_bytes": 100,
            "used_bytes": 40,
            "free_bytes": 60,
            "cached_bytes": 10,
            "buffer_bytes": 5,
            "swap_total": 20,
            "swap_free": 15,
            "utilization_percent": 40.0,
            "polled_at": polled_at,
        },
        "storage": [{
            "volume_id": "root",
            "mount_name": "/",
            "total_bytes": 1000,
            "used_bytes": 300,
            "free_bytes": 700,
            "utilization_percent": 30.0,
            "type_label": "disk",
            "polled_at": polled_at,
        }],
        "interfaces": [{
            "interface_id": 4,
            "if_index": 1,
            "name": "eth0",
            "oper_status": "UP",
            "admin_status": "UP",
            "speed_bps": 1000,
            "rx_mbps": 1.0,
            "tx_mbps": 2.0,
            "rx_octets": 10,
            "tx_octets": 20,
            "rx_packets": 30,
            "tx_packets": 40,
            "errors": 0,
            "discards": 0,
            "utilization_percent": 1.5,
            "polled_at": polled_at,
        }],
        "environment": [{
            "sensor_id": "temp-1",
            "sensor_name": "CPU",
            "sensor_type": "temperature",
            "value": 42.0,
            "unit": "C",
            "status": "ok",
            "polled_at": polled_at,
        }],
    }
    cached = []
    monkeypatch.setattr("backend.cache.redis_cache.get_json", lambda key: None)
    monkeypatch.setattr("backend.cache.redis_cache.set_json", lambda key, value: cached.append(value))
    db = _CountingSession(row)

    result = snmp_device_routes.get_latest_metrics(7, db, None)

    assert db.execute_count == 1
    assert db.parameters == {"device_id": 7}
    assert result["device_id"] == 7
    assert result["cpu"]["utilization_percent"] == 12.5
    assert result["memory"]["used_bytes"] == 40
    assert result["storage"][0]["mount_name"] == "/"
    assert result["interfaces"][0]["name"] == "eth0"
    assert result["environment"][0]["value"] == 42.0
    assert cached == [result]
