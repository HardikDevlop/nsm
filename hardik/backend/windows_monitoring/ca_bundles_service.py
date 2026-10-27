"""Site-scoped Windows CA bundle metadata service.

Caller-facing authorization is deliberately left to the future API layer;
these methods enforce database ownership and trust-state invariants.
"""

from sqlalchemy.orm import Session

from .ca_bundles_repository import (
    can_delete_ca_bundle,
    create_ca_bundle,
    create_device_ca_assignment,
    delete_ca_bundle,
    get_active_device_ca_assignment,
    get_ca_bundle,
    get_ca_bundle_by_fingerprint,
    list_site_ca_bundles,
)
from .models import WindowsCABundle, WindowsCABundleStatus, WindowsDeviceCAAssignment, windows_now
from backend.models import Device
from .effective_trust import normalize_windows_timestamp


class WindowsCABundleError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class WindowsCABundleService:
    def __init__(self, db: Session):
        self.db = db

    def create_metadata(self, **values) -> WindowsCABundle:
        return create_ca_bundle(self.db, **values)

    def get(self, bundle_id: int, *, site_id: int | None = None) -> WindowsCABundle | None:
        return get_ca_bundle(self.db, bundle_id, site_id=site_id)

    def list_for_site(self, site_id: int) -> list[WindowsCABundle]:
        return list_site_ca_bundles(self.db, site_id)

    def duplicate_for_site(self, site_id: int, fingerprint: str) -> WindowsCABundle | None:
        return get_ca_bundle_by_fingerprint(self.db, site_id, fingerprint)

    def revoke(self, *, bundle_id: int, site_id: int, revoked_by: int | None = None) -> WindowsCABundle:
        bundle = get_ca_bundle(self.db, bundle_id, site_id=site_id)
        if bundle is None:
            raise WindowsCABundleError("CA_BUNDLE_NOT_FOUND", "CA bundle does not exist")
        if get_active_device_ca_assignment(self.db, bundle.id) is not None:
            raise WindowsCABundleError("CA_BUNDLE_IN_USE", "CA bundle is actively assigned to a device")
        if bundle.status == WindowsCABundleStatus.REVOKED.value:
            raise WindowsCABundleError("CA_BUNDLE_ALREADY_REVOKED", "CA bundle is already revoked")
        bundle.status = WindowsCABundleStatus.REVOKED.value
        bundle.revoked_at = windows_now()
        bundle.revoked_by = revoked_by
        self.db.flush()
        return bundle

    def assign(self, *, device_id: int, bundle_id: int, assigned_by: int | None = None) -> WindowsDeviceCAAssignment:
        device = self.db.get(Device, device_id)
        if device is None:
            raise WindowsCABundleError("DEVICE_NOT_FOUND", "Device does not exist")
        bundle = get_ca_bundle(self.db, bundle_id, site_id=device.site_id)
        if bundle is None:
            raise WindowsCABundleError("CA_BUNDLE_NOT_FOUND", "CA bundle is not available for the device site")
        if bundle.status != WindowsCABundleStatus.ACTIVE.value:
            raise WindowsCABundleError("CA_BUNDLE_NOT_ASSIGNABLE", "CA bundle is not active")
        if bundle.not_after is not None and normalize_windows_timestamp(bundle.not_after) <= normalize_windows_timestamp(windows_now()):
            raise WindowsCABundleError("CA_BUNDLE_EXPIRED", "CA bundle is expired")
        if get_active_device_ca_assignment(self.db, device_id) is not None:
            raise WindowsCABundleError("CA_ASSIGNMENT_EXISTS", "Device already has an active CA assignment")
        return create_device_ca_assignment(
            self.db,
            device_id=device_id,
            ca_bundle_id=bundle.id,
            assigned_by=assigned_by,
            assigned_at=windows_now(),
        )

    def unassign(self, device_id: int) -> WindowsDeviceCAAssignment:
        assignment = get_active_device_ca_assignment(self.db, device_id)
        if assignment is None:
            raise WindowsCABundleError("CA_ASSIGNMENT_NOT_FOUND", "Device has no active CA assignment")
        assignment.unassigned_at = windows_now()
        self.db.flush()
        return assignment

    def can_delete(self, bundle_id: int) -> bool:
        return can_delete_ca_bundle(self.db, bundle_id)

    def delete(self, bundle_id: int) -> None:
        bundle = get_ca_bundle(self.db, bundle_id)
        if bundle is None:
            raise WindowsCABundleError("CA_BUNDLE_NOT_FOUND", "CA bundle does not exist")
        if not can_delete_ca_bundle(self.db, bundle_id):
            raise WindowsCABundleError("CA_BUNDLE_IN_USE", "CA bundle is actively assigned to a device")
        delete_ca_bundle(self.db, bundle)
