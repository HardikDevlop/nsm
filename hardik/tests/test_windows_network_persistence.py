from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.windows_monitoring.cim import NetworkInterfaceResult
from backend.windows_monitoring import persistence


def interface(index=12, name="Ethernet 0"):
    return NetworkInterfaceResult(
        interface_index=index,
        name=name,
        description="Intel Ethernet",
        mac_address="AA-BB-CC-DD-EE-FF",
        ipv4_addresses=("192.168.100.154",),
        ipv6_addresses=("fe80::1%12",),
        interface_status="Up",
        link_speed_bps=1_000_000_000,
        rx_bytes_per_sec=1234,
        tx_bytes_per_sec=5678,
        adapter_index=index,
    )


def fake_db(row_id=41, row=None):
    db = Mock()
    db.execute.return_value.scalar_one.return_value = row_id
    db.query.return_value.filter.return_value.one.return_value = row or SimpleNamespace(
        id=row_id, device_id=314, module="network", collected_at=datetime.now(), data=[]
    )
    return db


def test_network_snapshot_serializes_real_fields_and_uses_network_module():
    db = fake_db()
    row = persistence.upsert_network_snapshot(db, 314, [interface()])

    statement = db.execute.call_args.args[0]
    assert row.module == "network"
    assert statement.table.name == "windows_metric_snapshots"
    assert statement.compile().params["module"] == "network"
    assert persistence.serialize_network_interfaces([interface()]) == [{
        "adapter_index": 12,
        "interface_index": 12,
        "name": "Ethernet 0",
        "description": "Intel Ethernet",
        "mac_address": "AA-BB-CC-DD-EE-FF",
        "ipv4_addresses": ["192.168.100.154"],
        "ipv6_addresses": ["fe80::1%12"],
        "interface_status": "Up",
        "link_speed_bps": 1_000_000_000,
        "rx_bytes_per_sec": 1234,
        "tx_bytes_per_sec": 5678,
    }]


def test_network_snapshot_upsert_targets_device_and_module_unique_key():
    db = fake_db()
    persistence.upsert_network_snapshot(db, 314, [interface(7, "Wi-Fi")])

    statement = db.execute.call_args.args[0]
    assert statement._post_values_clause is not None
    assert {column.name for column in statement.table.c}.issuperset({"device_id", "module", "collected_at", "data"})
    assert "uq_windows_metric_snapshots_device_module" in {
        constraint.name for constraint in statement.table.constraints
    }


def test_failed_network_persistence_rolls_back_without_commit():
    db = fake_db()
    db.execute.side_effect = RuntimeError("database unavailable")

    with pytest.raises(RuntimeError):
        persistence.save_network_snapshot(db, 314, [interface()])

    db.rollback.assert_called_once()
    db.commit.assert_not_called()


def test_network_snapshot_is_independent_from_other_modules():
    db = fake_db()
    persistence.upsert_network_snapshot(db, 314, [interface()])

    statement = db.execute.call_args.args[0]
    params = statement.compile().params
    assert params["device_id"] == 314
    assert params["module"] == "network"
    assert params["data"][0]["adapter_index"] == 12
    assert params["data"][0]["interface_index"] == 12


def test_missing_fields_and_multiple_adapters_are_json_safe():
    data = persistence.serialize_network_interfaces([
        NetworkInterfaceResult(1, "Ethernet", None, None, (), (), "Down", None, None, None, 0),
        NetworkInterfaceResult(None, None, None, None, (), (), None, None, None, None, None),
    ])

    assert len(data) == 2
    assert data[0]["mac_address"] is None
    assert data[0]["adapter_index"] == 0
    assert data[1]["interface_index"] is None
    assert data[1]["adapter_index"] is None
    assert data[1]["ipv4_addresses"] == []


def test_older_snapshot_records_remain_read_compatible_without_adapter_index():
    older = [{"interface_index": 18, "name": "Wi-Fi", "ipv4_addresses": ["192.168.100.154"]}]

    assert older[0]["interface_index"] == 18
    assert older[0].get("adapter_index") is None
