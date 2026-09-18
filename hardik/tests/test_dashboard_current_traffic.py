from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.api.overview_routes import (
    _aggregate_current_traffic, _overview_network_counts, _overview_timestamp,
    _select_current_interfaces,
)


def _row(row_id, polled_at, *, device_id=1, interface_id=10, rx=1.0, tx=2.0):
    return SimpleNamespace(
        id=row_id, device_id=device_id, interface_id=interface_id,
        name=f"eth{interface_id}", oper_status="UP", admin_status="UP",
        speed_bps=None, rx_mbps=rx, tx_mbps=tx, errors=None, discards=None,
        rx_packets=None, tx_packets=None, utilization_percent=None,
        polled_at=polled_at,
    )


def test_current_interface_selection_is_latest_then_id_and_fresh():
    now = datetime.now(timezone.utc)
    rows = [
        _row(1, now - timedelta(seconds=10), rx=1.0),
        _row(2, now - timedelta(seconds=10), rx=2.0),
        _row(3, now - timedelta(seconds=20), rx=3.0),
    ]
    selected = _select_current_interfaces(rows, {1: 10}, now)
    assert len(selected) == 1
    assert selected[0]["rx_mbps"] == 2.0
    assert selected[0]["freshness"] == "fresh"


def test_stale_and_null_measurements_are_not_recast_as_zero():
    now = datetime.now(timezone.utc)
    rows = [_row(1, now - timedelta(seconds=31), rx=None, tx=None)]
    selected = _select_current_interfaces(rows, {1: 10}, now)
    assert selected[0]["freshness"] == "stale"
    assert selected[0]["rx_mbps"] is None
    assert selected[0]["tx_mbps"] is None


def test_different_interfaces_each_contribute_once():
    now = datetime.now(timezone.utc)
    rows = [_row(1, now, interface_id=10, rx=0.0), _row(2, now, interface_id=11, rx=4.0)]
    selected = _select_current_interfaces(rows, {1: 60}, now)
    assert {(row["device_id"], row["interface_id"]) for row in selected} == {(1, 10), (1, 11)}
    assert selected[0]["rx_mbps"] in {0.0, 4.0}


def test_current_traffic_preserves_zero_and_returns_null_without_fresh_values():
    assert _aggregate_current_traffic([
        {"freshness": "fresh", "rx_mbps": 0.0, "tx_mbps": None},
    ]) == (0.0, None)
    assert _aggregate_current_traffic([
        {"freshness": "stale", "rx_mbps": 9.0, "tx_mbps": 4.0},
    ]) == (None, None)


def test_naive_interface_timestamp_is_utc_not_ist():
    value = _overview_timestamp(datetime(2026, 9, 18, 6, 0, 0))
    assert value == datetime(2026, 9, 18, 6, 0, 0, tzinfo=timezone.utc)


def test_capability_network_counts_use_successful_real_entries_only():
    def cap(device_id, **modules):
        return SimpleNamespace(device_id=device_id, capability_detail={
            name: {"collection_status": status, "data": data}
            for name, (status, data) in modules.items()
        })
    counts = _overview_network_counts([
        cap(283,
            lldp=("SUCCESS", {"neighbors": [{"local_port": "Gi1", "remote_device": "r1"}]}),
            cdp=("SUCCESS", {"neighbors": [{"local_port": "Gi1", "remote_device": "r1"}]}),
            vlan=("SUCCESS", {"vlans": [{"vlan_id": 1}, {"vlan_id": 2}]}),
            routing=("SUCCESS", {"routes": [{"destination": "0/0"}]}),
            arp=("SUCCESS", {"entries": [{"ip_address": "1.1.1.1"}]}),
            mac_table=("SUCCESS", {"entries": [{"mac": "aa"}, {"mac": "bb"}]})),
        cap(284, vlan=("NOT_SUPPORTED", {"vlans": [{"vlan_id": 3}]})),
    ])
    assert counts == {"lldp_neighbors": 1, "vlan_count": 2, "routing_entries": 1,
                      "arp_entries": 1, "mac_entries": 2}
