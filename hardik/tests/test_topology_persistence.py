from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.snmp_device_routes import _persist_topology_snapshot, get_snmp_topology
from backend.database.session import Base
from backend.models import Device  # noqa: F401
from backend.models.identity import DeviceCapabilities  # noqa: F401


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
