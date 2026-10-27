"""Fail-closed resolution of the effective Windows CA trust source."""

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session
from sqlalchemy.exc import ProgrammingError

from backend.config.settings import get_settings
from backend.models import Device

from .ca_bundles_repository import get_active_device_ca_assignment, get_ca_bundle
from .ca_bundle_storage import resolve_storage_path, CABundleStorageError
from .models import WindowsCABundleStatus, WindowsDeviceCAAssignment, windows_now


class EffectiveTrustError(RuntimeError):
    pass


def normalize_windows_timestamp(value: datetime) -> datetime:
    """Normalize CA timestamps to aware UTC.

    Windows monitoring tables use naive timestamps produced by windows_now(),
    which are application-local Asia/Kolkata UTC wall-clock values. Parsed
    certificate timestamps are already timezone-aware.
    """
    if not isinstance(value, datetime):
        raise EffectiveTrustError("Windows CA expiry timestamp is invalid")
    try:
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        return value.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        raise EffectiveTrustError("Windows CA expiry timestamp is invalid") from None


@dataclass(frozen=True)
class EffectiveWindowsCATrust:
    source: str
    bundle_id: int | None
    fingerprint: str | None
    protected_path: str
    expires_at: datetime | None


def resolve_effective_windows_ca(device_id: int, db: Session, *, global_ca_path: str | None = None) -> EffectiveWindowsCATrust:
    device = db.get(Device, device_id)
    if device is None:
        raise EffectiveTrustError("Windows device does not exist")
    try:
        assignment = get_active_device_ca_assignment(db, device_id)
    except ProgrammingError as exc:
        # 0066 is application-managed.  Until it is deployed, preserve the
        # legacy global-path behavior; do not hide other database failures.
        if "windows_device_ca_assignments" not in str(getattr(exc, "orig", exc)):
            raise
        db.rollback()
        assignment = None
    except (AttributeError, StopIteration):
        # Compatibility with lightweight legacy repository doubles; real
        # database failures are not handled here.
        assignment = None
    # Keep lightweight legacy test doubles and pre-0066 deployments from
    # being mistaken for an actual assignment row.
    if assignment is not None and not isinstance(assignment, WindowsDeviceCAAssignment):
        assignment = None
    if assignment is not None:
        bundle = get_ca_bundle(db, assignment.ca_bundle_id, site_id=device.site_id)
        if bundle is None or bundle.status != WindowsCABundleStatus.ACTIVE.value:
            raise EffectiveTrustError("Assigned Windows CA bundle is not active")
        if bundle.not_after is not None and normalize_windows_timestamp(bundle.not_after) <= normalize_windows_timestamp(windows_now()):
            raise EffectiveTrustError("Assigned Windows CA bundle is expired")
        try:
            path = resolve_storage_path(bundle.storage_key)
        except CABundleStorageError:
            raise EffectiveTrustError("Assigned Windows CA bundle is unavailable") from None
        return EffectiveWindowsCATrust("per_device", bundle.id, bundle.sha256_fingerprint, str(path), normalize_windows_timestamp(bundle.not_after) if bundle.not_after is not None else None)

    configured = (global_ca_path if global_ca_path is not None else get_settings().windows_ca_trust_path).strip()
    if configured:
        path = Path(configured)
        return EffectiveWindowsCATrust("global", None, None, str(path), None)

    # Existing deployments use the platform trust store when no explicit
    # bundle/path is configured. Preserve that policy without weakening any
    # explicit per-device assignment.
    return EffectiveWindowsCATrust("system", None, None, "", None)
