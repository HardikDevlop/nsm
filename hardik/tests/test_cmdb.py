from datetime import datetime
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.api.cmdb_routes import CITypePayload, CIPayload, CIRelationshipPayload, TopologyLinksPayload, router
from backend.database.migrations import MIGRATIONS
from backend.cmdb.service import create_relationship, sync_inventory_relationships, sync_topology_relationships
from backend.database.session import Base
from backend.models import APMApplication, APMService, CIHistory, CIType, CIRelationship, ConfigurationItem, Device, Interface
from backend.models.identity import DeviceIdentity
from backend.models.snmp import DeviceInterface, DeviceInventory, LLDPNeighbor
from backend.cmdb.service import reconcile_cmdb


def test_cmdb_models_keep_existing_inventory_links():
    assert CIType.__tablename__ == "cmdb_ci_types"
    assert ConfigurationItem.__tablename__ == "cmdb_configuration_items"
    assert CIRelationship.__tablename__ == "cmdb_ci_relationships"
    assert CIHistory.__tablename__ == "cmdb_ci_history"
    columns = ConfigurationItem.__table__.columns
    assert {"device_id", "interface_id", "site_id", "application_id", "owner_user_id"}.issubset(columns.keys())


def test_ci_payload_enforces_lifecycle_and_bounded_fields():
    item = CIPayload(ci_type_id=1, name="edge-router", lifecycle_state="active", attributes={"role": "edge"})
    assert item.lifecycle_state == "active"
    with pytest.raises(ValueError):
        CIPayload(ci_type_id=1, name="edge-router", lifecycle_state="unknown")


def test_relationship_payload_requires_a_target():
    relation = CIRelationshipPayload(target_ci_id=2, relationship_type="runs-on")
    assert relation.target_ci_id == 2
    with pytest.raises(ValueError):
        CIRelationshipPayload(target_ci_id=0, relationship_type="runs-on")


def test_ci_type_defaults_are_safe():
    ci_type = CITypePayload(name="Network Device")
    assert ci_type.category == "custom"


def test_cmdb_routes_cover_inventory_lifecycle_and_history():
    paths = {route.path for route in router.routes}
    assert {
        "/api/v1/cmdb/types",
        "/api/v1/cmdb/items",
        "/api/v1/cmdb/items/{ci_id}",
        "/api/v1/cmdb/items/{ci_id}/history",
        "/api/v1/cmdb/items/{ci_id}/relationships",
        "/api/v1/cmdb/relationships/sync",
        "/api/v1/cmdb/sync",
    }.issubset(paths)
    assert "/api/v1/cmdb/relationships/sync/topology" in paths


def test_cmdb_migration_is_registered_after_existing_migrations():
    ids = [migration.migration_id for migration in MIGRATIONS]
    assert ids[-1] == "20260831_0030_cmdb_reconciliation"


def test_topology_sync_maps_device_ips_and_skips_unknown_links():
    assert TopologyLinksPayload(links=[{"source": "192.0.2.1", "target": "192.0.2.2"}]).links
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        now = datetime.utcnow()
        db.add_all([
            Device(hostname="router", ip_address="192.0.2.1", created_at=now),
            Device(hostname="server", ip_address="192.0.2.2", created_at=now),
        ])
        db.commit()
        result = sync_topology_relationships(db, [
            {"source": "192.0.2.1", "target": "192.0.2.2"},
            {"source": "192.0.2.1", "target": "198.51.100.10"},
        ])
        assert result == {"relationships_created": 1, "links_skipped": 1}
        assert sync_topology_relationships(db, [{"source": "192.0.2.1", "target": "192.0.2.2"}])["relationships_created"] == 0


def test_relationships_reject_duplicates_and_cycles():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        now = datetime.utcnow()
        ci_type = CIType(name="custom", category="custom", created_at=now, updated_at=now)
        db.add(ci_type)
        db.flush()
        first = ConfigurationItem(ci_type_id=ci_type.id, name="one", created_at=now, updated_at=now)
        second = ConfigurationItem(ci_type_id=ci_type.id, name="two", created_at=now, updated_at=now)
        db.add_all([first, second])
        db.flush()
        db.add(create_relationship(db, first.id, second.id, "depends_on"))
        db.commit()
        with pytest.raises(ValueError, match="already exists"):
            create_relationship(db, first.id, second.id, "depends_on")
        with pytest.raises(ValueError, match="circular"):
            create_relationship(db, second.id, first.id, "depends_on")


def test_inventory_sync_creates_only_proven_relationships():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        now = datetime.utcnow()
        device = Device(hostname="edge-1", ip_address="192.0.2.1", created_at=now)
        db.add(device)
        db.flush()
        db.add(Interface(device_id=device.id, interface_name="eth0", last_updated=now))
        application = APMApplication(name="orders", environment="production", created_at=now, updated_at=now)
        db.add(application)
        db.flush()
        db.add(APMService(application_id=application.id, name="orders-api", service_key="orders-api", device_id=device.id, created_at=now, updated_at=now))
        db.commit()
        result = sync_inventory_relationships(db)
        assert result["configuration_items"] == 3
        assert result["relationships_created"] == 2
        assert sync_inventory_relationships(db)["relationships_created"] == 0


def test_reconciliation_updates_source_fields_idempotently_without_secrets():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        now = datetime.utcnow()
        device = Device(hostname="core-old", ip_address="192.0.2.10", model="old-model", status="online", created_at=now)
        db.add(device)
        db.flush()
        db.add(DeviceIdentity(device_id=device.id, hostname="core-old", model="old-model", vendor="ExampleVendor", discovered_at=now))
        db.add(DeviceInventory(device_id=device.id, serial_number="SER-1", model="old-model", firmware="1.0", created_at=now, updated_at=now))
        db.commit()

        first = reconcile_cmdb(db)
        ci = db.query(ConfigurationItem).filter_by(external_key=f"device:{device.id}").one()
        assert first["created"] == 1
        assert ci.attributes["nms"]["vendor"] == "ExampleVendor"
        assert ci.attributes["nms"]["serial_number"] == "SER-1"
        assert "password" not in json.dumps(ci.attributes).lower()

        second = reconcile_cmdb(db)
        assert second["created"] == 0
        assert second["updated"] == 0
        assert second["unchanged"] == 1
        assert db.query(CIHistory).filter_by(ci_id=ci.id).count() == 0

        device.hostname = "core-new"
        device.ip_address = "192.0.2.11"
        device.model = "new-model"
        identity = db.query(DeviceIdentity).filter_by(device_id=device.id).one()
        identity.hostname = "core-new"
        identity.model = "new-model"
        db.commit()
        third = reconcile_cmdb(db)
        db.refresh(ci)
        assert third["updated"] == 1
        assert ci.name == "core-new"
        assert ci.attributes["nms"]["ip_address"] == "192.0.2.11"
        assert ci.last_synchronized is not None
        assert db.query(CIHistory).filter_by(ci_id=ci.id).count() >= 1


def test_reconciliation_uses_normalized_interfaces_and_persisted_lldp():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        now = datetime.utcnow()
        first = Device(hostname="switch-a", ip_address="192.0.2.20", created_at=now)
        second = Device(hostname="switch-b", ip_address="192.0.2.21", created_at=now)
        db.add_all([first, second])
        db.flush()
        db.add(DeviceInterface(device_id=first.id, if_index=7, name="Gi0/7", status="UP", speed_bps=1000000000))
        db.add(LLDPNeighbor(device_id=first.id, remote_device="switch-b", remote_port="Gi0/1", status="supported"))
        db.commit()

        result = reconcile_cmdb(db)
        first_ci = db.query(ConfigurationItem).filter_by(external_key=f"device:{first.id}").one()
        interface_ci = db.query(ConfigurationItem).filter_by(external_key="interface:1").one()
        second_ci = db.query(ConfigurationItem).filter_by(external_key=f"device:{second.id}").one()
        assert result["relationships_created"] == 2
        assert interface_ci.attributes["nms"]["if_index"] == 7
        assert db.query(CIRelationship).filter_by(source_ci_id=first_ci.id, target_ci_id=interface_ci.id, relationship_type="contains").count() == 1
        assert db.query(CIRelationship).filter_by(source_ci_id=first_ci.id, target_ci_id=second_ci.id, relationship_type="topology_link").count() == 1


def test_reconciliation_retains_offline_and_retires_deleted_devices():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        now = datetime.utcnow()
        device = Device(hostname="edge", ip_address="192.0.2.30", status="offline", created_at=now)
        db.add(device)
        db.commit()
        reconcile_cmdb(db)
        ci = db.query(ConfigurationItem).filter_by(external_key=f"device:{device.id}").one()
        assert ci.lifecycle_state == "active"
        assert ci.attributes["nms"]["operational_status"] == "offline"

        device.deleted_at = now
        db.commit()
        reconcile_cmdb(db)
        db.refresh(ci)
        assert ci.lifecycle_state == "retired"
        assert ci.deleted_at is None


def test_reconciliation_does_not_overwrite_manual_ci():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        now = datetime.utcnow()
        device = Device(hostname="source-name", ip_address="192.0.2.40", created_at=now)
        db.add(device)
        db.flush()
        ci_type = CIType(name="custom", category="custom", created_at=now, updated_at=now)
        db.add(ci_type)
        db.flush()
        manual = ConfigurationItem(ci_type_id=ci_type.id, name="manual-label", device_id=device.id, attributes={"owner_note": "keep"}, created_at=now, updated_at=now)
        db.add(manual)
        db.commit()

        reconcile_cmdb(db)
        db.refresh(manual)
        assert manual.name == "manual-label"
        assert manual.attributes["owner_note"] == "keep"
        assert db.query(ConfigurationItem).filter_by(external_key=f"device:{device.id}").count() == 1
