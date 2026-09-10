from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.manual_topology_routes import _link_key, _observed_links
from backend.api.snmp_device_routes import _persist_topology_snapshot, _topology_revision, get_snmp_topology
from backend.database.session import Base
from backend.models import Device  # noqa: F401
from backend.models.identity import DeviceCapabilities  # noqa: F401


def test_manual_topology_link_key_is_direction_independent_and_normalized():
    first = {"from": "A", "fromPort": " Gi1 ", "to": "B", "toPort": "Eth0"}
    reverse = {"from": "b", "fromPort": " eth0", "to": "a", "toPort": "gi1 "}
    assert _link_key(first) == _link_key(reverse)


def test_manual_topology_observed_links_require_port_evidence():
    payload = {
        "devices": [
            {"id": "manual-a", "backendId": 1, "name": "core"},
            {"id": "manual-b", "backendId": 2, "name": "edge"},
        ]
    }
    links = _observed_links({"links": [{"source_node": "1", "target_node": "2"}]}, payload)
    assert links == []

    links = _observed_links({"links": [{
        "source_node": "1", "target_node": "2",
        "source_port": "Gi1", "target_port": "Eth0", "evidence_source": "lldp",
    }]}, payload)
    assert links[0]["evidence_available"] is True
    assert links[0]["evidence_source"] == "lldp"

    # MAC/ARP can prove the monitored switch-side port while the endpoint's
    # local port is unavailable. That is still sufficient physical evidence.
    links = _observed_links({"links": [{
        "source_node": "1", "target_node": "2", "source_port": "1",
        "protocol": "mac_table",
    }]}, payload)
    assert links[0]["fromPort"] == "1"
    assert links[0]["toPort"] == ""
    assert links[0]["evidence_available"] is True


def test_live_topology_snapshot_survives_reload_and_rejects_older_data():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    db.add_all([
        Device(id=7, hostname="core", ip_address="192.0.2.7", status="online"),
        Device(id=8, hostname="gateway", ip_address="192.0.2.8", status="online"),
    ])
    db.commit()

    latest = "2026-09-01T08:00:00+00:00"
    devices = [{"id": "7", "hostname": "core"}]
    links = [{"source_node": "7", "target_node": "8", "verified": True}]
    assert _persist_topology_snapshot(
        db, 7, [{"id": "old"}], [], "2026-09-01T07:00:00+00:00", source="collector"
    )
    assert _persist_topology_snapshot(db, 7, devices, links, latest)
    db.commit()

    # A remount/reload reads the same persisted source used by normal GETs.
    stored = db.query(DeviceCapabilities).filter_by(device_id=7).one()
    snapshot = stored.capability_detail["topology"]
    assert snapshot["timestamp"] == latest
    assert snapshot["source"] == "live_refresh"
    assert snapshot["data"] == {"nodes": devices, "links": links}
    normal_get = get_snmp_topology(device_id=None, refresh=False, db=db, _=None)
    assert normal_get["devices"] == devices
    assert normal_get["links"] == links

    # A newer snapshot on another collection root becomes the read source.
    assert _persist_topology_snapshot(
        db,
        8,
        [{"id": "old-root"}],
        [],
        "2026-09-01T09:00:00+00:00",
        source="collector",
    )
    db.commit()
    normal_get = get_snmp_topology(device_id=None, refresh=False, db=db, _=None)
    assert normal_get["devices"] == [{"id": "old-root"}]
    assert normal_get["links"] == []

    older = "2026-09-01T07:59:59+00:00"
    assert not _persist_topology_snapshot(db, 7, [{"id": "old"}], [], older)
    db.commit()
    reloaded = db.query(DeviceCapabilities).filter_by(device_id=7).one()
    assert reloaded.capability_detail["topology"]["timestamp"] == latest

    # The persisted timestamp is ISO-compatible and can be compared by the API.
    assert datetime.fromisoformat(reloaded.capability_detail["topology"]["collected_at"])


def test_topology_revision_changes_when_shared_device_is_edited():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        device = Device(hostname="before", ip_address="192.0.2.20", status="online")
        db.add(device)
        db.commit()
        before = _topology_revision(db)["revision"]
        device.hostname = "after"
        db.commit()
        assert _topology_revision(db)["revision"] != before


def test_topology_exposes_authenticated_live_sync_stream():
    from backend.api.snmp_device_routes import router
    assert "/api/v1/snmp/topology/stream" in {route.path for route in router.routes}


def test_live_topology_matches_endpoint_interface_mac_and_port_metadata(monkeypatch):
    from backend.api import snmp_device_routes as routes
    from backend.models.identity import DeviceIdentity
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        db.add_all([
            Device(id=7, hostname="core-switch", ip_address="192.0.2.7", status="online"),
            Device(id=8, hostname="NVR", ip_address="192.0.2.8", mac_address="72:AA:BA:65:8D:7B", status="online"),
        ])
        db.flush()
        db.add(DeviceIdentity(device_id=8, mac_addresses=["72:AA:BA:65:8D:7B", "E0:2E:FE:5A:7F:2A"]))
        db.commit()
        monkeypatch.setattr(routes, "_live_collect", lambda *args, **kwargs: {"collectors": {"topology": {
            "supported": True, "timestamp": "2026-09-09T10:44:54+00:00", "data": {
                "nodes": [{"id": "chassis-core"}, {"id": "E0:2E:FE:5A:7F:2A", "mac": "E0:2E:FE:5A:7F:2A"}],
                "links": [{"source_node": "chassis-core", "target_node": "E0:2E:FE:5A:7F:2A", "source_port": "7", "target_port": "eth0", "interface": {"name": "GigabitEthernet7"}, "protocol": "lldp", "verified": True}],
            },
        }}})
        live = routes.get_snmp_topology(device_id=None, refresh=True, db=db, _=None)
        assert live["links"][0]["target_node"] == "8"
        observed = _observed_links(live, {"devices": [{"id": "device-7", "backendId": 7}, {"id": "device-8", "backendId": 8}]})
        assert observed[0]["to"] == "device-8"
        assert observed[0]["fromPort"] == "GigabitEthernet7"
        assert observed[0]["toPort"] == "eth0"
        assert observed[0]["evidence_source"] == "lldp"
        assert observed[0]["last_verified_at"]
