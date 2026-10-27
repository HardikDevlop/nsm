from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.database.migrations import MIGRATIONS
from backend.windows_monitoring.ca_bundles_service import WindowsCABundleError, WindowsCABundleService
from backend.windows_monitoring.models import WindowsCABundle, WindowsCABundleStatus, WindowsDeviceCAAssignment


def test_ca_bundle_model_contains_metadata_only_and_constraints():
    columns = WindowsCABundle.__table__.columns
    assert "storage_key" in columns and "content_sha256" in columns
    assert "private_key" not in columns and "pem_contents" not in columns
    assert {fk.target_fullname for fk in columns.site_id.foreign_keys} == {"sites.id"}
    assert {fk.target_fullname for fk in columns.created_by.foreign_keys} == {"users.id"}
    assert {fk.target_fullname for fk in columns.revoked_by.foreign_keys} == {"users.id"}


def test_assignment_model_has_foreign_keys_and_partial_active_unique_index():
    columns = WindowsDeviceCAAssignment.__table__.columns
    assert {fk.target_fullname for fk in columns.device_id.foreign_keys} == {"devices.id"}
    assert {fk.target_fullname for fk in columns.ca_bundle_id.foreign_keys} == {"windows_ca_bundles.id"}
    indexes = {index.name: index for index in WindowsDeviceCAAssignment.__table__.indexes}
    assert indexes["uq_windows_device_ca_active"].unique is True
    assert str(indexes["uq_windows_device_ca_active"].dialect_options["postgresql"]["where"]) == "unassigned_at IS NULL"


def test_foundation_migration_follows_existing_head():
    ids = [migration.migration_id for migration in MIGRATIONS]
    assert ids.index("20261026_0066_windows_ca_bundle_foundation") < ids.index("20261026_0067_windows_ca_bundle_index_reconciliation")
    assert "CA bundle" in next(item.description for item in MIGRATIONS if item.migration_id == "20261026_0066_windows_ca_bundle_foundation")


def test_windows_ca_index_reconciliation_matches_orm_secondary_indexes():
    migration = next(item for item in MIGRATIONS if item.migration_id == "20261026_0067_windows_ca_bundle_index_reconciliation")
    assert "index" in migration.description.lower()
    assert "20261026_0067" in migration.migration_id


def bundle(status="active", site_id=10, expires=None):
    return SimpleNamespace(id=4, site_id=site_id, status=status, not_after=expires)


def test_assign_rejects_revoked_or_expired_bundle():
    for status, expires, code in [
        ("revoked", None, "CA_BUNDLE_NOT_ASSIGNABLE"),
        ("active", datetime.now() - timedelta(days=1), "CA_BUNDLE_EXPIRED"),
    ]:
        db = Mock()
        db.get.return_value = SimpleNamespace(id=7, site_id=10)
        service = WindowsCABundleService(db)
        service_module = __import__("backend.windows_monitoring.ca_bundles_service", fromlist=["get_ca_bundle"])
        service_module.get_ca_bundle = Mock(return_value=bundle(status=status, expires=expires))
        service_module.get_active_device_ca_assignment = Mock(return_value=None)
        with pytest.raises(WindowsCABundleError) as exc:
            service.assign(device_id=7, bundle_id=4)
        assert exc.value.code == code


def test_assign_rejects_cross_site_bundle_and_existing_active_assignment(monkeypatch):
    db = Mock()
    db.get.return_value = SimpleNamespace(id=7, site_id=10)
    service = WindowsCABundleService(db)
    monkeypatch.setattr("backend.windows_monitoring.ca_bundles_service.get_ca_bundle", Mock(return_value=None))
    with pytest.raises(WindowsCABundleError) as exc:
        service.assign(device_id=7, bundle_id=4)
    assert exc.value.code == "CA_BUNDLE_NOT_FOUND"

    monkeypatch.setattr("backend.windows_monitoring.ca_bundles_service.get_ca_bundle", Mock(return_value=bundle()))
    monkeypatch.setattr("backend.windows_monitoring.ca_bundles_service.get_active_device_ca_assignment", Mock(return_value=object()))
    with pytest.raises(WindowsCABundleError) as exc:
        service.assign(device_id=7, bundle_id=4)
    assert exc.value.code == "CA_ASSIGNMENT_EXISTS"


def test_assignment_and_unassignment(monkeypatch):
    db = Mock()
    db.get.return_value = SimpleNamespace(id=7, site_id=10)
    created = SimpleNamespace(device_id=7, ca_bundle_id=4, unassigned_at=None)
    monkeypatch.setattr("backend.windows_monitoring.ca_bundles_service.get_ca_bundle", Mock(return_value=bundle()))
    monkeypatch.setattr("backend.windows_monitoring.ca_bundles_service.get_active_device_ca_assignment", Mock(side_effect=[None, created]))
    monkeypatch.setattr("backend.windows_monitoring.ca_bundles_service.create_device_ca_assignment", Mock(return_value=created))
    service = WindowsCABundleService(db)

    assert service.assign(device_id=7, bundle_id=4).ca_bundle_id == 4
    result = service.unassign(7)
    assert result.unassigned_at is not None
    db.flush.assert_called()


def test_deletion_is_blocked_while_bundle_is_active(monkeypatch):
    db = Mock()
    bundle_item = bundle()
    monkeypatch.setattr("backend.windows_monitoring.ca_bundles_service.get_ca_bundle", Mock(return_value=bundle_item))
    monkeypatch.setattr("backend.windows_monitoring.ca_bundles_service.can_delete_ca_bundle", Mock(return_value=False))
    with pytest.raises(WindowsCABundleError) as exc:
        WindowsCABundleService(db).delete(4)
    assert exc.value.code == "CA_BUNDLE_IN_USE"
