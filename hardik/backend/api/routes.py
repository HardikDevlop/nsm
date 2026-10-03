from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import csv
import io
import ipaddress
from pathlib import Path
import logging
import uuid
import os
import signal
import subprocess
import time
from threading import Lock
from types import SimpleNamespace
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import case, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, load_only

from backend.auth.security import create_access_token, decode_access_token_claims, hash_password, verify_password
from backend.auth.authorization import can_access_site, can_assign_role, can_create_role, can_manage_permission_definition, can_modify_role, can_manage_user, can_view_audit_actor, can_view_security_audit, get_accessible_site_ids, get_authority_level, is_super_admin
from backend.database.session import get_db
from backend.database.migrations import get_migration_status
from backend.dependencies import bearer_scheme, get_current_user, require_permission, require_any_permission
from backend.models import (
    Alert,
    AuditLog,
    Device,
    DeviceCredential,
    DeviceMetric,
    DeviceStatusHistory,
    DeviceType,
    Event,
    Interface,
    MonitoringJob,
    Notification,
    Organization,
    Permission,
    Report,
    ReportSchedule,
    GeneratedReport,
    Role,
    Site,
    Threshold,
    User,
    UserSession,
    Vendor,
)
from backend.repositories.crud import CRUDRouterMixin
from backend.config.settings import get_settings
from backend.schemas.nms import (
    AlertCreate,
    AlertRead,
    AlertUpdate,
    AssignRoleRequest,
    AuditLogRead,
    BrandingRead,
    DashboardSummary,
    DeviceCreate,
    DeviceCredentialCreate,
    DeviceCredentialRead,
    DeviceCredentialUpdate,
    DeviceMetricCreate,
    DeviceMetricRead,
    DeviceOptionRead,
    DeviceMetricUpdate,
    DeviceRead,
    DeviceStatusHistoryRead,
    ReportManagementFilters,
    ReportScheduleCreate, ReportScheduleRead, ReportScheduleUpdate, GeneratedReportRead,
    ReportManagementOptionsItem,
    ReportManagementRecord,
    ReportManagementSection,
    ReportManagementSummary,
    ReportManagementDeviceOption,
    ReportInterfaceDetail,
    ReportAlertDetail,
    ReportManagementTrends, ReportTrendAvailabilityPoint, ReportTrendPerformancePoint, ReportTrendBandwidthPoint, ReportTrendAlertPoint, ReportInventory,
    DeviceTypeCreate,
    DeviceTypeRead,
    DeviceTypeUpdate,
    DeviceUpdate,
    DiscoveryRequest,
    EventCreate,
    EventRead,
    EventUpdate,
    InterfaceCreate,
    InterfaceRead,
    InterfaceUpdate,
    LoginRequest,
    MonitoringJobCreate,
    MonitoringJobRead,
    MonitoringJobUpdate,
    MonitoringRunRequest,
    NotificationCreate,
    NotificationRead,
    NotificationUpdate,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    PermissionCreate,
    PermissionIds,
    PermissionRead,
    PermissionUpdate,
    ReportCreate,
    ReportRead,
    ReportUpdate,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    RoleWithPermissions,
    SiteCreate,
    SiteRead,
    SiteUpdate,
    ThresholdCreate,
    ThresholdRead,
    ThresholdUpdate,
    Token,
    UserCreate,
    UserRead, UserSessionRead,
    UserStatusUpdate,
    UserUpdate,
    VendorCreate,
    VendorRead,
    VendorUpdate,
)
from backend.services.audit import record_audit_event
from backend.services.discovery import discover_network
from backend.services.monitoring import run_monitoring_check
from backend.services.device_health import derive_device_health
from backend.services.availability import build_intervals

from backend.services.alerting import _notify, create_device_added_alert, create_operational_alert
from backend.incidents.service import create_incident_from_alert, process_alert_recovery
from backend.utils.crypto import encrypt_secret


router = APIRouter(prefix="/api/v1")


def _notify_alert_after_response(alert_id: int) -> None:
    """Send audit notifications outside the device mutation request."""
    from backend.database.session import SessionLocal

    try:
        with SessionLocal() as db:
            alert = db.query(Alert).filter(Alert.id == alert_id).first()
            if alert is not None:
                _notify(db, alert)
                db.commit()
    except Exception:
        logger.exception("Deferred alert notification failed for alert %s", alert_id)
incident_logger = logging.getLogger(__name__)
_DASHBOARD_SUMMARY_TTL_SECONDS = 10
_dashboard_summary_cache: dict[str, object] = {}
_dashboard_summary_lock = Lock()
_PAGE_VIEW_TTL_SECONDS = 30
_page_view_cache: dict[tuple[int, str], datetime] = {}
_page_view_cache_lock = Lock()


def _derived_dashboard_health_counts(db: Session, devices: list[Device]) -> dict[str, int]:
    states = ("online", "offline", "degraded", "stale", "unknown")
    counts = {state: 0 for state in states}
    for device in devices:
        status = derive_device_health(db, device).get("status")
        counts[status if status in counts else "unknown"] += 1
    return counts


def audit(db: Session, user_id: int | None, action: str, resource_name: str, outcome: str = "success") -> None:
    db.add(AuditLog(user_id=user_id, action=action, resource_name=resource_name, outcome=outcome))
    db.commit()


def _client_ip(request: Request) -> str | None:
    peer = request.client.host if request.client else None
    trusted = get_settings().trusted_proxies
    if peer and peer in trusted:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            candidate = forwarded.split(",", 1)[0].strip()
            try:
                ipaddress.ip_address(candidate)
                return candidate
            except ValueError:
                pass
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            try:
                ipaddress.ip_address(real_ip.strip())
                return real_ip.strip()
            except ValueError:
                pass
    return peer


def _audit_request_context(request: Request) -> dict[str, str | None]:
    return {
        "request_method": request.method,
        "request_path": request.url.path,
        "source_ip": _client_ip(request),
        "user_agent": request.headers.get("user-agent"),
    }


def _user_read(user: User) -> UserRead:
    role_name = user.role.role_name if user.role else None
    permissions = [perm.code for perm in user.role.permissions] if user.role else []
    return UserRead(
        id=user.id,
        uuid=user.uuid,
        name=user.name,
        email=user.email,
        role_id=user.role_id,
        role_name=role_name,
        authority_level=user.role.authority_level if user.role else 0,
        permissions=permissions,
        status=user.status,
        created_at=user.created_at,
        max_concurrent_sessions=user.max_concurrent_sessions,
    )


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, object]:
    database_now = db.execute(select(func.now())).scalar()
    current_database = db.execute(select(func.current_database())).scalar()
    migration_status = get_migration_status(db.get_bind())
    return {
        "status": "ok",
        "database": {
            "connected": True,
            "name": current_database,
            "server_time": database_now.isoformat() if database_now else None,
        },
        "migrations": migration_status,
    }


@router.post("/auth/login", response_model=Token)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> Token:
    user = db.query(User).filter(User.email == payload.email).first()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if user is None:
        record_audit_event(db, action="LOGIN_FAILED", resource_type="user", outcome="failure", failure_reason="invalid_credentials", **_audit_request_context(request))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.status == "locked":
        locked_until = user.locked_until
        if locked_until is not None and locked_until.tzinfo is not None: locked_until = locked_until.replace(tzinfo=None)
        if locked_until is not None and locked_until > now:
            record_audit_event(db, actor=user, action="LOGIN_FAILED", resource_type="user", resource_id=user.id, target_user_id=user.id, outcome="failure", failure_reason="account_unavailable", **_audit_request_context(request))
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        user.status, user.failed_login_attempts, user.locked_until = "active", 0, None
        db.commit()
    if user.status != "active":
        record_audit_event(db, actor=user, action="LOGIN_FAILED", resource_type="user", resource_id=user.id, target_user_id=user.id, outcome="failure", failure_reason="account_unavailable", **_audit_request_context(request))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= 5:
            user.status, user.locked_until = "locked", now + timedelta(minutes=15)
        db.commit()
        record_audit_event(db, actor=user, action="LOGIN_FAILED", resource_type="user", resource_id=user.id, target_user_id=user.id, outcome="failure", failure_reason="invalid_credentials", **_audit_request_context(request))
        if user.status == "locked": record_audit_event(db, actor=user, action="ACCOUNT_LOCKED", resource_type="user", resource_id=user.id, target_user_id=user.id, outcome="failure", failure_reason="five_failed_attempts", **_audit_request_context(request))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    # Expired sessions must never consume a concurrent-session slot.
    db.query(UserSession).filter(
        UserSession.user_id == user.id,
        UserSession.revoked_at.is_(None),
        UserSession.expires_at <= now,
    ).update({"revoked_at": now, "revoke_reason": "expired"}, synchronize_session=False)
    # If the same browser reconnects after a dropped logout request, replace
    # its old session instead of locking the user out at the session limit.
    client_ip = request.client.host if request.client else None
    client_agent = request.headers.get("user-agent")
    if client_ip and client_agent:
        db.query(UserSession).filter(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
            UserSession.ip_address == client_ip,
            UserSession.user_agent == client_agent,
        ).update({"revoked_at": now, "revoke_reason": "replaced_login"}, synchronize_session=False)
    active = db.query(UserSession).filter(UserSession.user_id == user.id, UserSession.revoked_at.is_(None), UserSession.expires_at > now).count()
    # The protected Super Admin account always has three concurrent slots,
    # including accounts created before the session-limit migration.
    if is_super_admin(user):
        user.max_concurrent_sessions = 3
        limit = 3
    else:
        limit = max(1, min(10, user.max_concurrent_sessions or 1))
    # Super Admin is never blocked by the concurrent-session guard.
    if not is_super_admin(user) and active >= limit:
        record_audit_event(db, actor=user, action="SESSION_LIMIT_REACHED", resource_type="user", resource_id=user.id, target_user_id=user.id, outcome="failure", failure_reason="maximum_active_sessions", **_audit_request_context(request))
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="Maximum active sessions reached.")
    user.failed_login_attempts, user.locked_until, user.last_login_at = 0, None, datetime.now(timezone.utc)
    session_id = uuid.uuid4().hex
    expires = now + timedelta(minutes=get_settings().access_token_expire_minutes)
    db.add(UserSession(session_id=session_id, user_id=user.id, created_at=now, last_seen_at=now, expires_at=expires, ip_address=request.client.host if request.client else None, user_agent=request.headers.get("user-agent"), login_method="password"))
    db.commit()
    record_audit_event(db, actor=user, action="LOGIN_SUCCESS", resource_type="user", resource_id=user.id, target_user_id=user.id, outcome="success", metadata={"session_id": session_id}, **_audit_request_context(request))
    return Token(access_token=create_access_token(user.email, jti=session_id))


@router.post("/auth/logout")
def logout(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme), current_user: User = Depends(get_current_user), db: Session = Depends(get_db), request: Request = None):
    claims = decode_access_token_claims(credentials.credentials) if credentials else None
    session_id = claims.get("jti") if claims else None
    if session_id:
        session = db.query(UserSession).filter(UserSession.session_id == session_id, UserSession.user_id == current_user.id).first()
        if session and session.revoked_at is None:
            session.revoked_at = datetime.now(timezone.utc).replace(tzinfo=None)
            session.revoke_reason = "logout"
            db.commit()
            record_audit_event(db, actor=current_user, action="LOGOUT", resource_type="user", resource_id=current_user.id, target_user_id=current_user.id, outcome="success", metadata={"session_id": session_id}, **_audit_request_context(request))
    return {"detail": "Logged out"}


@router.get("/auth/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return _user_read(current_user)


role_crud = CRUDRouterMixin(Role)
permission_crud = CRUDRouterMixin(Permission)
user_crud = CRUDRouterMixin(User)
organization_crud = CRUDRouterMixin(Organization)
site_crud = CRUDRouterMixin(Site)
vendor_crud = CRUDRouterMixin(Vendor)
device_type_crud = CRUDRouterMixin(DeviceType)
device_crud = CRUDRouterMixin(Device)
credential_crud = CRUDRouterMixin(DeviceCredential)
interface_crud = CRUDRouterMixin(Interface)
job_crud = CRUDRouterMixin(MonitoringJob)
metric_crud = CRUDRouterMixin(DeviceMetric)
threshold_crud = CRUDRouterMixin(Threshold)
alert_crud = CRUDRouterMixin(Alert)
event_crud = CRUDRouterMixin(Event)
notification_crud = CRUDRouterMixin(Notification)
report_crud = CRUDRouterMixin(Report)
audit_crud = CRUDRouterMixin(AuditLog)

from backend.services.report_management import build_report_rows as _build_report_rows
from backend.services.report_schedule import sync_report_schedule, remove_report_schedule, set_report_scheduler, restore_report_schedules
from backend.services.report_csv import generate_report_csv
from backend.services.report_schedule import REPORT_STORAGE_DIR

def _validate_report_scope(current_user: User, db: Session, device_id: int | None, site_id: int | None) -> None:
    if site_id is not None and not can_access_site(current_user, site_id):
        raise HTTPException(status_code=404, detail="Report scope not found")
    if device_id is not None:
        device = db.query(Device).filter(Device.id == device_id, Device.deleted_at.is_(None)).first()
        if device is None or not can_access_site(current_user, device.site_id):
            raise HTTPException(status_code=404, detail="Report scope not found")


def _run_report_management(db: Session, filters: ReportManagementFilters):
    try:
        return _build_report_rows(db, filters)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

@router.get("/reports/management")
def get_report_management(
    device_type_id: int | None = None,
    device_id: int | None = None,
    site_id: int | None = None,
    device_status: Literal["all", "up", "down", "unreachable"] = "all",
    alert_severity: Literal["all", "critical", "high", "medium", "low", "warning", "info"] = "all",
    protocol: Literal["all", "snmp", "icmp"] = "all",
    period: Literal["today", "yesterday", "weekly", "monthly", "yearly", "custom"] = "today",
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("reports:read")),
):
    _validate_report_scope(current_user, db, device_id, site_id)
    filters = ReportManagementFilters(
        device_type_id=device_type_id,
        device_id=device_id,
        site_id=site_id, device_status=device_status, alert_severity=alert_severity,
        protocol=protocol, period=period,
        start_date=start_date, end_date=end_date,
    )
    summary, _ = _run_report_management(db, filters)
    return summary


def _schedule_filter_values(values: dict) -> dict:
    # Validate only report filters; recurring windows are calculated at runtime.
    validated = ReportManagementFilters(**values)
    validated.period = "custom"
    validated.start_date = None
    validated.end_date = None
    return validated.model_dump()


@router.get("/reports/schedules", response_model=list[ReportScheduleRead])
def list_report_schedules(db: Session = Depends(get_db), _: User = Depends(require_permission("reports:read"))):
    return db.query(ReportSchedule).order_by(ReportSchedule.id.asc()).all()


@router.post("/reports/schedules", response_model=ReportScheduleRead, status_code=status.HTTP_201_CREATED)
def create_report_schedule(payload: ReportScheduleCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("reports:read"))):
    item = ReportSchedule(**payload.model_dump(exclude={"filters"}), filters=_schedule_filter_values(payload.filters), created_by=current_user.id)
    db.add(item); db.commit(); db.refresh(item)
    sync_report_schedule(item); db.commit(); db.refresh(item)
    return item


@router.put("/reports/schedules/{item_id}", response_model=ReportScheduleRead)
def update_report_schedule(item_id: int, payload: ReportScheduleUpdate, db: Session = Depends(get_db), _: User = Depends(require_permission("reports:read"))):
    item = db.query(ReportSchedule).filter(ReportSchedule.id == item_id).first()
    if item is None: raise HTTPException(status_code=404, detail="Report schedule not found")
    values = payload.model_dump(exclude_unset=True)
    if "filters" in values: values["filters"] = _schedule_filter_values(values["filters"])
    for key, value in values.items(): setattr(item, key, value)
    db.commit(); db.refresh(item); sync_report_schedule(item); db.commit(); db.refresh(item)
    return item


@router.delete("/reports/schedules/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report_schedule(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("reports:read"))):
    item = db.query(ReportSchedule).filter(ReportSchedule.id == item_id).first()
    if item is None: raise HTTPException(status_code=404, detail="Report schedule not found")
    remove_report_schedule(item.id); db.delete(item); db.commit()


@router.get("/reports/generated", response_model=list[GeneratedReportRead])
def list_generated_reports(schedule_id: int | None = None, report_status: str | None = None, db: Session = Depends(get_db), _: User = Depends(require_permission("reports:read"))):
    query = db.query(GeneratedReport)
    if schedule_id is not None: query = query.filter(GeneratedReport.schedule_id == schedule_id)
    if report_status is not None: query = query.filter(GeneratedReport.status == report_status)
    return query.order_by(GeneratedReport.generated_at.desc(), GeneratedReport.id.desc()).limit(100).all()


@router.get("/reports/generated/{item_id}/download")
def download_generated_report(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("reports:read"))):
    item = db.query(GeneratedReport).filter(GeneratedReport.id == item_id).first()
    if item is None: raise HTTPException(status_code=404, detail="Generated report not found")
    if item.status != "SUCCESS" or not item.file_path: raise HTTPException(status_code=404, detail="Generated report is not available")
    base = REPORT_STORAGE_DIR.resolve()
    path = Path(item.file_path).resolve()
    if base not in path.parents: raise HTTPException(status_code=404, detail="Generated report file is invalid")
    if not path.is_file(): raise HTTPException(status_code=404, detail="Generated report file not found")
    return FileResponse(path, media_type="text/csv", filename=path.name)


@router.get("/reports/management/email-schedule")
def get_report_management_email_schedule(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("reports:read")),
):
    from backend.services.report_email import report_email_status
    return report_email_status(db)


@router.get("/reports/management/options")
def get_report_management_options(db: Session = Depends(get_db), current_user: User = Depends(require_permission("reports:read"))):
    accessible_site_ids = get_accessible_site_ids(current_user)
    devices_query = db.query(Device).filter(Device.deleted_at.is_(None))
    sites_query = db.query(Site).filter(Site.deleted_at.is_(None))
    if accessible_site_ids is not None:
        devices_query = devices_query.filter(Device.site_id.in_(accessible_site_ids) if accessible_site_ids else False)
        sites_query = sites_query.filter(Site.id.in_(accessible_site_ids) if accessible_site_ids else False)
    devices = devices_query.order_by(Device.hostname.asc()).all()
    return {
        "device_types": [ReportManagementOptionsItem(id=row.id, name=row.name) for row in db.query(DeviceType).filter(DeviceType.deleted_at.is_(None)).order_by(DeviceType.name.asc()).all()],
        "sites": [ReportManagementOptionsItem(id=row.id, name=row.name) for row in sites_query.order_by(Site.name.asc()).all()],
        "devices": [ReportManagementDeviceOption(id=d.id, hostname=d.hostname, ip_address=d.ip_address, device_type_id=d.device_type_id, site_id=d.site_id, status=d.status) for d in devices],
    }


def _format_duration(seconds: int | float | None) -> str:
    total = max(0, round(float(seconds or 0)))
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{days}d {hours}h {minutes}m {secs}s"


@router.get("/reports/management/export")
def export_report_management(
    format: str = "csv",
    device_type_id: int | None = None,
    device_id: int | None = None,
    site_id: int | None = None,
    device_status: Literal["all", "up", "down", "unreachable"] = "all",
    alert_severity: Literal["all", "critical", "high", "medium", "low", "warning", "info"] = "all",
    protocol: Literal["all", "snmp", "icmp"] = "all",
    period: Literal["today", "yesterday", "weekly", "monthly", "yearly", "custom"] = "today",
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("reports:read")),
):
    _validate_report_scope(current_user, db, device_id, site_id)
    filters = ReportManagementFilters(
        device_type_id=device_type_id,
        device_id=device_id,
        site_id=site_id, device_status=device_status, alert_severity=alert_severity,
        protocol=protocol, period=period,
        start_date=start_date, end_date=end_date,
    )
    summary, rows = _run_report_management(db, filters)
    if format == "csv":
        content = generate_report_csv(rows)
        filename = f"report-management-{summary.period_start.date()}-{summary.period_end.date()}.csv"
        return StreamingResponse(iter([content]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported export format on backend")


def _is_protected_super_admin_role(role: Role | None) -> bool:
    return bool(role and role.role_name == "Super Admin" and role.authority_level == 100 and role.is_system_role and not role.is_assignable)


def _is_protected_super_admin_user(user: User | None) -> bool:
    return bool(user and _is_protected_super_admin_role(user.role))


def _reject_protected_role(role: Role | None) -> None:
    if _is_protected_super_admin_role(role):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")


def _reject_protected_user(user: User | None) -> None:
    if _is_protected_super_admin_user(user):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")


# ---------------------------------------------------------------- Roles
@router.get("/roles", response_model=list[RoleRead])
def list_roles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("roles:read"))):
    return (db.query(Role)
        .filter(~((Role.role_name == "Super Admin") & (Role.authority_level == 100) & (Role.is_system_role.is_(True)) & (Role.is_assignable.is_(False))))
        .order_by(Role.id).offset(skip).limit(min(limit, 500)).all())


@router.post("/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
def create_role(payload: RoleCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("roles:create"))):
    if payload.role_name.strip() == "Super Admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Protected role cannot be created")
    if not can_create_role(current_user, payload.authority_level):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot create a role at this authority level")
    item = role_crud.create(db, payload)
    audit(db, current_user.id, "CREATE", "roles")
    return item


@router.get("/roles/{item_id}", response_model=RoleRead)
def get_role(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("roles:read"))):
    role = role_crud.get(db, item_id)
    _reject_protected_role(role)
    return role


@router.patch("/roles/{item_id}", response_model=RoleRead)
def update_role(item_id: int, payload: RoleUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("roles:update"))):
    target = role_crud.get(db, item_id)
    _reject_protected_role(target)
    if not can_modify_role(current_user, target):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient authority to modify this role")
    if payload.authority_level is not None and not can_create_role(current_user, payload.authority_level):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot raise a role to this authority level")
    item = role_crud.update(db, item_id, payload)
    audit(db, current_user.id, "UPDATE", "roles")
    return item


@router.delete("/roles/{item_id}")
def delete_role(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("roles:delete"))):
    target = role_crud.get(db, item_id)
    _reject_protected_role(target)
    if not can_modify_role(current_user, target):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient authority to delete this role")
    result = role_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "roles")
    return result


@router.get("/roles/{item_id}/permissions", response_model=RoleWithPermissions)
def get_role_permissions(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("roles:read"))):
    role = role_crud.get(db, item_id)
    _reject_protected_role(role)
    return role


@router.put("/roles/{item_id}/permissions", response_model=RoleWithPermissions)
def assign_role_permissions(item_id: int, payload: PermissionIds, db: Session = Depends(get_db), current_user: User = Depends(require_permission("roles:update"))):
    role = role_crud.get(db, item_id)
    _reject_protected_role(role)
    if not can_modify_role(current_user, role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient authority to modify this role")
    permissions = db.query(Permission).filter(Permission.id.in_(payload.permission_ids)).all()
    if len(permissions) != len(set(payload.permission_ids)):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="One or more permission IDs are invalid")
    role.permissions = permissions
    db.commit()
    db.refresh(role)
    audit(db, current_user.id, "ASSIGN_PERMISSIONS", f"role:{role.id}")
    return role


@router.post("/roles/{item_id}/permissions/{permission_id}", response_model=RoleWithPermissions)
def add_role_permission(item_id: int, permission_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("roles:update"))):
    role = role_crud.get(db, item_id)
    _reject_protected_role(role)
    if not can_modify_role(current_user, role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient authority to modify this role")
    permission = permission_crud.get(db, permission_id)
    if permission not in role.permissions:
        role.permissions.append(permission)
        db.commit()
        db.refresh(role)
    audit(db, current_user.id, "ADD_PERMISSION", f"role:{role.id}")
    return role


@router.delete("/roles/{item_id}/permissions/{permission_id}", response_model=RoleWithPermissions)
def remove_role_permission(item_id: int, permission_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("roles:update"))):
    role = role_crud.get(db, item_id)
    _reject_protected_role(role)
    if not can_modify_role(current_user, role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient authority to modify this role")
    permission = permission_crud.get(db, permission_id)
    if permission in role.permissions:
        role.permissions.remove(permission)
        db.commit()
        db.refresh(role)
    audit(db, current_user.id, "REMOVE_PERMISSION", f"role:{role.id}")
    return role


# ---------------------------------------------------------------- Permissions
@router.get("/permissions", response_model=list[PermissionRead])
def list_permissions(module: str | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("permissions:read"))):
    query = db.query(Permission)
    if module:
        query = query.filter(Permission.module == module)
    return query.order_by(Permission.module, Permission.action).offset(skip).limit(min(limit, 500)).all()


@router.post("/permissions", response_model=PermissionRead, status_code=status.HTTP_201_CREATED)
def create_permission(payload: PermissionCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("permissions:create"))):
    if not can_manage_permission_definition(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Super Admin may manage permission definitions")
    item = permission_crud.create(db, payload)
    audit(db, current_user.id, "CREATE", "permissions")
    return item


@router.get("/permissions/{item_id}", response_model=PermissionRead)
def get_permission(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("permissions:read"))):
    return permission_crud.get(db, item_id)


@router.patch("/permissions/{item_id}", response_model=PermissionRead)
def update_permission(item_id: int, payload: PermissionUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("permissions:update"))):
    if not can_manage_permission_definition(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Super Admin may manage permission definitions")
    item = permission_crud.update(db, item_id, payload)
    audit(db, current_user.id, "UPDATE", "permissions")
    return item


@router.delete("/permissions/{item_id}")
def delete_permission(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("permissions:delete"))):
    if not can_manage_permission_definition(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Super Admin may manage permission definitions")
    result = permission_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "permissions")
    return result


class UserSiteAssignments(BaseModel):
    site_ids: list[int] = []


# ---------------------------------------------------------------- Users
@router.get("/users", response_model=list[UserRead])
def list_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("users:read"))):
    users = (
        db.query(User)
        .options(joinedload(User.role).joinedload(Role.permissions))
        .filter(~User.role.has((Role.role_name == "Super Admin") & (Role.authority_level == 100) & (Role.is_system_role.is_(True)) & (Role.is_assignable.is_(False))))
        .order_by(User.id)
        .offset(skip)
        .limit(min(limit, 500))
        .all()
    )
    return [_user_read(user) for user in users]


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_permission("users:create"))):
    data = payload.model_dump()
    data["password_hash"] = hash_password(data.pop("password"))
    if data.get("role_id") is not None:
        role = role_crud.get(db, data["role_id"])
        if not can_assign_role(current_user, role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign this role")
    item = user_crud.create(db, data)
    record_audit_event(db, actor=current_user, action="USER_CREATED", resource_type="user", resource_id=item.id, target_user_id=item.id, new_values={"name": item.name, "email": item.email, "role_id": item.role_id, "status": item.status}, **_audit_request_context(request))
    return _user_read(item)


@router.get("/users/{item_id}", response_model=UserRead)
def get_user(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("users:read"))):
    target = user_crud.get(db, item_id)
    _reject_protected_user(target)
    return _user_read(target)


@router.get("/users/{item_id}/sites")
def get_user_sites(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("users:read"))):
    target = user_crud.get(db, item_id)
    _reject_protected_user(target)
    if not can_manage_user(current_user, target):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient authority to view this user's site assignments")
    return {"site_ids": [site.id for site in target.sites]}


@router.put("/users/{item_id}/sites")
def replace_user_sites(item_id: int, payload: UserSiteAssignments, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_permission("users:update"))):
    target = user_crud.get(db, item_id)
    _reject_protected_user(target)
    if not can_manage_user(current_user, target):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient authority to manage this user's site assignments")
    site_ids = list(dict.fromkeys(payload.site_ids))
    if any(not isinstance(site_id, int) or isinstance(site_id, bool) or site_id <= 0 for site_id in site_ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="site_ids must contain positive integer IDs")
    sites = db.query(Site).filter(Site.id.in_(site_ids), Site.deleted_at.is_(None)).all() if site_ids else []
    found = {site.id: site for site in sites}
    if len(found) != len(site_ids):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="One or more site IDs are invalid")
    if not is_super_admin(current_user):
        inaccessible = [site_id for site_id in site_ids if not can_access_site(current_user, site_id)]
        if inaccessible:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign sites outside your access scope")
    old_ids = sorted(site.id for site in target.sites)
    target.sites = [found[site_id] for site_id in site_ids]
    db.commit()
    record_audit_event(db, actor=current_user, action="USER_SITE_ASSIGNMENTS_CHANGED", resource_type="user", resource_id=target.id, target_user_id=target.id, outcome="success", old_values={"site_ids": old_ids}, new_values={"site_ids": sorted(site_ids)}, **_audit_request_context(request))
    return {"site_ids": sorted(site_ids)}


@router.post("/users/{item_id}/role", response_model=UserRead)
def assign_user_role(item_id: int, payload: AssignRoleRequest, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_permission("users:update"))):
    target = user_crud.get(db, item_id)
    _reject_protected_user(target)
    role = role_crud.get(db, payload.role_id)
    if not can_manage_user(current_user, target):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient authority to manage this user")
    if not can_assign_role(current_user, role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign this role")
    old_role_id = target.role_id
    item = user_crud.update(db, item_id, {"role_id": payload.role_id})
    record_audit_event(db, actor=current_user, action="USER_ROLE_CHANGED", resource_type="user", resource_id=item.id, target_user_id=item.id, old_values={"role_id": old_role_id}, new_values={"role_id": item.role_id}, **_audit_request_context(request))
    return _user_read(item)


@router.patch("/users/{item_id}/status", response_model=UserRead)
def update_user_status(item_id: int, payload: UserStatusUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_permission("users:update"))):
    target = user_crud.get(db, item_id)
    _reject_protected_user(target)
    if not can_manage_user(current_user, target):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient authority to change this user status")
    old_status = target.status
    target.status = payload.status
    target.locked_until = payload.suspended_until if payload.status == "suspended" else None
    db.commit()
    db.refresh(target)
    record_audit_event(db, actor=current_user, action="USER_STATUS_CHANGED", resource_type="user", resource_id=target.id, target_user_id=target.id, old_values={"status": old_status}, new_values={"status": target.status}, **_audit_request_context(request))
    return _user_read(target)


@router.patch("/users/{item_id}", response_model=UserRead)
def update_user(item_id: int, payload: UserUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_permission("users:update"))):
    target = user_crud.get(db, item_id)
    _reject_protected_user(target)
    if not can_manage_user(current_user, target):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient authority to manage this user")
    old_values = {"name": target.name, "email": target.email, "role_id": target.role_id}
    data = payload.model_dump(exclude_unset=True)
    if "max_concurrent_sessions" in data:
        if not is_super_admin(current_user) or _is_protected_super_admin_user(target):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Super Admin may change session limits")
        data["max_concurrent_sessions"] = max(1, min(10, int(data["max_concurrent_sessions"])))
    if "role_id" in data:
        role = role_crud.get(db, data["role_id"])
        if not can_assign_role(current_user, role):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot assign this role")
    if "password" in data:
        data["password_hash"] = hash_password(data.pop("password"))
    item = user_crud.update(db, item_id, data)
    record_audit_event(db, actor=current_user, action="USER_UPDATED", resource_type="user", resource_id=item.id, target_user_id=item.id, old_values=old_values, new_values={"name": item.name, "email": item.email, "role_id": item.role_id}, **_audit_request_context(request))
    return _user_read(item)


@router.delete("/users/{item_id}")
def delete_user(item_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_permission("users:delete"))):
    target = user_crud.get(db, item_id)
    _reject_protected_user(target)
    if not can_manage_user(current_user, target):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient authority to manage this user")
    result = user_crud.delete(db, item_id)
    record_audit_event(db, actor=current_user, action="USER_DELETED", resource_type="user", resource_id=target.id, target_user_id=target.id, old_values={"name": target.name, "email": target.email, "role_id": target.role_id, "status": target.status}, **_audit_request_context(request))
    return result


@router.get("/users/{item_id}/sessions", response_model=list[UserSessionRead])
def list_user_sessions(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("users:read"))):
    if not is_super_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Super Admin may manage user sessions")
    target = user_crud.get(db, item_id)
    _reject_protected_user(target)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    sessions = db.query(UserSession).filter(UserSession.user_id == target.id).order_by(UserSession.created_at.desc()).limit(100).all()
    return [UserSessionRead.model_validate({**{key: getattr(item, key) for key in ("session_id", "created_at", "last_seen_at", "expires_at", "revoked_at", "revoke_reason", "ip_address", "user_agent")}, "active": item.revoked_at is None and item.expires_at > now}) for item in sessions]


@router.delete("/users/{item_id}/sessions/{session_id}")
def revoke_user_session(item_id: int, session_id: str, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_permission("users:update"))):
    if not is_super_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Super Admin may manage user sessions")
    target = user_crud.get(db, item_id)
    _reject_protected_user(target)
    session = db.query(UserSession).filter(UserSession.user_id == target.id, UserSession.session_id == session_id).first()
    if session is None: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    session.revoked_at, session.revoke_reason = datetime.now(timezone.utc).replace(tzinfo=None), "admin_revoke"
    db.commit()
    record_audit_event(db, actor=current_user, action="SESSION_REVOKED", resource_type="user", resource_id=target.id, target_user_id=target.id, outcome="success", metadata={"session_id": session_id}, **_audit_request_context(request))
    return {"detail": "Session revoked"}


@router.post("/users/{item_id}/sessions/revoke-all")
def revoke_all_user_sessions(item_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(require_permission("users:update"))):
    if not is_super_admin(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only Super Admin may manage user sessions")
    target = user_crud.get(db, item_id)
    _reject_protected_user(target)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    count = db.query(UserSession).filter(UserSession.user_id == target.id, UserSession.revoked_at.is_(None)).update({"revoked_at": now, "revoke_reason": "admin_revoke_all"}, synchronize_session=False)
    db.commit()
    record_audit_event(db, actor=current_user, action="SESSION_REVOKED", resource_type="user", resource_id=target.id, target_user_id=target.id, outcome="success", metadata={"revoke_all": True, "count": count}, **_audit_request_context(request))
    return {"revoked": count}


@router.get("/users/{item_id}/activity")
def user_activity(item_id: int, action: str | None = None, outcome: str | None = None, source_ip: str | None = None, start_date: datetime | None = None, end_date: datetime | None = None, limit: int = 50, offset: int = 0, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit_logs:read"))):
    target = user_crud.get(db, item_id)
    _reject_protected_user(target)
    if not can_view_audit_actor(current_user, target):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot view this user's activity")
    query = db.query(AuditLog).filter((AuditLog.target_user_id == target.id) | (AuditLog.user_id == target.id))
    if action: query = query.filter(AuditLog.action == action)
    if outcome: query = query.filter(AuditLog.outcome == outcome)
    if source_ip: query = query.filter(AuditLog.source_ip == source_ip)
    if start_date: query = query.filter(AuditLog.timestamp >= start_date)
    if end_date: query = query.filter(AuditLog.timestamp <= end_date)
    total = query.count()
    items = query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).offset(max(0, offset)).limit(min(max(1, limit), 200)).all()
    return {"items": items, "total": total, "limit": min(max(1, limit), 200), "offset": max(0, offset)}


# ---------------------------------------------------------------- Branding / Organizations
@router.get("/branding", response_model=BrandingRead)
def get_branding() -> BrandingRead:
    """Expose non-sensitive tenant branding configured by the backend."""
    settings = get_settings()
    return BrandingRead(
        application_name=settings.branding_application_name,
        logo_url=settings.branding_logo_url or None,
        allowed_themes=settings.allowed_themes or ["light"],
    )


@router.get("/organizations", response_model=list[OrganizationRead])
def list_organizations(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("organizations:read"))):
    return organization_crud.list(db, skip, limit)


@router.post("/organizations", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED)
def create_organization(payload: OrganizationCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("organizations:create"))):
    item = organization_crud.create(db, payload)
    audit(db, current_user.id, "CREATE", "organizations")
    return item


@router.get("/organizations/{item_id}", response_model=OrganizationRead)
def get_organization(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("organizations:read"))):
    return organization_crud.get(db, item_id)


@router.patch("/organizations/{item_id}", response_model=OrganizationRead)
def update_organization(item_id: int, payload: OrganizationUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("organizations:update"))):
    item = organization_crud.update(db, item_id, payload)
    audit(db, current_user.id, "UPDATE", "organizations")
    return item


@router.delete("/organizations/{item_id}")
def delete_organization(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("organizations:delete"))):
    result = organization_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "organizations")
    return result


# ---------------------------------------------------------------- Sites
@router.get("/sites", response_model=list[SiteRead])
def list_sites(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: User = Depends(require_permission("sites:read"))):
    query = db.query(Site).filter(Site.deleted_at.is_(None))
    accessible_site_ids = get_accessible_site_ids(current_user)
    if accessible_site_ids is not None:
        if not accessible_site_ids:
            return []
        query = query.filter(Site.id.in_(accessible_site_ids))
    return query.order_by(Site.id).offset(skip).limit(min(limit, 500)).all()


@router.post("/sites", response_model=SiteRead, status_code=status.HTTP_201_CREATED)
def create_site(payload: SiteCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("sites:create"))):
    item = site_crud.create(db, payload)
    audit(db, current_user.id, "CREATE", "sites")
    return item


@router.get("/sites/{item_id}", response_model=SiteRead)
def get_site(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("sites:read"))):
    item = site_crud.get(db, item_id)
    if not can_access_site(current_user, item_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Site {item_id} not found")
    return item


@router.patch("/sites/{item_id}", response_model=SiteRead)
def update_site(item_id: int, payload: SiteUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("sites:update"))):
    item = site_crud.get(db, item_id)
    if not can_access_site(current_user, item_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Site {item_id} not found")
    item = site_crud.update(db, item_id, payload)
    audit(db, current_user.id, "UPDATE", "sites")
    return item


@router.delete("/sites/{item_id}")
def delete_site(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("sites:delete"))):
    site_crud.get(db, item_id)
    if not can_access_site(current_user, item_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Site {item_id} not found")
    result = site_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "sites")
    return result


# ---------------------------------------------------------------- Vendors
@router.get("/vendors", response_model=list[VendorRead])
def list_vendors(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("vendors:read"))):
    return vendor_crud.list(db, skip, limit)


@router.post("/vendors", response_model=VendorRead, status_code=status.HTTP_201_CREATED)
def create_vendor(payload: VendorCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("vendors:create"))):
    item = vendor_crud.create(db, payload)
    audit(db, current_user.id, "CREATE", "vendors")
    return item


@router.get("/vendors/{item_id}", response_model=VendorRead)
def get_vendor(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("vendors:read"))):
    return vendor_crud.get(db, item_id)


@router.patch("/vendors/{item_id}", response_model=VendorRead)
def update_vendor(item_id: int, payload: VendorUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("vendors:update"))):
    item = vendor_crud.update(db, item_id, payload)
    audit(db, current_user.id, "UPDATE", "vendors")
    return item


@router.delete("/vendors/{item_id}")
def delete_vendor(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("vendors:delete"))):
    result = vendor_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "vendors")
    return result


# ---------------------------------------------------------------- Device types
@router.get("/device-types", response_model=list[DeviceTypeRead])
def list_device_types(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("device_types:read"))):
    return device_type_crud.list(db, skip, limit)


@router.post("/device-types", response_model=DeviceTypeRead, status_code=status.HTTP_201_CREATED)
def create_device_type(payload: DeviceTypeCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("device_types:create"))):
    item = device_type_crud.create(db, payload)
    audit(db, current_user.id, "CREATE", "device_types")
    return item


@router.get("/device-types/{item_id}", response_model=DeviceTypeRead)
def get_device_type(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("device_types:read"))):
    return device_type_crud.get(db, item_id)


@router.patch("/device-types/{item_id}", response_model=DeviceTypeRead)
def update_device_type(item_id: int, payload: DeviceTypeUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("device_types:update"))):
    item = device_type_crud.update(db, item_id, payload)
    audit(db, current_user.id, "UPDATE", "device_types")
    return item


@router.delete("/device-types/{item_id}")
def delete_device_type(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("device_types:delete"))):
    item = device_type_crud.get(db, item_id)
    active_device_count = (
        db.query(func.count(Device.id))
        .filter(Device.device_type_id == item_id, Device.deleted_at.is_(None))
        .scalar()
    ) or 0
    if active_device_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Cannot delete device type "{item.name}" because it is assigned to {active_device_count} device(s).',
        )

    active_threshold_count = (
        db.query(func.count(Threshold.id))
        .filter(Threshold.device_type_id == item_id, Threshold.deleted_at.is_(None))
        .scalar()
    ) or 0
    if active_threshold_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'Cannot delete device type "{item.name}" because it is used by {active_threshold_count} threshold(s).',
        )

    db.delete(item)
    db.commit()
    result = {"detail": f'DeviceType {item_id} deleted'}
    audit(db, current_user.id, "DELETE", "device_types")
    return result


# ---------------------------------------------------------------- Devices
@router.get("/devices", response_model=list[DeviceRead])
def list_devices(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: User = Depends(require_permission("devices:read"))):
    devices = (
        db.query(Device)
        .options(
            load_only(
                Device.id, Device.site_id, Device.hostname, Device.ip_address,
                Device.mac_address, Device.vendor_id, Device.device_type_id,
                Device.serial_number, Device.model, Device.firmware_version,
                Device.status, Device.monitoring_status, Device.last_seen,
                Device.created_at, Device.uptime_seconds, Device.downtime_seconds,
                Device.last_status_change, Device.deleted_at,
            ),
            joinedload(Device.vendor).load_only(Vendor.id, Vendor.vendor_name),
            joinedload(Device.device_type).load_only(DeviceType.id, DeviceType.name),
            joinedload(Device.credentials).load_only(DeviceCredential.device_id, DeviceCredential.snmp_version),
        )
        .filter(Device.deleted_at.is_(None))
        .filter(
            is_super_admin(current_user)
            if get_accessible_site_ids(current_user) is None
            else (Device.site_id.in_(get_accessible_site_ids(current_user)) if get_accessible_site_ids(current_user) else False)
        )
        .order_by(Device.id)
        .offset(skip)
        .limit(min(limit, 500))
        .all()
    )
    return [
        {
            "id": device.id,
            "site_id": device.site_id,
            "hostname": device.hostname,
            "ip_address": device.ip_address,
            "mac_address": device.mac_address,
            "vendor_id": device.vendor_id,
            "vendor_name": device.vendor.vendor_name if device.vendor else None,
            "device_type_id": device.device_type_id,
            "device_type": device.device_type.name if device.device_type else None,
            "serial_number": device.serial_number,
            "model": device.model,
            "firmware_version": device.firmware_version,
            "status": device.status,
            "monitoring_status": device.monitoring_status,
            "snmp_version": device.credentials[0].snmp_version if device.credentials else None,
            "last_seen": device.last_seen,
            "created_at": device.created_at,
            "uptime_seconds": device.uptime_seconds,
            "downtime_seconds": device.downtime_seconds,
            "last_status_change": device.last_status_change,
        }
        for device in devices
    ]


@router.get("/devices/options", response_model=list[DeviceOptionRead])
def list_device_options(
    skip: int = 0,
    limit: int = 500,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("devices:read")),
):
    accessible_site_ids = get_accessible_site_ids(current_user)
    devices = (
        db.query(Device)
        .options(
            load_only(
                Device.id, Device.hostname, Device.ip_address, Device.mac_address,
                Device.model, Device.status, Device.deleted_at,
            ),
            joinedload(Device.vendor).load_only(Vendor.id, Vendor.vendor_name),
            joinedload(Device.device_type).load_only(DeviceType.id, DeviceType.name),
        )
        .filter(Device.deleted_at.is_(None))
        .filter(is_super_admin(current_user) if accessible_site_ids is None else (Device.site_id.in_(accessible_site_ids) if accessible_site_ids else False))
        .order_by(Device.hostname.asc(), Device.id.asc())
        .offset(skip)
        .limit(min(limit, 1000))
        .all()
    )
    return [
        {
            "id": device.id,
            "hostname": device.hostname,
            "ip_address": device.ip_address,
            "mac_address": device.mac_address,
            "model": device.model,
            "vendor_name": device.vendor.vendor_name if device.vendor else None,
            "device_type": device.device_type.name if device.device_type else None,
            "status": device.status,
        }
        for device in devices
    ]


@router.post("/devices", response_model=DeviceRead, status_code=status.HTTP_201_CREATED)
def create_device(payload: DeviceCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("devices:create"))):
    item = device_crud.create(db, payload)
    audit(db, current_user.id, "CREATE", "devices")
    return item


# ---- Add device with auto-discovery (ping + DNS + ARP + vendor) ---- #

class DeviceAddWithDiscoveryRequest(BaseModel):
    """Request body for adding a device with automatic network probing."""
    ip_address: str
    site_id: int | None = None


@router.post("/devices/add-with-discovery", status_code=status.HTTP_201_CREATED)
def add_device_with_discovery(
    payload: DeviceAddWithDiscoveryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("devices:create")),
):
    """Add a device by IP — auto-discovers hostname, MAC, vendor, and status.

    Steps:
    1. Ping the IP to check reachability (ICMP)
    2. Reverse DNS lookup for hostname
    3. ARP cache lookup for MAC address
    4. MAC OUI vendor resolution
    5. Save device to DB with all discovered details
    """
    import time
    from backend.services.discovery import _ping, _resolve_hostname, _lookup_mac
    from vendor_map import lookup_vendor  # type: ignore

    ip = payload.ip_address.strip()
    if not ip:
        raise HTTPException(status_code=400, detail="ip_address is required")

    # ---- 1. Ping the IP to check reachability ----
    started = time.perf_counter()
    reachable = _ping(ip, timeout_ms=1000)
    rtt_ms = round((time.perf_counter() - started) * 1000, 2)

    # ---- 2. Reverse DNS hostname resolution ----
    hostname = _resolve_hostname(ip)

    # ---- 3. ARP cache MAC lookup ----
    mac_address = _lookup_mac(ip)

    # ---- 4. Vendor resolution from MAC OUI ----
    vendor_name = None
    vendor_id = None
    if mac_address:
        resolved_vendor = lookup_vendor(mac_address)
        if resolved_vendor and resolved_vendor != "Unknown":
            vendor_name = resolved_vendor
            # Try to find or create vendor record in DB
            from backend.models import Vendor as VendorModel
            existing_vendor = db.query(VendorModel).filter(
                VendorModel.vendor_name == vendor_name,
                VendorModel.deleted_at.is_(None),
            ).first()
            if existing_vendor:
                vendor_id = existing_vendor.id

    # ---- 5. Determine status ----
    device_status = "online" if reachable else "offline"

    # ---- 6. Check if device already exists ----
    existing_device = db.query(Device).filter(
        Device.ip_address == ip,
        Device.deleted_at.is_(None),
    ).first()
    if existing_device:
        # Update existing device with fresh discovery data
        existing_device.status = device_status
        existing_device.hostname = hostname or existing_device.hostname
        existing_device.mac_address = mac_address or existing_device.mac_address
        if vendor_id:
            existing_device.vendor_id = vendor_id
        if reachable:
            existing_device.last_seen = datetime.utcnow()
        db.flush()
        audit(db, current_user.id, "UPDATE", "devices")
        return {
            "device": DeviceRead.model_validate(existing_device),
            "discovery": {
                "reachable": reachable,
                "rtt_ms": rtt_ms,
                "hostname": hostname,
                "mac_address": mac_address,
                "vendor": vendor_name,
                "status": device_status,
            },
            "created": False,
        }

    # ---- 7. Create new device ----
    new_device = Device(
        ip_address=ip,
        hostname=hostname or ip,
        mac_address=mac_address,
        vendor_id=vendor_id,
        site_id=payload.site_id,
        status=device_status,
        monitoring_status=True,
        last_seen=datetime.utcnow() if reachable else None,
        last_status_change=datetime.utcnow(),
    )
    db.add(new_device)
    db.flush()
    db.refresh(new_device)
    create_device_added_alert(
        db,
        new_device.id,
        new_device.hostname,
        new_device.ip_address,
        "ICMP",
        new_device.status,
        new_device.mac_address,
    )
    audit(db, current_user.id, "CREATE", "devices")

    return {
        "device": DeviceRead.model_validate(new_device),
        "discovery": {
            "reachable": reachable,
            "rtt_ms": rtt_ms,
            "hostname": hostname,
            "mac_address": mac_address,
            "vendor": vendor_name,
            "status": device_status,
        },
        "created": True,
    }


@router.get("/devices/{item_id}", response_model=DeviceRead)
def get_device(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("devices:read"))):
    device = device_crud.get(db, item_id)
    if not can_access_site(current_user, device.site_id):
        raise HTTPException(status_code=404, detail=f"Device {item_id} not found")
    return device


@router.patch("/devices/{item_id}", response_model=DeviceRead)
def update_device(item_id: int, payload: DeviceUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("devices:update"))):
    device = device_crud.get(db, item_id)
    if not can_access_site(current_user, device.site_id):
        raise HTTPException(status_code=404, detail=f"Device {item_id} not found")
    values = payload.model_dump(exclude_unset=True)
    vendor_name = values.pop("vendor_name", None)
    if vendor_name is not None:
        vendor_name = vendor_name.strip()
        if vendor_name:
            vendor = db.query(Vendor).filter(Vendor.vendor_name.ilike(vendor_name)).first()
            if not vendor:
                vendor = Vendor(vendor_name=vendor_name)
                db.add(vendor)
                db.flush()
            values["vendor_id"] = vendor.id
        else:
            values["vendor_id"] = None
    item = device_crud.update(db, item_id, values)
    audit(db, current_user.id, "UPDATE", "devices")
    return item


@router.delete("/devices/{item_id}")
def delete_device(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("devices:delete")), background_tasks: BackgroundTasks = None):
    # Device deletion is permanent. The generic CRUD helper soft-deletes
    # models with ``deleted_at``, which leaves the device and stale discovery
    # data available for later re-discovery. Use the model cascade instead.
    device = db.query(Device).filter(Device.id == item_id).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    if not can_access_site(current_user, device.site_id):
        raise HTTPException(status_code=404, detail="Device not found")
    deleted_hostname = device.hostname
    deleted_ip = device.ip_address
    try:
        # Some legacy device tables use RESTRICT/NO ACTION foreign keys,
        # while newer tables use database cascades. Delete the targeted
        # device-owned rows explicitly so one device can always be removed.
        db.execute(text(
            "DELETE FROM notifications WHERE alert_id IN "
            "(SELECT id FROM alerts WHERE device_id = :device_id)"
        ), {"device_id": item_id})
        for table in (
            "alerts", "events", "snmp_traps", "alarms",
            "device_credentials", "interfaces", "monitoring_jobs",
            "device_metrics", "device_status_history", "device_inventory",
            "snmp_credentials", "device_performance", "cpu_statistics",
            "memory_statistics", "storage_statistics", "environment_statistics",
            "power_statistics", "poe_statistics", "vlan_information",
            "lldp_neighbors", "routing_table", "system_health",
            "polling_history", "interface_statistics", "oid_cache",
            "device_interfaces", "device_capabilities", "device_identity",
            "monitoring_configs", "latest_cpu", "latest_memory",
            "latest_storage", "latest_interface", "latest_environment",
        ):
            db.execute(text(f"DELETE FROM {table} WHERE device_id = :device_id"), {"device_id": item_id})
        db.delete(device)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        logger.exception("Failed to permanently delete device %s", item_id)
        raise HTTPException(status_code=409, detail="Device cannot be deleted because related data is still in use") from exc
    if hasattr(db, "add"):
        alert = create_operational_alert(
            db,
            title=f"Device Deleted: {deleted_hostname}",
            description=f"Device {deleted_ip} was deleted from the NMS inventory.",
            notify=False,
        )
        db.commit()
        if background_tasks is not None:
            background_tasks.add_task(_notify_alert_after_response, alert.id)
        else:
            # Preserve behavior for direct/internal callers that do not pass
            # FastAPI background tasks.
            _notify(db, alert)
    audit(db, current_user.id, "DELETE", "devices")
    return {"deleted": True, "detail": f"Device {item_id} deleted"}


@router.delete("/devices")
def delete_all_devices(db: Session = Depends(get_db), current_user: User = Depends(require_permission("devices:delete"))):
    """Hard delete all devices and their related data from the database."""
    from backend.models import Device
    
    # Get all devices
    devices = db.query(Device).all()
    count = len(devices)
    
    # Delete each device individually to trigger cascade deletes properly
    for device in devices:
        db.delete(device)
    
    db.commit()
    if hasattr(db, "add"):
        create_operational_alert(
            db,
            title="Devices Deleted",
            description=f"{count} device(s) were deleted from the NMS inventory.",
        )
        db.commit()
    audit(db, current_user.id, "DELETE", "devices")
    return {"deleted": count, "message": f"All {count} devices deleted successfully"}


@router.post("/devices/{item_id}/monitoring/{enabled}", response_model=DeviceRead)
def set_monitoring(item_id: int, enabled: bool, db: Session = Depends(get_db), current_user: User = Depends(require_permission("devices:update"))):
    item = device_crud.get(db, item_id)
    if not can_access_site(current_user, item.site_id):
        raise HTTPException(status_code=404, detail=f"Device {item_id} not found")
    item = device_crud.update(db, item_id, {"monitoring_status": enabled})
    if enabled:
        create_operational_alert(
            db,
            title=f"Monitoring Started: {item.hostname}",
            description=f"Monitoring enabled for device {item.ip_address}.",
            device_id=item.id,
        )
        db.commit()
    audit(db, current_user.id, "UPDATE", "device_monitoring")
    return item


@router.get("/devices/{item_id}/status-history", response_model=list[DeviceStatusHistoryRead])
def get_device_status_history(
    item_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("devices:read")),
):
    device = device_crud.get(db, item_id)
    if not can_access_site(current_user, device.site_id):
        raise HTTPException(status_code=404, detail=f"Device {item_id} not found")
    # Monitoring transition timestamps are stored as naive IST values for
    # legacy compatibility. Keep the API window in the same timezone and
    # expose a rolling frame of the newest 100 transitions.
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)
    since = now_ist - timedelta(hours=24)
    return (
        db.query(DeviceStatusHistory)
        .filter(
            DeviceStatusHistory.device_id == item_id,
            DeviceStatusHistory.timestamp >= since,
            DeviceStatusHistory.old_status.in_(["online", "offline"]),
            DeviceStatusHistory.new_status.in_(["online", "offline"]),
            DeviceStatusHistory.old_status != DeviceStatusHistory.new_status,
        )
        .order_by(DeviceStatusHistory.timestamp.desc())
        .offset(max(skip, 0))
        .limit(min(max(limit, 1), 100))
        .all()
    )


# ---------------------------------------------------------------- Device credentials
@router.get("/device-credentials", response_model=list[DeviceCredentialRead])
def list_credentials(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("device_credentials:read"))):
    return credential_crud.list(db, skip, limit)


@router.get("/device-credentials/{item_id}", response_model=DeviceCredentialRead)
def get_credential(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("device_credentials:read"))):
    return credential_crud.get(db, item_id)


@router.post("/device-credentials", response_model=DeviceCredentialRead, status_code=status.HTTP_201_CREATED)
def create_credential(payload: DeviceCredentialCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("device_credentials:create"))):
    data = payload.model_dump()
    for field in ("community_string", "password", "auth_password", "privacy_password", "api_token"):
        data[field] = encrypt_secret(data.get(field))
    item = credential_crud.create(db, data)
    audit(db, current_user.id, "CREATE", "device_credentials")
    return item


@router.patch("/device-credentials/{item_id}", response_model=DeviceCredentialRead)
def update_credential(item_id: int, payload: DeviceCredentialUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("device_credentials:update"))):
    data = payload.model_dump(exclude_unset=True)
    for field in ("community_string", "password", "auth_password", "privacy_password", "api_token"):
        if field in data:
            data[field] = encrypt_secret(data.get(field))
    item = credential_crud.update(db, item_id, data)
    audit(db, current_user.id, "UPDATE", "device_credentials")
    return item


@router.delete("/device-credentials/{item_id}")
def delete_credential(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("device_credentials:delete"))):
    result = credential_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "device_credentials")
    return result


# ---------------------------------------------------------------- Interfaces
@router.get("/interfaces", response_model=list[InterfaceRead])
def list_interfaces(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: User = Depends(require_permission("interfaces:read"))):
    return (
        db.query(Interface)
        .options(load_only(
            Interface.id,
            Interface.device_id,
            Interface.interface_name,
            Interface.status,
            Interface.speed,
            Interface.traffic_in,
            Interface.traffic_out,
            Interface.packet_errors,
            Interface.last_updated,
        ))
        .join(Device, Interface.device_id == Device.id)
        .filter(Device.deleted_at.is_(None))
        .filter(is_super_admin(current_user) if get_accessible_site_ids(current_user) is None else (Device.site_id.in_(get_accessible_site_ids(current_user)) if get_accessible_site_ids(current_user) else False))
        .order_by(Interface.id)
        .offset(skip)
        .limit(min(limit, 500))
        .all()
    )


@router.get("/interfaces/{item_id}", response_model=InterfaceRead)
def get_interface(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("interfaces:read"))):
    item = interface_crud.get(db, item_id)
    device = db.get(Device, item.device_id)
    if device is None or not can_access_site(current_user, device.site_id):
        raise HTTPException(status_code=404, detail=f"Interface {item_id} not found")
    return item


@router.post("/interfaces", response_model=InterfaceRead, status_code=status.HTTP_201_CREATED)
def create_interface(payload: InterfaceCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("interfaces:create"))):
    item = interface_crud.create(db, payload)
    audit(db, current_user.id, "CREATE", "interfaces")
    return item


@router.patch("/interfaces/{item_id}", response_model=InterfaceRead)
def update_interface(item_id: int, payload: InterfaceUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("interfaces:update"))):
    data = payload.model_dump(exclude_unset=True)
    data["last_updated"] = datetime.utcnow()
    item = interface_crud.update(db, item_id, data)
    audit(db, current_user.id, "UPDATE", "interfaces")
    return item


@router.delete("/interfaces/{item_id}")
def delete_interface(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("interfaces:delete"))):
    result = interface_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "interfaces")
    return result


# ---------------------------------------------------------------- Monitoring jobs
def _nms_processes() -> list[dict]:
    started = time.perf_counter()
    rows: list[dict] = []
    try:
        output = subprocess.run(["ps", "-eo", "pid=,etimes=,args="], capture_output=True, text=True, timeout=2, check=False).stdout
        for line in output.splitlines():
            parts = line.strip().split(None, 2)
            if len(parts) != 3:
                continue
            pid, elapsed, command = parts
            if not any(name in command for name in ("uvicorn", "simple_monitor.py", "continuous_monitoring.py")):
                continue
            rows.append({"pid": int(pid), "name": "Backend" if "uvicorn" in command else "Monitoring worker", "status": "running", "uptime_seconds": int(elapsed), "command": command[:180]})
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return {"response_time_ms": round((time.perf_counter() - started) * 1000, 2), "processes": rows}


@router.get("/runtime-status")
def runtime_status(_: User = Depends(require_permission("monitoring_jobs:read"))):
    return _nms_processes()


@router.post("/runtime-status/restart/{pid}")
def restart_runtime_process(pid: int, current_user: User = Depends(require_permission("monitoring_jobs:update"))):
    snapshot = _nms_processes()["processes"]
    target = next((row for row in snapshot if row["pid"] == pid and row["name"] == "Monitoring worker"), None)
    if target is None:
        raise HTTPException(status_code=404, detail="Only an active NMS monitoring worker can be restarted")
    try:
        os.kill(pid, signal.SIGTERM)
        subprocess.Popen(["nohup", "python3", "simple_monitor.py"], cwd="/home/agnigate/Desktop/NMS/hardik", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        return {"detail": "Monitoring worker restart requested", "pid": pid}
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Unable to restart worker: {exc}") from exc


@router.get("/monitoring-jobs", response_model=list[MonitoringJobRead])
def list_monitoring_jobs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("monitoring_jobs:read"))):
    return job_crud.list(db, skip, limit)


@router.get("/monitoring-jobs/{item_id}", response_model=MonitoringJobRead)
def get_monitoring_job(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("monitoring_jobs:read"))):
    return job_crud.get(db, item_id)


@router.post("/monitoring-jobs", response_model=MonitoringJobRead, status_code=status.HTTP_201_CREATED)
def create_monitoring_job(payload: MonitoringJobCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("monitoring_jobs:create"))):
    item = job_crud.create(db, payload)
    audit(db, current_user.id, "CREATE", "monitoring_jobs")
    return item


@router.patch("/monitoring-jobs/{item_id}", response_model=MonitoringJobRead)
def update_monitoring_job(item_id: int, payload: MonitoringJobUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("monitoring_jobs:update"))):
    item = job_crud.update(db, item_id, payload)
    audit(db, current_user.id, "UPDATE", "monitoring_jobs")
    return item


@router.delete("/monitoring-jobs/{item_id}")
def delete_monitoring_job(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("monitoring_jobs:delete"))):
    result = job_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "monitoring_jobs")
    return result


# ---------------------------------------------------------------- Device metrics
@router.get("/device-metrics", response_model=list[DeviceMetricRead])
def list_device_metrics(device_id: int | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("device_metrics:read", "devices:read"))):
    query = db.query(DeviceMetric).options(load_only(
        DeviceMetric.id,
        DeviceMetric.device_id,
        DeviceMetric.cpu_usage,
        DeviceMetric.memory_usage,
        DeviceMetric.disk_usage,
        DeviceMetric.temperature,
        DeviceMetric.latency,
        DeviceMetric.packet_loss,
        DeviceMetric.bandwidth_usage,
        DeviceMetric.created_at,
    ))
    query = query.join(Device, DeviceMetric.device_id == Device.id).filter(Device.deleted_at.is_(None))
    accessible_site_ids = get_accessible_site_ids(current_user)
    if accessible_site_ids is not None:
        query = query.filter(Device.site_id.in_(accessible_site_ids) if accessible_site_ids else False)
    if device_id:
        query = query.filter(DeviceMetric.device_id == device_id)
    return query.order_by(DeviceMetric.created_at.desc()).offset(skip).limit(min(limit, 500)).all()


@router.post("/device-metrics", response_model=DeviceMetricRead, status_code=status.HTTP_201_CREATED)
def create_device_metric(payload: DeviceMetricCreate, db: Session = Depends(get_db), _: User = Depends(require_permission("device_metrics:create"))):
    return metric_crud.create(db, payload)


@router.get("/device-metrics/{item_id}", response_model=DeviceMetricRead)
def get_device_metric(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_any_permission("device_metrics:read", "devices:read"))):
    item = metric_crud.get(db, item_id)
    device = db.get(Device, item.device_id)
    if device is None or not can_access_site(current_user, device.site_id):
        raise HTTPException(status_code=404, detail=f"DeviceMetric {item_id} not found")
    return item


@router.patch("/device-metrics/{item_id}", response_model=DeviceMetricRead)
def update_device_metric(item_id: int, payload: DeviceMetricUpdate, db: Session = Depends(get_db), _: User = Depends(require_permission("device_metrics:update"))):
    return metric_crud.update(db, item_id, payload)


@router.delete("/device-metrics/{item_id}")
def delete_device_metric(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("device_metrics:delete"))):
    result = metric_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "device_metrics")
    return result


# ---------------------------------------------------------------- Thresholds
@router.get("/thresholds", response_model=list[ThresholdRead])
def list_thresholds(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("thresholds:read"))):
    return threshold_crud.list(db, skip, limit)


@router.post("/thresholds", response_model=ThresholdRead, status_code=status.HTTP_201_CREATED)
def create_threshold(payload: ThresholdCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("thresholds:create"))):
    item = threshold_crud.create(db, payload)
    audit(db, current_user.id, "CREATE", "thresholds")
    return item


@router.get("/thresholds/{item_id}", response_model=ThresholdRead)
def get_threshold(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("thresholds:read"))):
    return threshold_crud.get(db, item_id)


@router.patch("/thresholds/{item_id}", response_model=ThresholdRead)
def update_threshold(item_id: int, payload: ThresholdUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("thresholds:update"))):
    item = threshold_crud.update(db, item_id, payload)
    audit(db, current_user.id, "UPDATE", "thresholds")
    return item


@router.delete("/thresholds/{item_id}")
def delete_threshold(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("thresholds:delete"))):
    result = threshold_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "thresholds")
    return result


# ---------------------------------------------------------------- Alerts
@router.get("/alerts", response_model=list[AlertRead])
def list_alerts(status_filter: str | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:read"))):
    query = db.query(Alert).options(load_only(
        Alert.id,
        Alert.device_id,
        Alert.interface_id,
        Alert.severity,
        Alert.title,
        Alert.description,
        Alert.status,
        Alert.acknowledged_by,
        Alert.resolved_at,
        Alert.created_at,
        Alert.deleted_at,
    )).filter(Alert.deleted_at.is_(None))
    accessible_site_ids = get_accessible_site_ids(current_user)
    query = query.join(Device, Alert.device_id == Device.id).filter(Device.deleted_at.is_(None))
    if accessible_site_ids is not None:
        query = query.filter(Device.site_id.in_(accessible_site_ids) if accessible_site_ids else False)
    if status_filter:
        query = query.filter(Alert.status == status_filter)
    return query.order_by(Alert.created_at.desc()).offset(skip).limit(min(limit, 500)).all()


@router.post("/alerts", response_model=AlertRead, status_code=status.HTTP_201_CREATED)
def create_alert(payload: AlertCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:create"))):
    item = alert_crud.create(db, payload)
    if item.status in {"open", "acknowledged"}:
        _notify(db, item)
    db.add(Event(device_id=item.device_id, event_type="ALERT_CREATED", description=item.title))
    db.commit()
    db.refresh(item)
    # Incident automation is additive; an incident persistence problem must
    # not turn an already committed source alert into a failed alert request.
    try:
        auto_incident = create_incident_from_alert(db, item, current_user.id)
        if auto_incident is not None:
            db.commit()
    except Exception:
        db.rollback()
        incident_logger.exception("Incident automation failed for alert %s", item.id)
    audit(db, current_user.id, "CREATE", "alerts")
    return item


@router.get("/alerts/{item_id}", response_model=AlertRead)
def get_alert(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:read"))):
    item = alert_crud.get(db, item_id)
    device = db.get(Device, item.device_id) if item.device_id else None
    if device is None or not can_access_site(current_user, device.site_id):
        raise HTTPException(status_code=404, detail=f"Alert {item_id} not found")
    return item


@router.patch("/alerts/{item_id}", response_model=AlertRead)
def update_alert(item_id: int, payload: AlertUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:update"))):
    existing = alert_crud.get(db, item_id)
    device = db.get(Device, existing.device_id) if existing.device_id else None
    if device is None or not can_access_site(current_user, device.site_id):
        raise HTTPException(status_code=404, detail=f"Alert {item_id} not found")
    item = alert_crud.update(db, item_id, payload)
    if item.status == "resolved":
        try:
            process_alert_recovery(db, item.id, current_user.id)
            db.commit()
        except Exception:
            db.rollback()
            incident_logger.exception("Incident recovery processing failed for alert %s", item.id)
    audit(db, current_user.id, "UPDATE", "alerts")
    return item


@router.delete("/alerts/clear-all")
def clear_all_alerts(db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:delete"))):
    """Soft-delete all alerts at once."""
    from backend.models import Alert
    count = db.query(Alert).filter(Alert.deleted_at.is_(None)).update({Alert.deleted_at: datetime.utcnow()})
    db.commit()
    audit(db, current_user.id, "CLEAR_ALL", "alerts")
    return {"cleared": count}


@router.delete("/alerts/{item_id}")
def delete_alert(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:delete"))):
    existing = alert_crud.get(db, item_id)
    device = db.get(Device, existing.device_id) if existing.device_id else None
    if device is None or not can_access_site(current_user, device.site_id):
        raise HTTPException(status_code=404, detail=f"Alert {item_id} not found")
    result = alert_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "alerts")
    return result


@router.post("/alerts/{item_id}/acknowledge", response_model=AlertRead)
def acknowledge_alert(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:update"))):
    existing = alert_crud.get(db, item_id)
    device = db.get(Device, existing.device_id) if existing.device_id else None
    if device is None or not can_access_site(current_user, device.site_id):
        raise HTTPException(status_code=404, detail=f"Alert {item_id} not found")
    item = alert_crud.update(db, item_id, {"status": "acknowledged", "acknowledged_by": current_user.id})
    audit(db, current_user.id, "ACKNOWLEDGE", "alerts")
    return item


@router.post("/alerts/{item_id}/resolve", response_model=AlertRead)
def resolve_alert(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:update"))):
    existing = alert_crud.get(db, item_id)
    device = db.get(Device, existing.device_id) if existing.device_id else None
    if device is None or not can_access_site(current_user, device.site_id):
        raise HTTPException(status_code=404, detail=f"Alert {item_id} not found")
    item = alert_crud.update(db, item_id, {"status": "resolved", "resolved_at": datetime.utcnow()})
    try:
        process_alert_recovery(db, item.id, current_user.id)
        db.commit()
    except Exception:
        db.rollback()
        incident_logger.exception("Incident recovery processing failed for alert %s", item.id)
    audit(db, current_user.id, "RESOLVE", "alerts")
    return item


# ---------------------------------------------------------------- Events
@router.get("/events", response_model=list[EventRead])
def list_events(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("events:read"))):
    return (
        db.query(Event)
        .options(load_only(
            Event.id,
            Event.device_id,
            Event.event_type,
            Event.description,
            Event.timestamp,
            Event.deleted_at,
        ))
        .filter(Event.deleted_at.is_(None))
        .order_by(Event.timestamp.desc())
        .offset(skip)
        .limit(min(limit, 500))
        .all()
    )


@router.get("/events/{item_id}", response_model=EventRead)
def get_event(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("events:read"))):
    return event_crud.get(db, item_id)


@router.post("/events", response_model=EventRead, status_code=status.HTTP_201_CREATED)
def create_event(payload: EventCreate, db: Session = Depends(get_db), _: User = Depends(require_permission("events:create"))):
    return event_crud.create(db, payload)


@router.patch("/events/{item_id}", response_model=EventRead)
def update_event(item_id: int, payload: EventUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("events:update"))):
    item = event_crud.update(db, item_id, payload)
    audit(db, current_user.id, "UPDATE", "events")
    return item


@router.delete("/events/{item_id}")
def delete_event(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("events:delete"))):
    result = event_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "events")
    return result


# ---------------------------------------------------------------- Notifications
@router.get("/notifications", response_model=list[NotificationRead])
def list_notifications(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("notifications:read"))):
    return notification_crud.list(db, skip, limit)


@router.get("/notifications/{item_id}", response_model=NotificationRead)
def get_notification(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("notifications:read"))):
    return notification_crud.get(db, item_id)


@router.post("/notifications", response_model=NotificationRead, status_code=status.HTTP_201_CREATED)
def create_notification(payload: NotificationCreate, db: Session = Depends(get_db), _: User = Depends(require_permission("notifications:create"))):
    return notification_crud.create(db, payload)


@router.patch("/notifications/{item_id}", response_model=NotificationRead)
def update_notification(item_id: int, payload: NotificationUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("notifications:update"))):
    item = notification_crud.update(db, item_id, payload)
    audit(db, current_user.id, "UPDATE", "notifications")
    return item


@router.delete("/notifications/{item_id}")
def delete_notification(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("notifications:delete"))):
    result = notification_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "notifications")
    return result


# ---------------------------------------------------------------- Reports
@router.get("/reports", response_model=list[ReportRead])
def list_reports(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("reports:read"))):
    return report_crud.list(db, skip, limit)


@router.get("/reports/daily")
def get_daily_report(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("reports:read")),
):
    """Daily Network Monitoring Report — all 8 sections, last 24h, single DB call."""
    from datetime import datetime, timedelta  # noqa: PLC0415
    from sqlalchemy import func  # noqa: PLC0415
    from backend.models import (  # noqa: PLC0415
        Alert as _Alert, Device as _Device, DeviceMetric as _DM,
        DeviceStatusHistory as _DSH, Event as _Event, Interface as _Iface,
    )

    now   = datetime.utcnow()
    since = now - timedelta(hours=24)

    # ── 1. Device availability ─────────────────────────────────────────
    all_devices = db.query(_Device).filter(_Device.deleted_at.is_(None)).all()
    total_devices   = len(all_devices)
    online_devices  = sum(1 for d in all_devices if d.status == "online")
    offline_devices = sum(1 for d in all_devices if d.status == "offline")
    warning_devices = total_devices - online_devices - offline_devices
    avail_pct = round(online_devices / total_devices * 100, 2) if total_devices else 0.0

    downtime_events = db.query(_DSH).filter(
        _DSH.timestamp >= since, _DSH.new_status == "offline"
    ).all()
    devices_with_downtime_ids = {e.device_id for e in downtime_events}
    dev_map = {d.id: d for d in all_devices}

    downtime_detail = [
        {
            "id": d.id, "hostname": d.hostname, "ip": d.ip_address,
            "status": d.status, "downtime_sec": d.downtime_seconds,
            "last_seen": d.last_seen.isoformat() if d.last_seen else None,
        }
        for d in all_devices
        if d.id in devices_with_downtime_ids or d.status == "offline"
    ]

    availability_section = {
        "total_devices": total_devices, "online": online_devices,
        "offline": offline_devices, "warning": warning_devices,
        "availability_pct": avail_pct,
        "downtime_events_24h": len(downtime_events),
        "devices_with_downtime": downtime_detail,
    }

    # ── 2. Performance ─────────────────────────────────────────────────
    metrics_24h = db.query(_DM).filter(_DM.created_at >= since).all()

    def _avg(vals):
        c = [v for v in vals if v is not None]
        return round(sum(c) / len(c), 2) if c else None

    def _max(vals):
        c = [v for v in vals if v is not None]
        return round(max(c), 2) if c else None

    cpu_vals  = [m.cpu_usage    for m in metrics_24h]
    mem_vals  = [m.memory_usage for m in metrics_24h]
    disk_vals = [m.disk_usage   for m in metrics_24h]
    lat_vals  = [m.latency      for m in metrics_24h]
    loss_vals = [m.packet_loss  for m in metrics_24h]
    bw_vals   = [m.bandwidth_usage for m in metrics_24h]

    dev_cpu: dict = {}; dev_mem: dict = {}; dev_lat: dict = {}
    for m in metrics_24h:
        if m.cpu_usage    is not None: dev_cpu.setdefault(m.device_id, []).append(m.cpu_usage)
        if m.memory_usage is not None: dev_mem.setdefault(m.device_id, []).append(m.memory_usage)
        if m.latency      is not None: dev_lat.setdefault(m.device_id, []).append(m.latency)

    def _top(d_map, n=5):
        avgs = {did: round(sum(v)/len(v), 2) for did, v in d_map.items() if v}
        return [
            {"device_id": did, "hostname": dev_map[did].hostname if did in dev_map else f"Device-{did}",
             "ip": dev_map[did].ip_address if did in dev_map else "—",
             "avg_value": avg, "max_value": round(max(d_map[did]), 2)}
            for did, avg in sorted(avgs.items(), key=lambda x: x[1], reverse=True)[:n]
        ]

    performance_section = {
        "sample_count": len(metrics_24h),
        "cpu":      {"avg": _avg(cpu_vals),  "max": _max(cpu_vals),  "samples": len([v for v in cpu_vals  if v is not None])},
        "memory":   {"avg": _avg(mem_vals),  "max": _max(mem_vals),  "samples": len([v for v in mem_vals  if v is not None])},
        "disk":     {"avg": _avg(disk_vals), "max": _max(disk_vals), "samples": len([v for v in disk_vals if v is not None])},
        "latency":  {"avg": _avg(lat_vals),  "max": _max(lat_vals),  "samples": len([v for v in lat_vals  if v is not None])},
        "packet_loss": {"avg": _avg(loss_vals), "max": _max(loss_vals), "samples": len([v for v in loss_vals if v is not None])},
        "bandwidth":   {"avg": _avg(bw_vals),   "max": _max(bw_vals),   "samples": len([v for v in bw_vals   if v is not None])},
        "top_cpu_devices":     _top(dev_cpu),
        "top_mem_devices":     _top(dev_mem),
        "top_latency_devices": _top(dev_lat),
    }

    # ── 3. Interfaces ──────────────────────────────────────────────────
    all_ifaces = db.query(_Iface).all()
    if_total = len(all_ifaces); if_up = sum(1 for i in all_ifaces if i.status=="up"); if_down = sum(1 for i in all_ifaces if i.status=="down")
    high_traffic = sorted([i for i in all_ifaces if (i.traffic_in or 0)+(i.traffic_out or 0)>0],
                          key=lambda x: (x.traffic_in or 0)+(x.traffic_out or 0), reverse=True)[:10]
    error_ifaces = [i for i in all_ifaces if i.packet_errors > 0]

    interfaces_section = {
        "total": if_total, "up": if_up, "down": if_down,
        "high_traffic": [
            {"id": i.id, "name": i.interface_name, "device_id": i.device_id,
             "hostname": dev_map[i.device_id].hostname if i.device_id in dev_map else "—",
             "status": i.status, "traffic_in": i.traffic_in, "traffic_out": i.traffic_out,
             "speed": i.speed, "last_updated": i.last_updated.isoformat() if i.last_updated else None}
            for i in high_traffic
        ],
        "interfaces_with_errors": [
            {"id": i.id, "name": i.interface_name, "device_id": i.device_id,
             "hostname": dev_map[i.device_id].hostname if i.device_id in dev_map else "—",
             "packet_errors": i.packet_errors, "status": i.status}
            for i in error_ifaces
        ],
        "down_interfaces": [
            {"id": i.id, "name": i.interface_name, "device": dev_map[i.device_id].hostname if i.device_id in dev_map else "—", "speed": i.speed}
            for i in all_ifaces if i.status == "down"
        ],
    }

    # ── 4. Alerts ──────────────────────────────────────────────────────
    alerts_24h = db.query(_Alert).filter(_Alert.created_at >= since, _Alert.deleted_at.is_(None)).all()
    sev_counts: dict = {}
    for a in alerts_24h:
        sev_counts[a.severity] = sev_counts.get(a.severity, 0) + 1
    resolved_24h = sum(1 for a in alerts_24h if a.status == "resolved")
    open_alerts  = sum(1 for a in alerts_24h if a.status in ("open","acknowledged"))
    dev_alert_count: dict = {}
    for a in alerts_24h:
        if a.device_id: dev_alert_count[a.device_id] = dev_alert_count.get(a.device_id, 0) + 1
    top_alert_raw = sorted(dev_alert_count.items(), key=lambda x: x[1], reverse=True)[:5]

    events_24h = db.query(_Event).filter(_Event.timestamp >= since, _Event.deleted_at.is_(None)).all()
    evt_types: dict = {}
    for e in events_24h: evt_types[e.event_type] = evt_types.get(e.event_type, 0) + 1

    alerts_section = {
        "total_alerts_24h": len(alerts_24h),
        "by_severity": sev_counts,
        "resolved": resolved_24h, "open": open_alerts,
        "critical": sev_counts.get("critical",0), "high": sev_counts.get("high",0),
        "warning":  sev_counts.get("warning",0),  "info": sev_counts.get("info",0),
        "top_alert_devices": [
            {"device_id": did, "hostname": dev_map[did].hostname if did in dev_map else f"Device-{did}",
             "ip": dev_map[did].ip_address if did in dev_map else "—", "count": cnt}
            for did, cnt in top_alert_raw
        ],
        "recent_alerts": [
            {"id": a.id, "severity": a.severity, "title": a.title,
             "description": a.description, "status": a.status, "device_id": a.device_id,
             "hostname": dev_map[a.device_id].hostname if a.device_id and a.device_id in dev_map else "—",
             "created_at": a.created_at.isoformat() if a.created_at else None}
            for a in sorted(alerts_24h, key=lambda x: x.created_at or datetime.min, reverse=True)[:20]
        ],
        "total_events_24h": len(events_24h), "event_types": evt_types,
    }

    # ── 5. Incidents ───────────────────────────────────────────────────
    sc_24h = db.query(_DSH).filter(_DSH.timestamp >= since).order_by(_DSH.timestamp.desc()).all()
    incidents_section = {
        "total_status_changes": len(sc_24h),
        "went_offline": sum(1 for s in sc_24h if s.new_status=="offline"),
        "came_online":  sum(1 for s in sc_24h if s.new_status=="online"),
        "changes": [
            {"device_id": s.device_id,
             "hostname": dev_map[s.device_id].hostname if s.device_id in dev_map else "—",
             "ip": dev_map[s.device_id].ip_address if s.device_id in dev_map else "—",
             "old_status": s.old_status, "new_status": s.new_status,
             "reason": s.change_reason,
             "timestamp": s.timestamp.isoformat() if s.timestamp else None}
            for s in sc_24h[:30]
        ],
    }

    # ── 6. Top performers ──────────────────────────────────────────────
    top_performers = {
        "top_cpu":     _top(dev_cpu),
        "top_memory":  _top(dev_mem),
        "top_latency": _top(dev_lat),
        "max_downtime": sorted(
            [{"device_id": d.id, "hostname": d.hostname, "ip": d.ip_address,
              "status": d.status, "downtime_sec": d.downtime_seconds}
             for d in all_devices if d.downtime_seconds > 0],
            key=lambda x: x["downtime_sec"], reverse=True)[:5],
        "max_alerts": [
            {"device_id": did, "hostname": dev_map[did].hostname if did in dev_map else f"Device-{did}",
             "ip": dev_map[did].ip_address if did in dev_map else "—", "alerts": cnt}
            for did, cnt in top_alert_raw
        ],
    }

    # ── 7. Daily summary ───────────────────────────────────────────────
    issues = []
    if offline_devices:  issues.append(f"{offline_devices} device(s) currently offline")
    if sev_counts.get("critical",0): issues.append(f"{sev_counts['critical']} critical alert(s) generated")
    if if_down:          issues.append(f"{if_down} interface(s) currently down")
    if error_ifaces:     issues.append(f"{len(error_ifaces)} interface(s) with packet errors")
    if open_alerts:      issues.append(f"{open_alerts} alert(s) remain unresolved")

    health_score = round(
        avail_pct * 0.4
        + max(0, 100 - sev_counts.get("critical",0)*20) * 0.3
        + (round(if_up/if_total*100,1) if if_total else 100) * 0.3, 1)
    overall_health = "GOOD" if health_score >= 80 else "WARNING" if health_score >= 60 else "CRITICAL"

    daily_summary = {
        "overall_health": overall_health, "health_score": health_score,
        "availability_pct": avail_pct,
        "issues": issues or ["No major issues observed"],
        "devices_needing_attention": [
            {"device_id": d.id, "hostname": d.hostname, "ip": d.ip_address, "status": d.status, "reason": "Currently offline"}
            for d in all_devices if d.status == "offline"
        ] + [
            {"device_id": r["device_id"], "hostname": r["hostname"], "ip": r["ip"], "status": "online",
             "reason": f"Generated {dev_alert_count.get(r['device_id'],0)} alert(s)"}
            for r in top_performers["max_alerts"][:3]
        ],
    }

    # ── 8. Recommendations ─────────────────────────────────────────────
    recs = []
    if offline_devices:
        names = ", ".join(d["hostname"] for d in downtime_detail[:3])
        recs.append({"priority": "CRITICAL", "message": f"Investigate offline device(s): {names}. Check power, connectivity and SNMP credentials."})
    if sev_counts.get("critical",0):
        recs.append({"priority": "CRITICAL", "message": f"{sev_counts['critical']} critical alert(s) unresolved. Immediate action required."})
    if open_alerts:
        recs.append({"priority": "HIGH", "message": f"{open_alerts} open alert(s) need review and resolution."})
    if error_ifaces:
        names = ", ".join(i.interface_name for i in error_ifaces[:3])
        recs.append({"priority": "HIGH", "message": f"Interfaces with errors: {names}. Review cable/SFP health and switch logs."})
    if if_down:
        recs.append({"priority": "HIGH", "message": f"{if_down} interface(s) are down. Verify if intentional."})
    avg_cpu = _avg(cpu_vals)
    if avg_cpu and avg_cpu > 70:
        recs.append({"priority": "WARNING", "message": f"Average CPU is {avg_cpu}% — consider load balancing or hardware upgrade."})
    if not recs:
        recs.append({"priority": "INFO", "message": "Network operating within normal parameters. Continue routine monitoring."})

    return {
        "report_date": now.strftime("%Y-%m-%d"),
        "period": f"{since.strftime('%Y-%m-%d %H:%M')} UTC → {now.strftime('%Y-%m-%d %H:%M')} UTC",
        "generated_at": now.isoformat(),
        "availability": availability_section,
        "performance":  performance_section,
        "interfaces":   interfaces_section,
        "alerts":       alerts_section,
        "incidents":    incidents_section,
        "top_performers": top_performers,
        "daily_summary":  daily_summary,
        "recommendations": recs,
    }


@router.get("/reports/{item_id}", response_model=ReportRead)
def get_report(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("reports:read"))):
    return report_crud.get(db, item_id)


@router.post("/reports", response_model=ReportRead, status_code=status.HTTP_201_CREATED)
def create_report(payload: ReportCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("reports:create"))):
    data = payload.model_dump()
    data["generated_by"] = data["generated_by"] or current_user.id
    item = report_crud.create(db, data)
    audit(db, current_user.id, "CREATE", "reports")
    return item


@router.patch("/reports/{item_id}", response_model=ReportRead)
def update_report(item_id: int, payload: ReportUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("reports:update"))):
    item = report_crud.update(db, item_id, payload)
    audit(db, current_user.id, "UPDATE", "reports")
    return item


@router.delete("/reports/{item_id}")
def delete_report(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("reports:delete"))):
    result = report_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "reports")
    return result


# ---------------------------------------------------------------- Audit logs (read-only)
@router.post("/audit-logs/page-view", response_model=AuditLogRead)
def record_page_view(page: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    normalized_page = page[:160]
    cache_key = (current_user.id, normalized_page)
    now = datetime.utcnow()
    with _page_view_cache_lock:
        last_seen = _page_view_cache.get(cache_key)
        if last_seen and (now - last_seen).total_seconds() < _PAGE_VIEW_TTL_SECONDS:
            return AuditLog(
                id=0,
                user_id=current_user.id,
                action="VIEW_PAGE",
                resource_name=normalized_page,
                timestamp=last_seen,
            )
        _page_view_cache[cache_key] = now

    entry = AuditLog(user_id=current_user.id, action="VIEW_PAGE", resource_name=normalized_page)
    db.add(entry)
    db.flush()
    db.commit()
    return entry


@router.get("/audit-logs/users")
def list_audit_log_users(db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit_logs:read"))):
    if not can_view_security_audit(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Security-wide audit access is not permitted")
    query = db.query(User.id, User.name, User.email).join(Role, User.role_id == Role.id)
    if not is_super_admin(current_user):
        query = query.filter(Role.authority_level < get_authority_level(current_user))
    return [{"id": user_id, "name": name, "email": email} for user_id, name, email in query.order_by(User.name.asc()).all()]


@router.get("/audit-logs")
def list_audit_logs(
    user_id: int | None = None,
    action: str | None = None,
    outcome: str | None = None,
    resource_type: str | None = None,
    resource_id: int | None = None,
    source_ip: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    include_total: bool = Query(False),
    skip: int | None = Query(None, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit_logs:read")),
):
    if not can_view_security_audit(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Security-wide audit access is not permitted")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start_date must be before or equal to end_date")
    if is_super_admin(current_user):
        query = db.query(AuditLog, User.name.label("user_name")).outerjoin(User, AuditLog.user_id == User.id)
    else:
        query = db.query(AuditLog, User.name.label("user_name")).join(User, AuditLog.user_id == User.id).join(Role, User.role_id == Role.id)
        query = query.filter(Role.authority_level < get_authority_level(current_user))
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if action is not None:
        query = query.filter(AuditLog.action == action)
    if outcome is not None:
        query = query.filter(AuditLog.outcome == outcome)
    if resource_type is not None:
        query = query.filter(AuditLog.resource_type == resource_type)
    if resource_id is not None:
        query = query.filter(AuditLog.resource_id == resource_id)
    if source_ip is not None:
        query = query.filter(AuditLog.source_ip == source_ip)
    if start_date is not None:
        query = query.filter(AuditLog.timestamp >= start_date)
    if end_date is not None:
        query = query.filter(AuditLog.timestamp <= end_date)
    effective_offset = skip if skip is not None else offset
    total = query.with_entities(func.count(AuditLog.id)).scalar() if include_total else None
    rows = query.order_by(AuditLog.timestamp.desc(), AuditLog.id.desc()).offset(effective_offset).limit(limit).all()
    items = [{**log.__dict__, "user_name": name} for log, name in rows]
    return {"items": items, "total": total} if include_total else items


@router.get("/audit-logs/summary")
def audit_log_summary(
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("audit_logs:read")),
):
    if not can_view_security_audit(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Security-wide audit access is not permitted")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="start_date must be before or equal to end_date")
    if is_super_admin(current_user):
        query = db.query(AuditLog).outerjoin(User, AuditLog.user_id == User.id)
    else:
        query = db.query(AuditLog).join(User, AuditLog.user_id == User.id).join(Role, User.role_id == Role.id)
        query = query.filter(Role.authority_level < get_authority_level(current_user))
    if start_date is not None:
        query = query.filter(AuditLog.timestamp >= start_date)
    if end_date is not None:
        query = query.filter(AuditLog.timestamp <= end_date)
    counts = query.with_entities(
        func.count(AuditLog.id).label("total_activities"),
        func.count(case((AuditLog.outcome == "success", 1))).label("successful_actions"),
        func.count(case((AuditLog.outcome == "failure", 1))).label("failed_actions"),
        func.count(case((AuditLog.action == "LOGIN_SUCCESS", 1))).label("login_success"),
        func.count(case((AuditLog.action == "LOGIN_FAILED", 1))).label("login_failed"),
        func.count(case((AuditLog.action == "ACCOUNT_LOCKED", 1))).label("account_locked"),
        func.count(case((AuditLog.action == "USER_STATUS_CHANGED", 1))).label("user_status_changes"),
    ).one()
    return {
        "total_activities": counts.total_activities,
        "successful_actions": counts.successful_actions,
        "failed_actions": counts.failed_actions,
        "login_success": counts.login_success,
        "login_failed": counts.login_failed,
        "account_locked": counts.account_locked,
        "user_status_changes": counts.user_status_changes,
    }


@router.get("/audit-logs/{item_id}", response_model=AuditLogRead)
def get_audit_log(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("audit_logs:read"))):
    if not can_view_security_audit(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Security-wide audit access is not permitted")
    row = db.query(AuditLog, User).outerjoin(User, AuditLog.user_id == User.id).filter(AuditLog.id == item_id).first()
    if row is None or not can_view_audit_actor(current_user, row[1]):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Audit entry is outside your authority scope")
    return row[0]


# ---------------------------------------------------------------- Dashboard
@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(db: Session = Depends(get_db), _: User = Depends(require_permission("dashboard:read"))):
    from backend.cache.redis_cache import set_json

    now = datetime.utcnow()
    # Device availability is operational state, not a cacheable inventory
    # value. Always read it from the current DB transaction so a stale Redis
    # snapshot cannot make the UI report zero online devices.

    since = now - timedelta(hours=24)
    eligible_devices = db.query(Device).filter(Device.deleted_at.is_(None)).all()
    health_counts = _derived_dashboard_health_counts(db, eligible_devices)
    summary_counts = db.query(
        db.query(func.count(Alert.id)).filter(
            Alert.status.in_(["open", "acknowledged"]), Alert.deleted_at.is_(None)
        ).scalar_subquery().label("active_alerts"),
        db.query(func.count(Alert.id)).filter(
            Alert.severity == "critical", Alert.status != "resolved"
        ).scalar_subquery().label("critical_alerts"),
        db.query(func.count(Event.id)).filter(Event.timestamp >= since).scalar_subquery().label("recent_events"),
    ).one()
    summary = DashboardSummary(
        total_devices=len(eligible_devices),
        online_devices=health_counts["online"],
        offline_devices=health_counts["offline"],
        health_counts=health_counts,
        active_alerts=int(summary_counts.active_alerts or 0),
        critical_alerts=int(summary_counts.critical_alerts or 0),
        recent_events=int(summary_counts.recent_events or 0),
    )
    with _dashboard_summary_lock:
        _dashboard_summary_cache["cached_at"] = now
        _dashboard_summary_cache["value"] = summary
    set_json("nms:dashboard:summary:v1", summary.model_dump())
    return summary


# ---------------------------------------------------------------- Discovery / Monitoring
@router.post("/monitoring/run", response_model=list[DeviceRead])
def run_monitoring(
    payload: MonitoringRunRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("monitoring:execute")),
):
    request = payload or MonitoringRunRequest()
    if request.timeout_ms < 500 or request.timeout_ms > 10000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="timeout_ms must be between 500 and 10000")
    devices = run_monitoring_check(db, ip_addresses=request.ip_addresses, timeout_ms=request.timeout_ms)
    audit(db, current_user.id, "RUN_MONITORING", f"{len(devices)} devices")
    db.commit()
    return devices


@router.post("/discovery/run", response_model=list[DeviceRead], status_code=status.HTTP_201_CREATED)
def run_discovery(payload: DiscoveryRequest, db: Session = Depends(get_db), current_user: User = Depends(require_permission("discovery:execute"))):
    try:
        if payload.site_id and not db.get(Site, payload.site_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"site_id {payload.site_id} does not exist. Create a site first or send site_id as null.",
            )
        if payload.max_hosts < 1 or payload.max_hosts > 255:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="IP range cannot contain more than 255 addresses")
        if payload.timeout_ms < 100 or payload.timeout_ms > 5000:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="timeout_ms must be between 100 and 5000")

        # ---- Expand & dedupe ------------------------------------------------
        # Use the tolerant NetworkRange parser so users can type CIDR,
        # "start-end", or a comma-separated list. Existing devices in the
        # DB are skipped so we only probe *new* IPs.
        from network_range import plan_scan  # icmp_discovery/ on sys.path
        from vendor_map import lookup_vendor  # icmp_discovery/ on sys.path

        try:
            plan = plan_scan(
                spec=payload.network_range,
                known_ips=[d.ip_address for d in db.query(Device.ip_address).all()],
                max_hosts=payload.max_hosts,
            )
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

        scan_results = discover_network(
            network_range=payload.network_range,
            ports=payload.ports,
            timeout_ms=payload.timeout_ms,
            snmp_community=payload.snmp_community,
            scan_icmp=payload.scan_icmp,
            scan_tcp_ports=payload.scan_ports,
            scan_snmp=payload.scan_snmp,
            max_hosts=payload.max_hosts,
            ip_list=plan.new_ips or None,  # only scan NEW IPs
        )

        discovered = []
        for result in scan_results:
            vendor = lookup_vendor(result.mac_address)
            # Smart name: SNMP name > hostname > vendor (from MAC) > generic
            if result.snmp_name:
                hostname = result.snmp_name
            elif result.hostname:
                hostname = result.hostname
            elif vendor != "Unknown":
                hostname = vendor
            else:
                hostname = f"device-{result.ip_address.replace('.', '-')}"
            description = result.snmp_description or f"Open ports: {', '.join(str(port) for port in result.open_ports) or 'none'}"

            device = db.query(Device).filter(Device.ip_address == result.ip_address).first()
            is_new = device is None
            if is_new:
                device = Device(ip_address=result.ip_address)
                db.add(device)

            device.hostname = hostname
            if result.mac_address:
                device.mac_address = result.mac_address
            # Vendor field takes precedence; fall back to SNMP description
            if vendor != "Unknown":
                existing_vendor = db.query(Vendor).filter(Vendor.vendor_name == vendor).first()
                if existing_vendor is None:
                    existing_vendor = Vendor(vendor_name=vendor)
                    db.add(existing_vendor)
                    db.flush()
                device.vendor_id = existing_vendor.id
            if result.snmp_description:
                device.model = result.snmp_description[:120]
            device.status = "online"
            device.monitoring_status = True
            device.last_seen = datetime.utcnow()
            if payload.site_id is not None:
                device.site_id = payload.site_id
            device.deleted_at = None

            db.flush()
            event_type = "DISCOVERY_FOUND" if is_new else "DISCOVERY_UPDATED"
            db.add(Event(device_id=device.id, event_type=event_type, description=description))
            if is_new:
                create_device_added_alert(
                    db,
                    device.id,
                    device.hostname,
                    device.ip_address,
                    "ICMP",
                    device.status,
                    device.mac_address,
                )
            discovered.append(device)
        db.commit()
        for device in discovered:
            db.refresh(device)
        audit(
            db,
            current_user.id,
            "RUN_DISCOVERY",
            f"{payload.network_range} (new={len(plan.new_ips)}, known={len(plan.known_ips)}, found={len(discovered)})",
        )
        return discovered
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Discovery failed: {str(e)}",
        )
