"""Minimal secured Windows credential endpoints."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File, Form
from fastapi import Request
import logging
from time import perf_counter
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.auth.authorization import can_access_site
from backend.dependencies import require_permission
from backend.models import Device
from backend.database.session import get_db
from backend.services.audit import record_audit_event

from .models import WindowsCredential, WindowsSystemSnapshot, WindowsMetricSnapshot, WindowsEventLog, WindowsHardwareSnapshot, windows_now
from .cim import WindowsCIMClient, CIMError
from backend.utils.crypto import decrypt_secret
from backend.config.settings import get_settings
from .schemas import WindowsCredentialCreate, WindowsCredentialRead, WindowsCredentialUpdate, WindowsHardwareSnapshotRead, WindowsUSBInventoryRead
from dataclasses import asdict
import errno
import socket
import ssl
from .service import WindowsCredentialService
from .persistence import get_hardware_snapshot, serialize_hardware_information, upsert_hardware_snapshot, upsert_network_snapshot
from .persistence import latest_system_event_time, list_system_events, save_system_events
from .events import SystemEventError, collect_system_events
from .winrm import WinRMHTTPSAdapter
from .sensors import LibreHardwareMonitorProvider, NativeCIMSensorProvider
from .ca_bundle_parser import parse_ca_bundle, CABundleParseError, MAX_BUNDLE_BYTES
from .ca_bundle_storage import store_pem_bytes, delete_stored_bundle, CABundleStorageError
from .ca_bundles_service import WindowsCABundleService, WindowsCABundleError
from .ca_bundles_repository import get_active_device_ca_assignment
from .effective_trust import resolve_effective_windows_ca, EffectiveTrustError
from .models import WindowsCABundleStatus

router = APIRouter(prefix="/windows", tags=["Windows Monitoring"])
service = WindowsCredentialService()
logger = logging.getLogger(__name__)
# Phase 2 deliberately exposes only the four manually-triggered modules.  The
# generic CIM code for future modules remains in place, but is not reachable.
WINDOW_MODULES = {"system", "cpu", "memory", "disk", "network"}
TCP_DIAGNOSTIC_TIMEOUT_SECONDS = 5.0
TLS_DIAGNOSTIC_TIMEOUT_SECONDS = 5.0
TLS_EXPIRING_SOON_DAYS = 30
CA_UPLOAD_CHUNK_SIZE = 64 * 1024


def _diagnostic_stage(step: str, status: str, category: str, message: str, started: float) -> dict[str, object]:
    return {
        "step": step,
        "status": status,
        "category": category,
        "message": message,
        "duration_ms": round((perf_counter() - started) * 1000, 1),
    }


def _ca_bundle_response(bundle, certificate_count: int | None = None) -> dict:
    return {
        "id": bundle.id, "site_id": bundle.site_id, "name": bundle.name,
        "description": bundle.description, "sha256_fingerprint": bundle.sha256_fingerprint,
        "content_sha256": bundle.content_sha256, "subject": bundle.subject,
        "issuer": bundle.issuer, "serial_number": bundle.serial_number,
        "not_before": bundle.not_before, "not_after": bundle.not_after,
        "is_ca": bundle.is_ca, "is_self_signed": bundle.is_self_signed,
        "trust_type": bundle.trust_type, "status": bundle.status,
        "certificate_count": certificate_count, "created_by": bundle.created_by,
        "created_at": bundle.created_at, "updated_at": bundle.updated_at,
        "revoked_at": bundle.revoked_at, "revoked_by": bundle.revoked_by,
    }


def _read_ca_upload(upload: UploadFile) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while total <= MAX_BUNDLE_BYTES:
        chunk = upload.file.read(CA_UPLOAD_CHUNK_SIZE)
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > MAX_BUNDLE_BYTES:
            raise HTTPException(status_code=413, detail="CA bundle exceeds the maximum upload size")
        chunks.append(chunk)
    raise HTTPException(status_code=413, detail="CA bundle exceeds the maximum upload size")


def _effective_ca_path(db: Session, device_id: int) -> str:
    try:
        return resolve_effective_windows_ca(
            device_id, db,
            global_ca_path=get_settings().windows_ca_trust_path,
        ).protected_path
    except EffectiveTrustError as exc:
        raise HTTPException(status_code=502, detail="Windows CA trust configuration is unavailable") from exc


@router.post("/ca-bundles", status_code=status.HTTP_201_CREATED)
def create_ca_bundle(
    site_id: int = Form(...),
    name: str = Form(...),
    description: str | None = Form(None),
    certificate: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_permission("windows_ca:manage")),
):
    if site_id <= 0 or not can_access_site(user, site_id):
        raise HTTPException(status_code=404, detail="Site not found")
    name = name.strip()
    if not name or len(name) > 160 or (description is not None and len(description) > 2000):
        raise HTTPException(status_code=422, detail="Invalid CA bundle metadata")
    try:
        pem = _read_ca_upload(certificate)
        parsed = parse_ca_bundle(pem)
    except HTTPException:
        raise
    except CABundleParseError as exc:
        raise HTTPException(status_code=422, detail=exc.message)
    fingerprint = parsed.certificates[0].sha256_fingerprint if parsed.certificate_count == 1 else parsed.content_sha256
    service = WindowsCABundleService(db)
    if service.duplicate_for_site(site_id, fingerprint) is not None:
        raise HTTPException(status_code=409, detail="An equivalent CA bundle already exists for this site")
    storage_key = None
    try:
        storage_key = store_pem_bytes(pem)
        bundle = service.create_metadata(
            site_id=site_id, name=name, description=description, storage_key=storage_key,
            sha256_fingerprint=fingerprint, content_sha256=parsed.content_sha256,
            subject=parsed.subject, issuer=parsed.issuer, serial_number=parsed.serial_number,
            not_before=parsed.not_before, not_after=parsed.not_after, is_ca=parsed.is_ca,
            is_self_signed=parsed.is_self_signed, trust_type=parsed.trust_type,
            status=WindowsCABundleStatus.ACTIVE.value, created_by=user.id,
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        if storage_key:
            try:
                delete_stored_bundle(storage_key)
            except Exception:
                logger.warning("CA bundle cleanup failed after database error", extra={"event": "windows_ca_orphan_cleanup_failed"})
        raise HTTPException(status_code=500, detail="CA bundle could not be saved")
    except CABundleStorageError:
        raise HTTPException(status_code=500, detail="CA bundle storage is unavailable")
    record_audit_event(
        db, actor=user, action="windows_ca_bundle.create", resource_type="windows_ca_bundle",
        resource_id=bundle.id, site_id=site_id, outcome="success",
        metadata={"certificate_count": parsed.certificate_count},
    )
    return _ca_bundle_response(bundle, parsed.certificate_count)


@router.get("/ca-bundles")
def list_ca_bundles(site_id: int, db: Session = Depends(get_db), user=Depends(require_permission("windows_ca:read"))):
    if site_id <= 0 or not can_access_site(user, site_id):
        raise HTTPException(status_code=404, detail="Site not found")
    return [_ca_bundle_response(item) for item in WindowsCABundleService(db).list_for_site(site_id)]


@router.get("/ca-bundles/{bundle_id}")
def get_ca_bundle(bundle_id: int, db: Session = Depends(get_db), user=Depends(require_permission("windows_ca:read"))):
    bundle = WindowsCABundleService(db).get(bundle_id)
    if bundle is None or not can_access_site(user, bundle.site_id):
        raise HTTPException(status_code=404, detail="CA bundle not found")
    return _ca_bundle_response(bundle)


@router.post("/ca-bundles/{bundle_id}/revoke")
def revoke_ca_bundle(bundle_id: int, db: Session = Depends(get_db), user=Depends(require_permission("windows_ca:manage"))):
    current = WindowsCABundleService(db).get(bundle_id)
    if current is None or not can_access_site(user, current.site_id):
        raise HTTPException(status_code=404, detail="CA bundle not found")
    try:
        bundle = WindowsCABundleService(db).revoke(bundle_id=bundle_id, site_id=current.site_id, revoked_by=user.id)
        db.commit()
    except WindowsCABundleError as exc:
        db.rollback()
        raise HTTPException(status_code=409 if exc.code == "CA_BUNDLE_IN_USE" else 422, detail=exc.message)
    record_audit_event(
        db, actor=user, action="windows_ca_bundle.revoke", resource_type="windows_ca_bundle",
        resource_id=bundle.id, site_id=bundle.site_id, outcome="success",
    )
    return _ca_bundle_response(bundle)


def _assignment_response(device_id: int, assignment, bundle) -> dict:
    return {
        "device_id": device_id, "trust_source": "per_device", "bundle_id": bundle.id,
        "bundle_name": bundle.name, "fingerprint": bundle.sha256_fingerprint,
        "expires_at": bundle.not_after,
    }


@router.get("/devices/{device_id}/ca-bundle")
def get_device_ca_bundle(device_id: int, db: Session = Depends(get_db), user=Depends(require_permission("windows_ca:read"))):
    device = _device(db, device_id, user)
    assignment = get_active_device_ca_assignment(db, device.id)
    if assignment is None:
        try:
            resolved = resolve_effective_windows_ca(device.id, db)
        except EffectiveTrustError:
            return {"device_id": device.id, "trust_source": "unavailable", "bundle_id": None, "bundle_name": None, "fingerprint": None, "expires_at": None}
        if resolved.source == "global":
            try:
                global_path = Path(resolved.protected_path)
                if not global_path.is_file() or not global_path.stat().st_size:
                    raise OSError
                ssl.create_default_context(cafile=str(global_path))
            except (OSError, ssl.SSLError, ValueError):
                return {"device_id": device.id, "trust_source": "unavailable", "bundle_id": None, "bundle_name": None, "fingerprint": None, "expires_at": None}
        return {"device_id": device.id, "trust_source": resolved.source, "bundle_id": None, "bundle_name": None, "fingerprint": None, "expires_at": resolved.expires_at}
    bundle = WindowsCABundleService(db).get(assignment.ca_bundle_id, site_id=device.site_id)
    if bundle is None:
        raise HTTPException(status_code=409, detail="Assigned Windows CA bundle is unavailable")
    try:
        resolve_effective_windows_ca(device.id, db)
    except EffectiveTrustError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _assignment_response(device.id, assignment, bundle)


@router.put("/devices/{device_id}/ca-bundle")
def assign_device_ca_bundle(device_id: int, bundle_id: int, db: Session = Depends(get_db), user=Depends(require_permission("windows_ca:assign"))):
    device = _device(db, device_id, user)
    current = get_active_device_ca_assignment(db, device.id)
    try:
        if current is not None:
            current.unassigned_at = windows_now()
            db.flush()
        assignment = WindowsCABundleService(db).assign(device_id=device.id, bundle_id=bundle_id, assigned_by=user.id)
        db.commit()
    except WindowsCABundleError as exc:
        db.rollback()
        raise HTTPException(status_code=404 if exc.code in {"DEVICE_NOT_FOUND", "CA_BUNDLE_NOT_FOUND"} else 409, detail=exc.message)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="CA bundle assignment conflicts with another active assignment")
    record_audit_event(
        db, actor=user, action="windows_ca_bundle.assign", resource_type="windows_device",
        resource_id=device.id, site_id=device.site_id, outcome="success",
        metadata={"bundle_id": assignment.ca_bundle_id},
    )
    bundle = WindowsCABundleService(db).get(assignment.ca_bundle_id, site_id=device.site_id)
    return _assignment_response(device.id, assignment, bundle)


@router.delete("/devices/{device_id}/ca-bundle")
def unassign_device_ca_bundle(device_id: int, db: Session = Depends(get_db), user=Depends(require_permission("windows_ca:assign"))):
    device = _device(db, device_id, user)
    try:
        assignment = WindowsCABundleService(db).unassign(device.id)
        db.commit()
    except WindowsCABundleError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=exc.message)
    record_audit_event(
        db, actor=user, action="windows_ca_bundle.unassign", resource_type="windows_device",
        resource_id=device.id, site_id=device.site_id, outcome="success",
        metadata={"bundle_id": assignment.ca_bundle_id},
    )
    return {"device_id": device.id, "trust_source": "global", "bundle_id": None, "bundle_name": None, "fingerprint": None, "expires_at": None}


def _fetch_lock(db: Session, device_id: int, module: str) -> None:
    """Claim a transaction-scoped PostgreSQL lock for one fetch target."""
    lock_key = f"nms.windows.fetch:{device_id}:{module}"
    acquired = db.execute(
        text("SELECT pg_try_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": lock_key},
    ).scalar_one()
    if not acquired:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Windows {module} fetch is already in progress",
        )


def _upsert_system_snapshot(db: Session, device_id: int, value: dict) -> WindowsSystemSnapshot:
    collected_at = windows_now()
    statement = pg_insert(WindowsSystemSnapshot).values(
        device_id=device_id,
        collected_at=collected_at,
        system_info=value,
    ).on_conflict_do_update(
        index_elements=[WindowsSystemSnapshot.device_id],
        set_={"collected_at": collected_at, "system_info": value},
    ).returning(WindowsSystemSnapshot.id)
    row_id = db.execute(statement).scalar_one()
    return db.query(WindowsSystemSnapshot).filter(WindowsSystemSnapshot.id == row_id).first()


def _upsert_metric_snapshot(db: Session, device_id: int, module: str, value) -> WindowsMetricSnapshot:
    collected_at = windows_now()
    statement = pg_insert(WindowsMetricSnapshot).values(
        device_id=device_id,
        module=module,
        collected_at=collected_at,
        data=value,
    ).on_conflict_do_update(
        index_elements=[WindowsMetricSnapshot.device_id, WindowsMetricSnapshot.module],
        set_={"collected_at": collected_at, "data": value},
    ).returning(WindowsMetricSnapshot.id)
    row_id = db.execute(statement).scalar_one()
    return db.query(WindowsMetricSnapshot).filter(WindowsMetricSnapshot.id == row_id).one()


def _device(db: Session, device_id: int, user, *, refresh: bool = False) -> Device:
    query = db.query(Device).filter(Device.id == device_id, Device.deleted_at.is_(None))
    if refresh:
        query = query.populate_existing()
    device = query.first()
    if device is None:
        logger.warning("windows_device_lookup_not_found device_id=%s user_id=%s refresh=%s", device_id, getattr(user, "id", None), refresh)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    if not can_access_site(user, device.site_id):
        logger.warning("windows_device_lookup_unauthorized device_id=%s site_id=%s user_id=%s refresh=%s", device_id, device.site_id, getattr(user, "id", None), refresh)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return device


def _credential(db: Session, device_id: int, credential_id: int) -> WindowsCredential:
    credential = db.query(WindowsCredential).filter(
        WindowsCredential.id == credential_id,
        WindowsCredential.device_id == device_id,
    ).first()
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Windows credential not found")
    return credential


def _audit(db: Session, user, action: str, device: Device, credential_id: int | None, outcome: str = "success") -> None:
    record_audit_event(
        db, actor=user, action=action, resource_type="windows_credential", resource_id=credential_id,
        site_id=device.site_id, outcome=outcome, metadata={"device_id": device.id},
    )


def _audit_system_failure(db: Session, user, device: Device, reason: str) -> None:
    try:
        record_audit_event(
            db,
            actor=user,
            action="SYSTEM_FETCH",
            resource_type="windows_device",
            resource_id=device.id,
            site_id=device.site_id,
            outcome="failure",
            failure_reason=reason,
            metadata={"device_id": device.id, "module": "system"},
        )
    except Exception:
        logger.warning("windows_system_fetch failure_audit_failed device_id=%s", device.id, exc_info=True)


def _system_failure_reason(exc: CIMError) -> str:
    if exc.category == "authentication":
        return "credential_unavailable" if exc.message == "Stored Windows credential is unavailable" else "authentication_failed"
    if exc.category == "tls":
        return "tls_validation_failed"
    if exc.category in {"transport", "timeout"}:
        return "winrm_connection_failed"
    return "cim_collection_failed"


def _audit_metric_failure(db: Session, user, device: Device | None, module: str, reason: str) -> None:
    if device is None:
        return
    try:
        record_audit_event(
            db,
            actor=user,
            action=f"{module.upper()}_FETCH",
            resource_type="windows_device",
            resource_id=device.id,
            site_id=device.site_id,
            outcome="failure",
            failure_reason=reason,
            metadata={"device_id": device.id, "module": module},
        )
    except Exception:
        logger.warning("windows_metric_fetch failure_audit_failed device_id=%s module=%s", device.id, module, exc_info=True)


def _metric_failure_reason(exc: CIMError) -> str:
    if exc.category == "authentication":
        return "credential_unavailable" if exc.message == "Stored Windows credential is unavailable" else "authentication_failed"
    if exc.category == "tls":
        return "tls_validation_failed"
    if exc.category in {"transport", "timeout"}:
        return "winrm_connection_failed"
    return "cim_collection_failed"


@dataclass(frozen=True)
class _WindowsConnectionContext:
    device: Device
    credential: WindowsCredential
    host: str
    username: str
    password: str


def _resolve_windows_connection(db: Session, device_id: int, user, *, device: Device | None = None) -> _WindowsConnectionContext:
    """Resolve authorized device and enabled credential without creating a client."""
    device = device or _device(db, device_id, user)
    credential = db.query(WindowsCredential).filter(
        WindowsCredential.device_id == device_id,
        WindowsCredential.enabled.is_(True),
    ).first()
    if credential is None:
        raise HTTPException(status_code=404, detail="Windows credential not found")
    password = decrypt_secret(credential.encrypted_secret)
    if not password:
        raise CIMError("authentication", "Stored Windows credential is unavailable")
    host = credential.connection_host or device.hostname or device.ip_address
    username = f"{credential.domain}\\{credential.username}" if credential.domain else credential.username
    return _WindowsConnectionContext(device, credential, host, username, password)


def _windows_tcp_target(db: Session, device: Device) -> str:
    """Resolve only the target already registered for this Windows device."""
    credential = db.query(WindowsCredential).filter(
        WindowsCredential.device_id == device.id,
    ).first()
    return (getattr(credential, "connection_host", None) if credential else None) or device.hostname or device.ip_address


def _tcp_diagnostic(target: str, *, port: int = 5986) -> dict[str, object]:
    """Perform a bounded TCP probe and expose only safe, stable classifications."""
    started = perf_counter()
    try:
        WinRMHTTPSAdapter._validate_target(target, port)
    except (TypeError, ValueError):
        category, message = "invalid_target", "The registered Windows target is invalid"
    else:
        try:
            with socket.create_connection((target, port), timeout=TCP_DIAGNOSTIC_TIMEOUT_SECONDS):
                category, message = "success", "TCP connection to WinRM HTTPS succeeded"
        except socket.timeout:
            category, message = "timeout", "TCP connection to WinRM HTTPS timed out"
        except socket.gaierror:
            category, message = "dns", "The registered Windows target could not be resolved"
        except ConnectionRefusedError:
            category, message = "refused", "The Windows target refused the TCP connection"
        except OSError as exc:
            if exc.errno == errno.ECONNREFUSED:
                category, message = "refused", "The Windows target refused the TCP connection"
            elif exc.errno in {errno.ETIMEDOUT, errno.EHOSTUNREACH, errno.ENETUNREACH}:
                category, message = "timeout", "TCP connection to WinRM HTTPS could not be established"
            else:
                category, message = "network", "TCP connection to WinRM HTTPS failed"
    return {
        "step": "tcp_connect",
        "status": "PASS" if category == "success" else "FAIL",
        "category": category,
        "message": message,
        "duration_ms": round((perf_counter() - started) * 1000, 1),
    }


@router.post("/devices/{device_id}/diagnostics/tcp")
def diagnose_tcp(device_id: int, db: Session = Depends(get_db), user=Depends(require_permission("devices:update"))):
    """Check only TCP reachability of the registered WinRM HTTPS target."""
    device = _device(db, device_id, user)
    _fetch_lock(db, device_id, "tcp")
    result = _tcp_diagnostic(_windows_tcp_target(db, device), port=5986)
    try:
        record_audit_event(
            db,
            actor=user,
            action="TCP_DIAGNOSTIC",
            resource_type="windows_device",
            resource_id=device.id,
            site_id=device.site_id,
            outcome="success" if result["status"] == "PASS" else "failure",
            failure_reason=None if result["status"] == "PASS" else str(result["category"]),
            metadata={"device_id": device.id, "step": "tcp_connect", "port": 5986},
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("windows_tcp_diagnostic audit_failed device_id=%s", device_id, exc_info=True)
    return result


def _certificate_name(cert: dict, field: str) -> str:
    values = cert.get(field) or ()
    result = []
    for item in values:
        pairs = [item] if len(item) == 2 and isinstance(item[0], str) else item
        result.extend(str(value) for _, value in pairs)
    return ", ".join(result)


def _tls_diagnostic(target: str, *, ca_trust_path: str | None = None, port: int = 5986) -> dict[str, object]:
    """Validate the registered target using a fully verified TLS context."""
    started = perf_counter()
    try:
        WinRMHTTPSAdapter._validate_target(target, port)
    except (TypeError, ValueError):
        category, message = "invalid_target", "The registered Windows target is invalid"
        certificate = None
    else:
        try:
            context = ssl.create_default_context(cafile=ca_trust_path or None)
            context.check_hostname = True
            context.verify_mode = ssl.CERT_REQUIRED
            with socket.create_connection((target, port), timeout=TLS_DIAGNOSTIC_TIMEOUT_SECONDS) as raw_socket:
                with context.wrap_socket(raw_socket, server_hostname=target) as tls_socket:
                    cert = tls_socket.getpeercert()
            san_entries = cert.get("subjectAltName") or ()
            expected_kind = "IP Address" if _is_ip_target(target) else "DNS"
            san_match = any(kind == expected_kind and value == target for kind, value in san_entries)
            not_after = ssl.cert_time_to_seconds(cert["notAfter"])
            expires_at = datetime.fromtimestamp(not_after, timezone.utc)
            days_remaining = int((expires_at - datetime.now(timezone.utc)).total_seconds() // 86400)
            certificate = {
                "subject": _certificate_name(cert, "subject"),
                "issuer": _certificate_name(cert, "issuer"),
                "expires_at": expires_at.isoformat().replace("+00:00", "Z"),
                "days_remaining": days_remaining,
                "san_match": san_match,
            }
            if not san_match:
                category, message = "hostname_mismatch", "The certificate does not contain a matching hostname or IP SAN"
            elif days_remaining <= TLS_EXPIRING_SOON_DAYS:
                category, message = "expiring_soon", "TLS certificate validation succeeded; certificate expires within 30 days"
            else:
                category, message = "success", "TLS certificate validation succeeded"
        except ssl.SSLCertVerificationError as exc:
            verify_code = getattr(exc, "verify_code", None)
            if verify_code == 62:
                category, message = "hostname_mismatch", "TLS certificate hostname validation failed"
            elif verify_code == 10:
                category, message = "expired_certificate", "The TLS certificate is expired"
            elif verify_code == 9:
                category, message = "certificate_not_yet_valid", "The TLS certificate is not yet valid"
            elif verify_code in {20, 21}:
                category, message = "untrusted_certificate", "The TLS certificate chain is not trusted"
            else:
                category, message = "tls_handshake_failed", "TLS certificate validation failed"
            certificate = None
        except ssl.CertificateError:
            category, message, certificate = "hostname_mismatch", "TLS certificate hostname validation failed", None
        except ssl.SSLError:
            category, message, certificate = "tls_handshake_failed", "TLS handshake failed", None
        except socket.timeout:
            category, message, certificate = "timeout", "TLS connection timed out", None
        except socket.gaierror:
            category, message, certificate = "network", "The registered Windows target could not be resolved", None
        except OSError:
            if ca_trust_path and (not Path(ca_trust_path).is_file() or not Path(ca_trust_path).stat().st_size):
                category, message = "configuration_error", "Configured Windows CA trust is invalid"
            else:
                category, message = "network", "TLS connection could not be established"
            certificate = None
    return {
        "step": "tls_certificate",
        "status": "PASS" if category in {"success", "expiring_soon"} else "FAIL",
        "category": category,
        "message": message,
        "duration_ms": round((perf_counter() - started) * 1000, 1),
        **({"certificate": certificate} if certificate is not None else {}),
    }


def _is_ip_target(target: str) -> bool:
    try:
        import ipaddress
        ipaddress.ip_address(target)
        return True
    except ValueError:
        return False


@router.post("/devices/{device_id}/diagnostics/tls")
def diagnose_tls(device_id: int, db: Session = Depends(get_db), user=Depends(require_permission("devices:update"))):
    """Validate the registered Windows WinRM HTTPS certificate without authenticating."""
    device = _device(db, device_id, user)
    _fetch_lock(db, device_id, "tls")
    target = _windows_tcp_target(db, device)
    result = _tls_diagnostic(target, ca_trust_path=_effective_ca_path(db, device.id), port=5986)
    try:
        record_audit_event(
            db,
            actor=user,
            action="TLS_DIAGNOSTIC",
            resource_type="windows_device",
            resource_id=device.id,
            site_id=device.site_id,
            outcome="success" if result["status"] == "PASS" else "failure",
            failure_reason=None if result["status"] == "PASS" else str(result["category"]),
            metadata={"device_id": device.id, "step": "tls_certificate", "port": 5986},
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("windows_tls_diagnostic audit_failed device_id=%s", device_id, exc_info=True)
    return result


def _winrm_diagnostic_failure(error: Exception) -> tuple[str, str]:
    """Map library errors to stable categories without exposing exception text."""
    diagnostic = WinRMHTTPSAdapter._classify(error)
    return {
        "authentication": ("authentication_denied", "WinRM authentication was rejected"),
        "timeout": ("timeout", "WinRM operation timed out"),
        "tls": ("tls", "TLS certificate validation failed"),
        "network": ("network", "WinRM network connection failed"),
        "protocol": ("protocol_error", "WinRM protocol operation failed"),
    }.get(diagnostic.category, ("indeterminate", "WinRM diagnostic result is indeterminate"))


def _cim_diagnostic_failure(error: CIMError) -> tuple[str, str]:
    if error.category in {"permission", "authentication"}:
        return "cim_access_denied", "The monitoring account cannot read the CIM class"
    if error.category == "timeout":
        return "timeout", "CIM query timed out"
    if error.category == "tls":
        return "tls", "TLS certificate validation failed"
    if error.category == "transport":
        return "network", "CIM transport connection failed"
    return "cim_query_failed", "The read-only CIM query failed"


def _winrm_diagnostic(db: Session, device_id: int, user) -> list[dict[str, object]]:
    connection = _resolve_windows_connection(db, device_id, user)
    settings = get_settings()
    ca_trust_path = _effective_ca_path(db, device_id)
    adapter = WinRMHTTPSAdapter(
        connection.host,
        connection.username,
        connection.password,
        port=5986,
        ca_trust_path=ca_trust_path,
        connect_timeout=5,
        operation_timeout=5,
    )
    stages: list[dict[str, object]] = []

    auth_started = perf_counter()
    try:
        session = adapter._session()
    except Exception as error:
        category, message = _winrm_diagnostic_failure(error)
        stages.append(_diagnostic_stage("winrm_authentication", "FAIL", category, message, auth_started))
        stages.append(_diagnostic_stage("powershell_authorization", "SKIPPED", "indeterminate", "Skipped because WinRM authentication did not complete", perf_counter()))
        stages.append(_diagnostic_stage("cim_query", "SKIPPED", "indeterminate", "Skipped because WinRM authentication did not complete", perf_counter()))
        return stages

    powershell_started = perf_counter()
    try:
        _stdout, _stderr, status_code = adapter._run_powershell(session, "$PSVersionTable.PSVersion.ToString()")
        if status_code != 0:
            stages.append(_diagnostic_stage(
                "winrm_authentication", "PASS", "indeterminate",
                "WinRM authentication and PowerShell session creation completed together; independent authentication status is unavailable",
                auth_started,
            ))
            stages.append(_diagnostic_stage("powershell_authorization", "FAIL", "protocol_error", "The PowerShell version check failed", powershell_started))
            stages.append(_diagnostic_stage("cim_query", "SKIPPED", "indeterminate", "Skipped because PowerShell authorization failed", perf_counter()))
            return stages
    except Exception as error:
        category, message = _winrm_diagnostic_failure(error)
        stages.append(_diagnostic_stage("winrm_authentication", "FAIL", category, message, auth_started))
        stages.append(_diagnostic_stage("powershell_authorization", "SKIPPED", "indeterminate", "Skipped because WinRM authentication or session creation failed", powershell_started))
        stages.append(_diagnostic_stage("cim_query", "SKIPPED", "indeterminate", "Skipped because PowerShell authorization was not established", perf_counter()))
        return stages

    stages.append(_diagnostic_stage(
        "winrm_authentication", "PASS", "indeterminate",
        "WinRM authentication and PowerShell session authorization succeeded together; independent authentication status is unavailable",
        auth_started,
    ))
    stages.append(_diagnostic_stage("powershell_authorization", "PASS", "success", "Read-only PowerShell version check succeeded", powershell_started))

    cim_started = perf_counter()
    try:
        client = WindowsCIMClient(
            connection.host,
            connection.username,
            connection.password,
            trusted_ca_path=ca_trust_path,
            connection_timeout=5,
            read_timeout=5,
            operation_timeout=5,
        )
        rows = client.operating_system()
        if not rows:
            raise CIMError("parsing", "No operating-system data returned")
        stages.append(_diagnostic_stage("cim_query", "PASS", "success", "Read-only Win32_OperatingSystem query succeeded", cim_started))
    except CIMError as error:
        category, message = _cim_diagnostic_failure(error)
        stages.append(_diagnostic_stage("cim_query", "FAIL", category, message, cim_started))
    except Exception:
        stages.append(_diagnostic_stage("cim_query", "FAIL", "cim_query_failed", "The read-only CIM query failed", cim_started))
    return stages


@router.post("/devices/{device_id}/diagnostics/winrm")
def diagnose_winrm(device_id: int, db: Session = Depends(get_db), user=Depends(require_permission("devices:update"))):
    """Run bounded, read-only WinRM, PowerShell, and CIM diagnostics."""
    device = _device(db, device_id, user)
    _fetch_lock(db, device_id, "winrm")
    try:
        stages = _winrm_diagnostic(db, device_id, user)
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        stages = [
            _diagnostic_stage("winrm_authentication", "FAIL", "indeterminate", "WinRM diagnostic could not be completed", perf_counter()),
            _diagnostic_stage("powershell_authorization", "SKIPPED", "indeterminate", "Skipped because WinRM diagnostic failed", perf_counter()),
            _diagnostic_stage("cim_query", "SKIPPED", "indeterminate", "Skipped because WinRM diagnostic failed", perf_counter()),
        ]
    outcome = "success" if all(stage["status"] == "PASS" for stage in stages) else "failure"
    try:
        record_audit_event(
            db,
            actor=user,
            action="WINRM_DIAGNOSTIC",
            resource_type="windows_device",
            resource_id=device.id,
            site_id=device.site_id,
            outcome=outcome,
            failure_reason=None if outcome == "success" else next((str(stage["category"]) for stage in stages if stage["status"] == "FAIL"), "indeterminate"),
            metadata={"device_id": device.id, "steps": [stage["step"] for stage in stages], "port": 5986},
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.warning("windows_winrm_diagnostic audit_failed device_id=%s", device_id, exc_info=True)
    return {"device_id": device_id, "stages": stages}


@router.get("/devices/{device_id}/credentials", response_model=list[WindowsCredentialRead])
def list_credentials(device_id: int, db: Session = Depends(get_db), user=Depends(require_permission("devices:read"))):
    _device(db, device_id, user)
    return db.query(WindowsCredential).filter(WindowsCredential.device_id == device_id).all()

@router.get("/devices/enrolled")
def list_enrolled_devices(db: Session = Depends(get_db), user=Depends(require_permission("devices:read"))):
    rows = db.query(WindowsCredential.device_id).join(Device, Device.id == WindowsCredential.device_id).filter(Device.deleted_at.is_(None)).distinct().all()
    return {"device_ids": [row[0] for row in rows]}


@router.post("/devices/{device_id}/credentials", response_model=WindowsCredentialRead, status_code=status.HTTP_201_CREATED)
def create_credential(device_id: int, payload: WindowsCredentialCreate, db: Session = Depends(get_db), user=Depends(require_permission("devices:update"))):
    device = _device(db, device_id, user)
    if payload.device_id != device_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Device mismatch")
    existing = db.query(WindowsCredential).filter(WindowsCredential.device_id == device_id).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Windows credential already exists; update the existing credential")
    try:
        result = service.create(db, payload)
        _audit(db, user, "CREATE", device, result.id)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Windows credential already exists; update the existing credential") from None
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to create Windows credential") from None


@router.patch("/devices/{device_id}/credentials/{credential_id}", response_model=WindowsCredentialRead)
def update_credential(device_id: int, credential_id: int, payload: WindowsCredentialUpdate, db: Session = Depends(get_db), user=Depends(require_permission("devices:update"))):
    device = _device(db, device_id, user)
    _credential(db, device_id, credential_id)
    try:
        result = service.update(db, credential_id, payload)
        _audit(db, user, "UPDATE", device, credential_id)
        db.commit()
        return result
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to update Windows credential") from None


@router.delete("/devices/{device_id}/credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_credential(device_id: int, credential_id: int, db: Session = Depends(get_db), user=Depends(require_permission("devices:update"))):
    device = _device(db, device_id, user)
    _credential(db, device_id, credential_id)
    try:
        service.delete(db, credential_id)
        _audit(db, user, "DELETE", device, credential_id)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to delete Windows credential") from None


@router.post("/devices/{device_id}/connection-test")
def test_connection(device_id: int, db: Session = Depends(get_db), user=Depends(require_permission("devices:update")), request: Request = None):
    device = _device(db, device_id, user)
    credential = db.query(WindowsCredential).filter(WindowsCredential.device_id == device_id).first()
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Windows credential not found")
    try:
        diagnostic = service.test_connection(db, credential.id, ca_trust_path=_effective_ca_path(db, device.id))
        logger.info(
            "windows_connection_test request_id=%s device_id=%s credential_id=%s category=%s ok=%s",
            getattr(getattr(request, "state", None), "request_id", "unknown"), device_id, credential.id,
            diagnostic.category, diagnostic.ok,
        )
        _audit(db, user, "CONNECTION_TEST", device, credential.id, "success" if diagnostic.ok else "failure")
        db.commit()
        return {"ok": diagnostic.ok, "category": diagnostic.category, "message": diagnostic.message}
    except ValueError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to test Windows credential") from None
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Unable to test Windows connection") from None

def _snapshot_read(row: WindowsSystemSnapshot | None):
    if row is None:
        return None
    return {"device_id": row.device_id, "collected_at": row.collected_at, "system_info": row.system_info, "cpu": row.cpu, "memory": row.memory, "disks": row.disks}

def _uptime_seconds(last_boot_time):
    """Return uptime from a normalized, timezone-aware boot timestamp."""
    if not last_boot_time:
        return None
    try:
        boot = datetime.fromisoformat(str(last_boot_time).replace("Z", "+00:00"))
        if boot.tzinfo is None:
            return None
        now = datetime.now(timezone.utc)
        if boot > now:
            return None
        return (now - boot).total_seconds()
    except (TypeError, ValueError, OverflowError):
        return None


def _system_info_value(os_data):
    """Serialize non-sensitive normalized OS information for the snapshot."""
    last_boot_time = getattr(os_data, "last_boot_time", None)
    uptime_seconds = _uptime_seconds(last_boot_time)
    return {
        "hostname": getattr(os_data, "hostname", None), "caption": getattr(os_data, "caption", None), "version": getattr(os_data, "version", None),
        "manufacturer": getattr(os_data, "manufacturer", None), "build_number": getattr(os_data, "build_number", None), "architecture": getattr(os_data, "architecture", None),
        "os_type": getattr(os_data, "os_type", None), "product_type": getattr(os_data, "product_type", None), "install_date": getattr(os_data, "install_date", None),
        "last_boot_time": last_boot_time, "uptime_seconds": uptime_seconds, "windows_directory": getattr(os_data, "windows_directory", None),
        "system_directory": getattr(os_data, "system_directory", None), "system_drive": getattr(os_data, "system_drive", None), "boot_device": getattr(os_data, "boot_device", None),
        "locale": getattr(os_data, "locale", None), "time_zone": getattr(os_data, "time_zone", None), "service_pack": getattr(os_data, "service_pack", None),
    }

@router.get("/devices/{device_id}/system-info")
def get_system_info(device_id: int, db: Session = Depends(get_db), user=Depends(require_permission("devices:read"))):
    _device(db, device_id, user)
    return _snapshot_read(db.query(WindowsSystemSnapshot).filter(WindowsSystemSnapshot.device_id == device_id).first()) or {"device_id": device_id, "collected_at": None, "system_info": {}, "cpu": {}, "memory": {}, "disks": []}

@router.post("/devices/{device_id}/system-info/fetch")
def fetch_system_info(device_id: int, db: Session = Depends(get_db), user=Depends(require_permission("devices:update"))):
    started = perf_counter()
    device = _device(db, device_id, user)
    _fetch_lock(db, device_id, "system")
    try:
        connection = _resolve_windows_connection(db, device_id, user, device=device)
        logger.info("windows_system_fetch stage=credential_resolution device_id=%s credential_id=%s host=%s tls=true", device_id, connection.credential.id, connection.host)
        client = WindowsCIMClient(connection.host, connection.username, connection.password, trusted_ca_path=_effective_ca_path(db, device.id))
        logger.info("windows_system_fetch stage=winrm_session device_id=%s credential_id=%s host=%s tls=true", device_id, connection.credential.id, connection.host)
        os_rows = client.operating_system()
        if not os_rows:
            raise CIMError("parsing", "Windows CIM returned no operating-system data")
        os_data = os_rows[0]
        logger.info("windows_system_fetch stage=cim_query device_id=%s class=Win32_OperatingSystem rows=%s", device_id, len(os_rows))
        value = _system_info_value(os_data)
        row = _upsert_system_snapshot(db, device_id, value)
        logger.info("windows_system_fetch stage=persistence device_id=%s action=upsert", device_id)
        db.commit()
        db.refresh(row)
        response = _snapshot_read(row)
        try:
            record_audit_event(
                db,
                actor=user,
                action="SYSTEM_FETCH",
                resource_type="windows_device",
                resource_id=device.id,
                site_id=device.site_id,
                outcome="success",
                metadata={"device_id": device.id, "module": "system"},
            )
        except Exception:
            logger.warning("windows_system_fetch audit_failed device_id=%s", device_id, exc_info=True)
        return response
    except CIMError as exc:
        db.rollback()
        _audit_system_failure(db, user, device, _system_failure_reason(exc))
        logger.warning("windows_system_fetch stage=%s category=%s device_id=%s duration_ms=%.1f message=%s", getattr(exc, "stage", "cim"), exc.category, device_id, (perf_counter() - started) * 1000, exc.message)
        raise HTTPException(status_code=502, detail=f"Windows collection failed during {getattr(exc, 'stage', 'CIM')}: {exc.message}") from None
    except SQLAlchemyError:
        db.rollback()
        _audit_system_failure(db, user, device, "persistence_failed")
        logger.exception("windows_system_fetch stage=persistence category=database device_id=%s duration_ms=%.1f", device_id, (perf_counter() - started) * 1000)
        raise HTTPException(status_code=502, detail="Windows collection succeeded but persistence failed") from None
    except HTTPException:
        db.rollback()
        # Device authorization failures occur before this try block. The only
        # expected HTTP error here is credential lookup failure.
        _audit_system_failure(db, user, device, "credential_missing")
        raise
    except Exception as exc:
        db.rollback()
        _audit_system_failure(db, user, device, "unexpected_error")
        logger.exception("windows_system_fetch stage=unknown category=unexpected device_id=%s duration_ms=%.1f exception_type=%s", device_id, (perf_counter() - started) * 1000, type(exc).__name__)
        raise HTTPException(status_code=502, detail="Windows collection failed; inspect server diagnostics") from None

def _metric_read(row: WindowsMetricSnapshot | None, device_id: int, module: str):
    return {"device_id": device_id, "module": module, "collected_at": row.collected_at if row else None, "data": row.data if row else {}}

def _metric_client(db: Session, device_id: int, user, *, device: Device | None = None):
    connection = _resolve_windows_connection(db, device_id, user, device=device)
    settings = get_settings()
    return WindowsCIMClient(connection.host, connection.username, connection.password, trusted_ca_path=_effective_ca_path(db, device_id)), connection.credential


def _hardware_read(row: WindowsHardwareSnapshot | None, device_id: int) -> dict:
    value = serialize_hardware_information({
        "computer_system": row.computer_system if row else {},
        "system_product": row.system_product if row else {},
        "baseboard": row.baseboard if row else {},
        "bios": row.bios if row else {},
        "processors": row.processors if row else [],
        "memory_modules": row.memory_modules if row else [],
        "memory_arrays": row.memory_arrays if row else [],
    })
    return {
        "device_id": device_id,
        "collected_at": row.collected_at if row else None,
        **value,
    }


@router.get("/devices/{device_id}/hardware", response_model=WindowsHardwareSnapshotRead)
def get_hardware(device_id: int, db: Session = Depends(get_db), user=Depends(require_permission("devices:read"))):
    _device(db, device_id, user)
    return _hardware_read(get_hardware_snapshot(db, device_id), device_id)


@router.post("/devices/{device_id}/hardware/fetch", response_model=WindowsHardwareSnapshotRead)
def fetch_hardware(device_id: int, db: Session = Depends(get_db), user=Depends(require_permission("devices:update"))):
    started = perf_counter()
    device = _device(db, device_id, user)
    _fetch_lock(db, device_id, "hardware")
    try:
        device = _device(db, device_id, user, refresh=True)
        client, credential = _metric_client(db, device_id, user, device=device)
        logger.info("windows_hardware_fetch stage=winrm_session device_id=%s credential_id=%s host=%s tls=true", device_id, credential.id, client.hostname)
        value = client.hardware_information()
        logger.info("windows_hardware_fetch stage=cim_query device_id=%s sections=%s", device_id, len(value))
        row = upsert_hardware_snapshot(db, device_id, value)
        db.commit()
        db.refresh(row)
        response = _hardware_read(row, device_id)
        try:
            _audit(db, user, "HARDWARE_FETCH", device, credential.id)
        except Exception:
            logger.warning("windows_hardware_fetch audit_failed device_id=%s", device_id, exc_info=True)
        logger.info("windows_hardware_fetch stage=persistence device_id=%s duration_ms=%.1f", device_id, (perf_counter() - started) * 1000)
        return response
    except CIMError as exc:
        db.rollback()
        logger.warning("windows_hardware_fetch stage=%s category=%s device_id=%s duration_ms=%.1f message=%s", getattr(exc, "stage", "cim"), exc.category, device_id, (perf_counter() - started) * 1000, exc.message)
        raise HTTPException(status_code=502, detail=f"Windows hardware collection failed during {getattr(exc, 'stage', 'CIM')}: {exc.message}") from None
    except SQLAlchemyError:
        db.rollback()
        logger.exception("windows_hardware_fetch stage=persistence category=database device_id=%s", device_id)
        raise HTTPException(status_code=502, detail="Windows hardware collection succeeded but persistence failed") from None
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        logger.exception("windows_hardware_fetch stage=unknown category=unexpected device_id=%s", device_id)
        raise HTTPException(status_code=502, detail="Windows hardware collection failed; inspect server diagnostics") from None

@router.get("/devices/{device_id}/hardware/sensors/discover")
def discover_hardware_sensors(device_id: int, db: Session = Depends(get_db), user=Depends(require_permission("devices:read"))):
    """Read-only native WMI sensor discovery; values are not persisted."""
    logger.info("windows_sensor_discovery_start device_id=%s user_id=%s", device_id, getattr(user, "id", None))
    _device(db, device_id, user)
    client, _credential = _metric_client(db, device_id, user)
    try:
        native = NativeCIMSensorProvider(client).discover()
        provider_results = [native, LibreHardwareMonitorProvider(client).discover()]
        result = {
            "device_id": device_id,
            "sensors": [sensor.as_dict() for provider in provider_results for sensor in provider.sensors],
            "providers": [provider.as_dict() for provider in provider_results],
        }
        logger.info("windows_sensor_discovery_success device_id=%s sensor_count=%s", device_id, len(result["sensors"]))
        return result
    except CIMError as exc:
        logger.warning("windows_sensor_discovery_failed device_id=%s category=%s message=%s", device_id, exc.category, exc.message)
        raise HTTPException(status_code=502, detail=f"Windows sensor discovery failed: {exc.message}") from None

@router.get("/devices/{device_id}/hardware/disks/inventory")
def discover_disk_inventory(device_id: int, db: Session = Depends(get_db), user=Depends(require_permission("devices:read"))):
    """Read-only physical disk, partition and optional Storage inventory."""
    _device(db, device_id, user)
    client, _credential = _metric_client(db, device_id, user)
    try:
        started = perf_counter()
        result = client.disk_inventory()
        logger.info("windows_disk_inventory_success device_id=%s physical=%s partitions=%s modern=%s duration_ms=%.1f", device_id, len(result.get("physical_disks", [])), len(result.get("partitions", [])), result.get("modern_status"), (perf_counter() - started) * 1000)
        return {"device_id": device_id, **result}
    except CIMError as exc:
        logger.warning("windows_disk_inventory_failed device_id=%s category=%s message=%s", device_id, exc.category, exc.message)
        raise HTTPException(status_code=502, detail=f"Windows disk inventory failed: {exc.message}") from None


@router.get("/devices/{device_id}/usb", response_model=WindowsUSBInventoryRead)
def get_usb_inventory(device_id: int, db: Session = Depends(get_db), user=Depends(require_permission("devices:read"))):
    """Collect a read-only USB inventory for an authorized Windows device."""
    _device(db, device_id, user)
    try:
        client, _credential = _metric_client(db, device_id, user)
        collected_at = datetime.now(timezone.utc).isoformat()
        inventory = client.usb_inventory()
        errors = [
            {"source": source, "status": "collection_failed", "error": category}
            for source, category in inventory.get("errors", {}).items()
        ]
        usb = {
            "controllers": [asdict(item) for item in inventory.get("controllers", [])],
            "hubs": [asdict(item) for item in inventory.get("hubs", [])],
            "devices": [asdict(item) for item in inventory.get("devices", [])],
            "collection_errors": errors,
        }
        status_value = "partial" if errors else "empty" if not any(usb[key] for key in ("controllers", "hubs", "devices")) else "ok"
        return {"device_id": device_id, "collected_at": collected_at, "status": status_value, "usb": usb}
    except CIMError as exc:
        logger.warning("windows_usb_inventory_failed device_id=%s category=%s message=%s", device_id, exc.category, exc.message)
        raise HTTPException(status_code=502, detail=f"Windows USB inventory failed: {exc.category}") from None


def _health_status(exc: CIMError | None = None) -> str:
    if exc is None:
        return "ok"
    if exc.category in {"permission", "authentication"}:
        return "permission_denied"
    if exc.category == "protocol":
        return "unavailable"
    return "collection_failed"


def _health_metric(raw: str | None, unit: str, source: str) -> dict[str, object | None]:
    if raw is None or raw == "":
        return {"value": None, "unit": unit, "status": "unavailable", "source": source, "error": "missing_value"}
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return {"value": None, "unit": unit, "status": "unavailable", "source": source, "error": "invalid_value"}
    if value < 0:
        return {"value": None, "unit": unit, "status": "unavailable", "source": source, "error": "invalid_value"}
    if value.is_integer():
        value = int(value)
    return {"value": value, "unit": unit, "status": "ok", "source": source, "error": None}


@router.get("/devices/{device_id}/hardware/disks/health")
def discover_disk_health(device_id: int, db: Session = Depends(get_db), user=Depends(require_permission("devices:read"))):
    """Read-only Storage health/reliability data with capability-aware results."""
    _device(db, device_id, user)
    client, _credential = _metric_client(db, device_id, user)
    collected_at = datetime.now(timezone.utc).isoformat()
    modern: list[dict] = []
    reliability: list[dict] = []
    modern_error = None
    reliability_error = None
    try:
        modern = client.modern_physical_disks()
    except CIMError as exc:
        modern_error = exc
    try:
        raw_reliability = client.storage_reliability_counters()
    except CIMError as exc:
        raw_reliability = []
        reliability_error = exc

    modern_ids = {str(row.get("DeviceId")) for row in modern if row.get("DeviceId")}
    physical = []
    for row in modern:
        physical.append({
            "device_id": row.get("DeviceId"),
            "friendly_name": row.get("FriendlyName"),
            "health_status": row.get("HealthStatus"),
            "operational_status": row.get("OperationalStatus"),
            "media_type": row.get("MediaType"),
            "bus_type": row.get("BusType"),
            "size": row.get("Size"),
            "firmware_version": row.get("FirmwareVersion"),
            "status": "ok",
            "source": "MSFT_PhysicalDisk",
            "error": None,
        })
    metric_fields = {
        "temperature": ("Temperature", "°C"), "temperature_max": ("TemperatureMax", "°C"),
        "wear": ("Wear", "%"), "read_errors_total": ("ReadErrorsTotal", "errors"),
        "write_errors_total": ("WriteErrorsTotal", "errors"), "read_errors_corrected": ("ReadErrorsCorrected", "errors"),
        "write_errors_corrected": ("WriteErrorsCorrected", "errors"), "power_on_hours": ("PowerOnHours", "hours"),
        "unsafe_shutdown_count": ("UnsafeShutdownCount", "events"),
    }
    for row in raw_reliability:
        stable_id = row.get("DeviceId")
        matched = bool(stable_id and str(stable_id) in modern_ids)
        metrics = {}
        for name, (field, unit) in metric_fields.items():
            metrics[name] = _health_metric(row.get(field), unit, f"MSFT_StorageReliabilityCounter.{field}")
        reliability.append({"device_id": stable_id, "physical_disk_device_id": stable_id if matched else None, "association_status": "matched" if matched else "unavailable", "metrics": metrics})
    provider_status = {"physical_disk": _health_status(modern_error) if modern_error else ("ok" if modern else "unsupported"), "reliability": _health_status(reliability_error) if reliability_error else ("ok" if raw_reliability else "unsupported")}
    return {"device_id": device_id, "collected_at": collected_at, "provider_status": provider_status, "physical_disks": physical, "reliability_counters": reliability, "correlation_status": "reliable" if any(row["association_status"] == "matched" for row in reliability) else "unavailable", "provider_error": reliability_error.message if reliability_error else (modern_error.message if modern_error else None)}

@router.get("/devices/{device_id}/metrics/{module}")
def get_metric(device_id: int, module: str, db: Session = Depends(get_db), user=Depends(require_permission("devices:read"))):
    if module not in WINDOW_MODULES:
        raise HTTPException(status_code=404, detail="Unsupported Windows metric module")
    _device(db, device_id, user)
    row = db.query(WindowsMetricSnapshot).filter(WindowsMetricSnapshot.device_id == device_id, WindowsMetricSnapshot.module == module).first()
    return _metric_read(row, device_id, module)

@router.post("/devices/{device_id}/metrics/{module}/fetch")
def fetch_metric(device_id: int, module: str, db: Session = Depends(get_db), user=Depends(require_permission("devices:update"))):
    if module not in WINDOW_MODULES:
        raise HTTPException(status_code=404, detail="Unsupported Windows metric module")
    started = perf_counter()
    _fetch_lock(db, device_id, module)
    device = None
    try:
        device = _device(db, device_id, user) if module in {"cpu", "memory", "disk", "network"} else None
        client, credential = _metric_client(db, device_id, user, device=device)
        logger.info("windows_metric_fetch stage=winrm_session device_id=%s module=%s credential_id=%s host=%s tls=true", device_id, module, credential.id, credential.connection_host)
        if module == "system":
            rows = client.operating_system(); logger.info("windows_metric_fetch stage=cim_query device_id=%s module=%s class=Win32_OperatingSystem rows=%s", device_id, module, len(rows))
            if not rows: raise CIMError("parsing", "Windows CIM returned no operating-system data")
            value = _system_info_value(rows[0])
        elif module == "memory":
            rows = client.operating_system(); logger.info("windows_metric_fetch stage=cim_query device_id=%s module=%s class=Win32_OperatingSystem rows=%s", device_id, module, len(rows))
            if not rows: raise CIMError("parsing", "Windows CIM returned no memory data")
            total, free = rows[0].total_memory_bytes, rows[0].free_memory_bytes
            memory_counter_rows = []
            memory_counter_error = None
            try:
                memory_counter_rows = client.memory_performance()
            except CIMError as exc:
                memory_counter_error = exc
            memory_counter = memory_counter_rows[0] if memory_counter_rows else None
            counter_names = {
                "available_mbytes": ("MB", "AvailableMBytes"), "pages_per_sec": ("pages/s", "PagesPersec"),
                "page_reads_per_sec": ("pages/s", "PageReadsPersec"), "page_writes_per_sec": ("pages/s", "PageWritesPersec"),
                "page_faults_per_sec": ("faults/s", "PageFaultsPersec"), "committed_bytes": ("bytes", "CommittedBytes"),
                "commit_limit": ("bytes", "CommitLimit"), "cache_bytes": ("bytes", "CacheBytes"),
                "pool_paged_bytes": ("bytes", "PoolPagedBytes"), "pool_nonpaged_bytes": ("bytes", "PoolNonpagedBytes"),
                "percent_committed_bytes_in_use": ("%", "PercentCommittedBytesInUse"),
            }
            def memory_counter_value(field):
                return getattr(memory_counter, field) if memory_counter else None
            def memory_counter_status(field):
                value = memory_counter_value(field)
                if value is not None:
                    status = "ok"; error = None
                elif memory_counter_error and memory_counter_error.category in {"permission", "authentication"}:
                    status = "permission_denied"; error = memory_counter_error.message
                elif memory_counter_error:
                    status = "unavailable"; error = memory_counter_error.message
                else:
                    status = "unsupported"; error = "counter_not_returned"
                unit, source_property = counter_names[field]
                return {"value": value, "unit": unit, "status": status, "source": f"Win32_PerfFormattedData_PerfOS_Memory.{source_property}", "error": error}
            value = {
                "total_bytes": total,
                "free_bytes": free,
                "used_bytes": max(0, total - free),
                "usage_percent": round((total - free) * 100 / total, 2) if total else None,
                "counters": {field: memory_counter_status(field) for field in counter_names},
            }
        elif module == "cpu":
            rows = client.processor_performance(); logger.info("windows_metric_fetch stage=cim_query device_id=%s module=%s class=Win32_PerfFormattedData_PerfOS_Processor rows=%s", device_id, module, len(rows))
            if not rows: raise CIMError("parsing", "Windows CIM returned no processor data")
            total = next((row for row in rows if row.name == "_Total"), None)
            physical = [row for row in rows if row.name != "_Total"]
            try:
                queue_rows = client.system_performance()
            except CIMError:
                queue_rows = []
            aggregate = total or (physical[0] if physical else None)
            def metric_status(value, *, source_available=True):
                status = "ok" if value is not None else ("unsupported" if not source_available else "unavailable")
                return {"value": value, "status": status, "error": None if status == "ok" else f"counter_{status}"}
            value = {
                "model": physical[0].name if physical else None,
                "logical_processors": len(physical) if physical else None,
                "usage_percent": round(
                    aggregate.usage_percent
                    if total
                    else sum(row.usage_percent for row in physical if row.usage_percent is not None) / len([row for row in physical if row.usage_percent is not None]), 2
                ) if aggregate and aggregate.usage_percent is not None else None,
                "logical_processors_usage": [
                    {"name": row.name, "usage_percent": row.usage_percent,
                     "user_percent": row.user_percent, "privileged_percent": row.privileged_percent,
                     "idle_percent": row.idle_percent, "interrupts_per_sec": row.interrupts_per_sec,
                     "context_switches_per_sec": row.context_switches_per_sec}
                    for row in physical
                ],
                "counters": {
                    "user_time_percent": metric_status(aggregate.user_percent if aggregate else None),
                    "privileged_time_percent": metric_status(aggregate.privileged_percent if aggregate else None),
                    "idle_time_percent": metric_status(aggregate.idle_percent if aggregate else None),
                    "interrupts_per_sec": metric_status(aggregate.interrupts_per_sec if aggregate else None),
                    "context_switches_per_sec": metric_status(queue_rows[0].context_switches_per_sec if queue_rows else None, source_available=bool(queue_rows)),
                    "processor_queue_length": metric_status(queue_rows[0].processor_queue_length if queue_rows else None, source_available=bool(queue_rows)),
                },
            }
            system_row = queue_rows[0] if queue_rows else None
            value["thread_count"] = system_row.threads if system_row else None
            value["process_count"] = system_row.processes if system_row else None
            try:
                inventory = client.hardware_processors()
                systems = client.computer_system()
                cpu = inventory[0] if inventory else None
                system = systems[0] if systems else None
                value["identity"] = {
                    "model": cpu.name if cpu else None,
                    "manufacturer": cpu.manufacturer if cpu else None,
                    "physical_cores": cpu.number_of_cores if cpu else None,
                    "logical_processors": (cpu.number_of_logical_processors if cpu else None) or (system.number_of_logical_processors if system else None),
                    "clock_speed_mhz": cpu.max_clock_speed_mhz if cpu else None,
                    "current_clock_speed_mhz": cpu.current_clock_speed_mhz if cpu else None,
                }
            except CIMError:
                value["identity"] = {"status": "unavailable"}
            try:
                process_rows = client.processes()
                value["processes"] = [
                    {"name": row.name, "pid": row.process_id, "memory_bytes": row.working_set_bytes,
                     "thread_count": row.thread_count, "status": None, "path": row.executable_path}
                    for row in process_rows
                ]
            except (CIMError, TypeError):
                value["processes"] = []
            try:
                os_rows = client.operating_system()
                if os_rows:
                    value["system"] = _system_info_value(os_rows[0])
                    value["uptime_seconds"] = value["system"].get("uptime_seconds")
            except (CIMError, TypeError, IndexError):
                value["system"] = {}
        elif module == "disk":
            rows = client.disks(); logger.info("windows_metric_fetch stage=cim_query device_id=%s module=%s class=Win32_LogicalDisk rows=%s", device_id, module, len(rows))
            value = [{
                "device_id": row.device_id,
                "volume_name": row.volume_name,
                "size_bytes": row.size_bytes,
                "free_bytes": row.free_bytes,
                "used_bytes": max(0, row.size_bytes - row.free_bytes),
                "usage_percent": round((row.size_bytes - row.free_bytes) * 100 / row.size_bytes, 2) if row.size_bytes else None,
            } for row in rows]
            performance_error = None
            try:
                logical_perf = client.disk_performance("logical")
                physical_perf = client.disk_performance("physical")
            except CIMError as exc:
                logical_perf, physical_perf, performance_error = [], [], exc

            metric_units = {
                "read_iops": "operations/s", "write_iops": "operations/s", "total_iops": "operations/s",
                "read_bytes_per_sec": "bytes/s", "write_bytes_per_sec": "bytes/s", "total_bytes_per_sec": "bytes/s",
                "read_latency_ms": "ms", "write_latency_ms": "ms", "average_latency_ms": "ms",
                "average_queue_length": "requests", "current_queue_length": "requests",
                "split_io_per_sec": "operations/s", "percent_disk_time": "%",
            }
            def counter_payload(perf, field):
                raw = getattr(perf, field)
                if raw is not None:
                    status, error = "ok", None
                elif performance_error and performance_error.category in {"permission", "authentication"}:
                    status, error = "permission_denied", performance_error.message
                elif performance_error:
                    status, error = "unavailable", performance_error.message
                else:
                    status, error = "unsupported", "counter_not_returned"
                return {"value": raw, "unit": metric_units[field], "status": status, "source": f"{perf.instance}:{field}", "error": error}
            def performance_payload(perf):
                return {field: counter_payload(perf, field) for field in metric_units}
            logical_instances = [perf for perf in logical_perf if perf.instance != "_Total"]
            physical_instances = [perf for perf in physical_perf if perf.instance != "_Total"]
            aggregate = {
                "logical": next((performance_payload(perf) for perf in logical_perf if perf.instance == "_Total"), None),
                "physical": next((performance_payload(perf) for perf in physical_perf if perf.instance == "_Total"), None),
            }
            performance = {
                "logical": [{"instance": perf.instance, "metrics": performance_payload(perf)} for perf in logical_instances],
                "physical": [{"instance": perf.instance, "metrics": performance_payload(perf)} for perf in physical_instances],
                "aggregate": aggregate,
            }
            # Keep the legacy array response shape. Each logical capacity row
            # carries the shared performance section as an additive field.
            for item in value:
                item["performance"] = performance
        elif module == "network":
            rows = client.network_interfaces()
            logger.info(
                "windows_metric_fetch stage=cim_query device_id=%s module=network collector=network_interfaces rows=%s",
                device_id,
                len(rows),
            )
            row = upsert_network_snapshot(db, device_id, rows)
            db.commit()
            response = _metric_read(row, device_id, module)
            try:
                record_audit_event(
                    db,
                    actor=user,
                    action="NETWORK_FETCH",
                    resource_type="windows_device",
                    resource_id=device.id,
                    site_id=device.site_id,
                    outcome="success",
                    metadata={"device_id": device.id, "module": "network"},
                )
            except Exception:
                logger.warning("windows_metric_fetch audit_failed device_id=%s module=network", device_id, exc_info=True)
            logger.info("windows_metric_fetch stage=persistence device_id=%s module=network duration_ms=%.1f", device_id, (perf_counter() - started) * 1000)
            return response
        else:
            raise CIMError("permission", "Unsupported Windows metric module")
        row = _upsert_metric_snapshot(db, device_id, module, value)
        db.commit()
        response = _metric_read(row, device_id, module)
        if module in {"cpu", "memory", "disk"}:
            action = {"cpu": "CPU_FETCH", "memory": "MEMORY_FETCH", "disk": "DISK_FETCH"}[module]
            try:
                record_audit_event(
                    db,
                    actor=user,
                    action=action,
                    resource_type="windows_device",
                    resource_id=device.id,
                    site_id=device.site_id,
                    outcome="success",
                    metadata={"device_id": device.id, "module": module},
                )
            except Exception:
                logger.warning("windows_metric_fetch audit_failed device_id=%s module=%s", device_id, module, exc_info=True)
        logger.info("windows_metric_fetch stage=persistence device_id=%s module=%s duration_ms=%.1f", device_id, module, (perf_counter() - started) * 1000)
        return response
    except CIMError as exc:
        db.rollback()
        if module in {"cpu", "memory", "disk"}:
            _audit_metric_failure(db, user, device, module, _metric_failure_reason(exc))
        logger.warning("windows_metric_fetch stage=cim category=%s device_id=%s module=%s duration_ms=%.1f message=%s", exc.category, device_id, module, (perf_counter() - started) * 1000, exc.message)
        raise HTTPException(status_code=502, detail=f"Windows {module} collection failed: {exc.message}") from None
    except SQLAlchemyError:
        db.rollback()
        if module in {"cpu", "memory", "disk"}:
            _audit_metric_failure(db, user, device, module, "persistence_failed")
        logger.exception("windows_metric_fetch stage=persistence category=database device_id=%s module=%s", device_id, module)
        raise HTTPException(status_code=502, detail="Windows metric collection succeeded but persistence failed") from None
    except HTTPException as exc:
        db.rollback()
        if module in {"cpu", "memory", "disk"} and exc.status_code == 404 and exc.detail == "Windows credential not found":
            _audit_metric_failure(db, user, device, module, "credential_missing")
        raise
    except Exception as exc:
        db.rollback()
        if module in {"cpu", "memory", "disk"}:
            _audit_metric_failure(db, user, device, module, "unexpected_error")
        logger.exception("windows_metric_fetch stage=unknown category=unexpected device_id=%s module=%s exception_type=%s", device_id, module, type(exc).__name__)
        raise HTTPException(status_code=502, detail="Windows metric collection failed; inspect server diagnostics") from None


def _event_row(row: WindowsEventLog) -> dict:
    return {name: getattr(row, name) for name in (
        "id", "device_id", "channel", "record_id", "time_created", "event_id",
        "provider", "level", "machine_name", "message", "user_id", "collected_at",
    )}


def _event_time(value: datetime | None, default: datetime) -> datetime:
    result = value or default
    return result if result.tzinfo is not None else result.replace(tzinfo=timezone.utc)


@router.get("/devices/{device_id}/events/system")
def get_system_events(
    device_id: int,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    event_ids: list[int] | None = Query(default=None, max_length=100),
    level: str | None = Query(default=None, max_length=80),
    offset: int = Query(default=0, ge=0, le=100000),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    user=Depends(require_permission("devices:read")),
):
    _device(db, device_id, user)
    if start_time and end_time and start_time > end_time:
        raise HTTPException(status_code=400, detail="Invalid event time range")
    if event_ids and any(event_id < 0 for event_id in event_ids):
        raise HTTPException(status_code=400, detail="Invalid event ID filter")
    try:
        rows = list_system_events(db, device_id, start_time=start_time, end_time=end_time, event_ids=event_ids or (), level=level, offset=offset, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"device_id": device_id, "channel": "System", "items": [_event_row(row) for row in rows], "offset": offset, "limit": limit}


@router.post("/devices/{device_id}/events/system/fetch")
def fetch_system_events(
    device_id: int,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    event_ids: list[int] | None = Query(default=None, max_length=100),
    max_records: int = Query(default=50, ge=1, le=50),
    db: Session = Depends(get_db),
    user=Depends(require_permission("devices:update")),
):
    started = perf_counter()
    if start_time and end_time and start_time > end_time:
        raise HTTPException(status_code=400, detail="Invalid event time range")
    if event_ids and (len(set(event_ids)) != len(event_ids) or any(event_id < 0 for event_id in event_ids)):
        raise HTTPException(status_code=400, detail="Invalid event ID filter")
    end = _event_time(end_time, datetime.now(timezone.utc))
    stored_latest = latest_system_event_time(db, device_id) if start_time is None else None
    default_start = stored_latest.replace(tzinfo=timezone.utc) if stored_latest is not None else end - timedelta(hours=24)
    start = _event_time(start_time, default_start)
    if start > end:
        raise HTTPException(status_code=400, detail="Invalid event time range")
    _fetch_lock(db, device_id, "events:system")
    try:
        connection = _resolve_windows_connection(db, device_id, user)
        adapter = WinRMHTTPSAdapter(
            connection.host, connection.username, connection.password,
            port=5986, ca_trust_path=_effective_ca_path(db, device_id),
            connect_timeout=10, operation_timeout=20,
        )
        collection = collect_system_events(adapter, start_time=start, end_time=end, event_ids=tuple(event_ids or ()), max_records=max_records)
        inserted = save_system_events(db, device_id, "System", collection.events, collected_at=datetime.now(timezone.utc).replace(tzinfo=None), max_records=max_records)
        response = {"device_id": device_id, "channel": "System", "fetched_count": collection.event_count, "inserted_count": inserted, "truncated": collection.truncated, "collected_at": collection.collected_at}
        try:
            record_audit_event(
                db,
                actor=user,
                action="EVENTS_FETCH",
                resource_type="windows_device",
                resource_id=connection.device.id,
                site_id=connection.device.site_id,
                outcome="success",
                metadata={"device_id": connection.device.id, "module": "events"},
            )
        except Exception:
            logger.warning("windows_system_events audit_failed device_id=%s", device_id, exc_info=True)
        return response
    except HTTPException:
        db.rollback()
        raise
    except SystemEventError as exc:
        db.rollback()
        logger.warning(
            "windows_system_event_api_failed device_id=%s category=%s field=%s reason=%s",
            device_id, exc.category, exc.field or "unknown", exc.reason or "unknown",
        )
        raise HTTPException(status_code=504 if exc.category == "timeout" else 502, detail=f"Windows System event collection failed: {exc.category}") from None
    except SQLAlchemyError:
        db.rollback()
        logger.exception("windows_system_events_persistence_failed device_id=%s duration_ms=%.1f", device_id, (perf_counter() - started) * 1000)
        raise HTTPException(status_code=502, detail="Windows System event persistence failed") from None
    except Exception:
        db.rollback()
        logger.exception("windows_system_events_failed device_id=%s duration_ms=%.1f", device_id, (perf_counter() - started) * 1000)
        raise HTTPException(status_code=502, detail="Windows System event collection failed") from None
