from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace

from backend.models import Alert, Interface
from backend.models.snmp import LatestEnvironment, LatestStorage
from backend.services.snmp_polling import SNMPPoller


class _Query:
    def __init__(self, db, model):
        self.db = db
        self.model = model
    def filter(self, *args):
        return self
    def order_by(self, *args):
        return self
    def all(self):
        return list(self.db.rows.get(self.model, []))


class _DB:
    def __init__(self, rows=None):
        self.rows = rows or {}
        self.query_counts = {}
        self.added = []
    def query(self, model):
        self.query_counts[model] = self.query_counts.get(model, 0) + 1
        return _Query(self, model)
    def add(self, value):
        self.added.append(value)


def test_storage_latest_lookup_is_constant_and_semantics_are_preserved():
    existing = LatestStorage(device_id=7, volume_id="1")
    db = _DB({LatestStorage: [existing]})
    poller = SNMPPoller(db)
    data = {"volumes": [
        {"index": 1, "filesystem": "/", "total_bytes": 100, "used_bytes": 50},
        {"index": 2, "filesystem": "/data", "total_bytes": 200, "used_bytes": 75},
        {"index": 3, "filesystem": "/logs", "total_bytes": 300, "used_bytes": 25},
    ]}
    asyncio.run(poller._persist_storage(7, data, datetime(2026, 1, 1)))
    assert db.query_counts[LatestStorage] == 1
    assert existing.mount_name == "/" and existing.total_bytes == 100
    latest_created = [row for row in db.added if isinstance(row, LatestStorage)]
    history_created = [row for row in db.added if row.__class__.__name__ == "StorageStatistic"]
    assert [row.volume_id for row in latest_created] == ["2", "3"]
    assert len(history_created) == 3


def test_environment_latest_lookup_is_constant_and_semantics_are_preserved():
    existing = LatestEnvironment(device_id=7, sensor_id="CPU Temp")
    db = _DB({LatestEnvironment: [existing]})
    poller = SNMPPoller(db)
    data = {
        "temperatures": [
            {"name": "CPU Temp", "type": "temperature", "value": 42, "status": "normal"},
            {"name": "Board Temp", "type": "temperature", "value": 50, "status": "warning"},
        ],
        "fans": [{"name": "Fan 1", "type": "fan", "value": 1000, "status": "failed"}],
    }
    asyncio.run(poller._persist_environment(7, data, datetime(2026, 1, 1)))
    assert db.query_counts[LatestEnvironment] == 1
    assert existing.value == 42 and existing.status == "ok"
    latest_created = [row for row in db.added if isinstance(row, LatestEnvironment)]
    history_created = [row for row in db.added if row.__class__.__name__ == "EnvironmentStatistic"]
    assert [row.sensor_id for row in latest_created] == ["Board Temp", "Fan 1"]
    assert len(history_created) == 3


def test_interface_alert_preloads_are_constant_and_preserve_actions(monkeypatch):
    interface_rows = [
        SimpleNamespace(id=11, interface_name="eth0"),
        SimpleNamespace(id=12, interface_name="eth1"),
        SimpleNamespace(id=13, interface_name="eth2"),
    ]
    active = SimpleNamespace(
        id=20, interface_id=12, title="Interface Down: eth1",
        status="open", created_at=datetime(2026, 1, 1),
    )
    db = _DB({Interface: interface_rows, Alert: [active]})
    created = []
    resolved = []

    def create_alert(db, device_id, title, description, severity, interface_id=None, existing_alert=None):
        if existing_alert is not None:
            return None
        alert = SimpleNamespace(title=title, interface_id=interface_id, status="open")
        created.append((title, severity, interface_id))
        return alert

    def resolve_alert(db, device_id, interface_id, interface_name, existing_alert=None):
        if existing_alert is None:
            return None
        existing_alert.status = "resolved"
        resolved.append((interface_id, interface_name))
        return existing_alert

    monkeypatch.setattr("backend.services.alerting.create_threshold_alert", create_alert)
    monkeypatch.setattr("backend.services.alerting.resolve_interface_down_alert", resolve_alert)
    poller = SNMPPoller(db)
    poller._evaluate_alerts(7, "interfaces", {"interfaces": [
        {"name": "eth0", "admin_status": "up", "oper_status": "down"},
        {"name": "eth1", "admin_status": "up", "oper_status": "down"},
        {"name": "eth2", "admin_status": "up", "oper_status": "up"},
    ]})
    assert db.query_counts == {Interface: 1, Alert: 1}
    assert created == [("Interface Down: eth0", "critical", 11)]
    assert resolved == []


def test_interface_alert_resolution_uses_preloaded_active_alert(monkeypatch):
    interface = SimpleNamespace(id=12, interface_name="eth1")
    active = SimpleNamespace(
        id=20, interface_id=12, title="Interface Down: eth1",
        status="open", created_at=datetime(2026, 1, 1),
    )
    db = _DB({Interface: [interface], Alert: [active]})
    resolved = []

    monkeypatch.setattr(
        "backend.services.alerting.resolve_interface_down_alert",
        lambda db, device_id, interface_id, interface_name, existing_alert=None:
            resolved.append(existing_alert) or existing_alert,
    )
    poller = SNMPPoller(db)
    poller._evaluate_alerts(7, "interfaces", {"interfaces": [
        {"name": "eth1", "admin_status": "up", "oper_status": "up"},
    ]})
    assert db.query_counts == {Interface: 1, Alert: 1}
    assert resolved == [active]
