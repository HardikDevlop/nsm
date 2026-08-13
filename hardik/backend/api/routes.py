from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from backend.auth.security import create_access_token, hash_password, verify_password
from backend.database.session import get_db
from backend.dependencies import get_current_user, require_permission
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
    Role,
    Site,
    Threshold,
    User,
    Vendor,
)
from backend.repositories.crud import CRUDRouterMixin
from backend.schemas.nms import (
    AlertCreate,
    AlertRead,
    AlertUpdate,
    AssignRoleRequest,
    AuditLogRead,
    DashboardSummary,
    DeviceCreate,
    DeviceCredentialCreate,
    DeviceCredentialRead,
    DeviceCredentialUpdate,
    DeviceMetricCreate,
    DeviceMetricRead,
    DeviceMetricUpdate,
    DeviceRead,
    DeviceStatusHistoryRead,
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
    UserRead,
    UserUpdate,
    VendorCreate,
    VendorRead,
    VendorUpdate,
)
from backend.services.discovery import discover_network
from backend.services.monitoring import run_monitoring_check
from backend.utils.crypto import encrypt_secret


router = APIRouter(prefix="/api/v1")


def audit(db: Session, user_id: int | None, action: str, resource_name: str) -> None:
    db.add(AuditLog(user_id=user_id, action=action, resource_name=resource_name))
    db.commit()


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
        permissions=permissions,
        status=user.status,
        created_at=user.created_at,
    )


@router.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    db.execute(select(func.now()))
    return {"status": "ok", "database": "connected"}


@router.post("/auth/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> Token:
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return Token(access_token=create_access_token(user.email))


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


# ---------------------------------------------------------------- Roles
@router.get("/roles", response_model=list[RoleRead])
def list_roles(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("roles:read"))):
    return role_crud.list(db, skip, limit)


@router.post("/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
def create_role(payload: RoleCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("roles:create"))):
    item = role_crud.create(db, payload)
    audit(db, current_user.id, "CREATE", "roles")
    return item


@router.get("/roles/{item_id}", response_model=RoleRead)
def get_role(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("roles:read"))):
    return role_crud.get(db, item_id)


@router.patch("/roles/{item_id}", response_model=RoleRead)
def update_role(item_id: int, payload: RoleUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("roles:update"))):
    item = role_crud.update(db, item_id, payload)
    audit(db, current_user.id, "UPDATE", "roles")
    return item


@router.delete("/roles/{item_id}")
def delete_role(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("roles:delete"))):
    result = role_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "roles")
    return result


@router.get("/roles/{item_id}/permissions", response_model=RoleWithPermissions)
def get_role_permissions(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("roles:read"))):
    return role_crud.get(db, item_id)


@router.put("/roles/{item_id}/permissions", response_model=RoleWithPermissions)
def assign_role_permissions(item_id: int, payload: PermissionIds, db: Session = Depends(get_db), current_user: User = Depends(require_permission("roles:update"))):
    role = role_crud.get(db, item_id)
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
    item = permission_crud.create(db, payload)
    audit(db, current_user.id, "CREATE", "permissions")
    return item


@router.get("/permissions/{item_id}", response_model=PermissionRead)
def get_permission(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("permissions:read"))):
    return permission_crud.get(db, item_id)


@router.patch("/permissions/{item_id}", response_model=PermissionRead)
def update_permission(item_id: int, payload: PermissionUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("permissions:update"))):
    item = permission_crud.update(db, item_id, payload)
    audit(db, current_user.id, "UPDATE", "permissions")
    return item


@router.delete("/permissions/{item_id}")
def delete_permission(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("permissions:delete"))):
    result = permission_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "permissions")
    return result


# ---------------------------------------------------------------- Users
@router.get("/users", response_model=list[UserRead])
def list_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("users:read"))):
    users = (
        db.query(User)
        .options(joinedload(User.role).joinedload(Role.permissions))
        .order_by(User.id)
        .offset(skip)
        .limit(min(limit, 500))
        .all()
    )
    return [_user_read(user) for user in users]


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("users:create"))):
    data = payload.model_dump()
    data["password_hash"] = hash_password(data.pop("password"))
    if data.get("role_id") is not None:
        role_crud.get(db, data["role_id"])
    item = user_crud.create(db, data)
    audit(db, current_user.id, "CREATE", "users")
    return _user_read(item)


@router.get("/users/{item_id}", response_model=UserRead)
def get_user(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("users:read"))):
    return _user_read(user_crud.get(db, item_id))


@router.post("/users/{item_id}/role", response_model=UserRead)
def assign_user_role(item_id: int, payload: AssignRoleRequest, db: Session = Depends(get_db), current_user: User = Depends(require_permission("users:update"))):
    role_crud.get(db, payload.role_id)
    item = user_crud.update(db, item_id, {"role_id": payload.role_id})
    audit(db, current_user.id, "ASSIGN_ROLE", f"user:{item.id}")
    return _user_read(item)


@router.patch("/users/{item_id}", response_model=UserRead)
def update_user(item_id: int, payload: UserUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("users:update"))):
    data = payload.model_dump(exclude_unset=True)
    if "password" in data:
        data["password_hash"] = hash_password(data.pop("password"))
    item = user_crud.update(db, item_id, data)
    audit(db, current_user.id, "UPDATE", "users")
    return _user_read(item)


@router.delete("/users/{item_id}")
def delete_user(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("users:delete"))):
    if item_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot delete your own account")
    result = user_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "users")
    return result


# ---------------------------------------------------------------- Organizations
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
def list_sites(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("sites:read"))):
    return site_crud.list(db, skip, limit)


@router.post("/sites", response_model=SiteRead, status_code=status.HTTP_201_CREATED)
def create_site(payload: SiteCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("sites:create"))):
    item = site_crud.create(db, payload)
    audit(db, current_user.id, "CREATE", "sites")
    return item


@router.get("/sites/{item_id}", response_model=SiteRead)
def get_site(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("sites:read"))):
    return site_crud.get(db, item_id)


@router.patch("/sites/{item_id}", response_model=SiteRead)
def update_site(item_id: int, payload: SiteUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("sites:update"))):
    item = site_crud.update(db, item_id, payload)
    audit(db, current_user.id, "UPDATE", "sites")
    return item


@router.delete("/sites/{item_id}")
def delete_site(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("sites:delete"))):
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
    result = device_type_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "device_types")
    return result


# ---------------------------------------------------------------- Devices
@router.get("/devices", response_model=list[DeviceRead])
def list_devices(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("devices:read"))):
    return device_crud.list(db, skip, limit)


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
def get_device(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("devices:read"))):
    return device_crud.get(db, item_id)


@router.patch("/devices/{item_id}", response_model=DeviceRead)
def update_device(item_id: int, payload: DeviceUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("devices:update"))):
    item = device_crud.update(db, item_id, payload)
    audit(db, current_user.id, "UPDATE", "devices")
    return item


@router.delete("/devices/{item_id}")
def delete_device(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("devices:delete"))):
    result = device_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "devices")
    return result


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
    audit(db, current_user.id, "DELETE", "devices")
    return {"deleted": count, "message": f"All {count} devices deleted successfully"}


@router.post("/devices/{item_id}/monitoring/{enabled}", response_model=DeviceRead)
def set_monitoring(item_id: int, enabled: bool, db: Session = Depends(get_db), current_user: User = Depends(require_permission("devices:update"))):
    item = device_crud.update(db, item_id, {"monitoring_status": enabled})
    audit(db, current_user.id, "UPDATE", "device_monitoring")
    return item


@router.get("/devices/{item_id}/status-history", response_model=list[DeviceStatusHistoryRead])
def get_device_status_history(
    item_id: int,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("devices:read")),
):
    device_crud.get(db, item_id)
    return (
        db.query(DeviceStatusHistory)
        .filter(DeviceStatusHistory.device_id == item_id)
        .order_by(DeviceStatusHistory.timestamp.desc())
        .offset(skip)
        .limit(min(limit, 500))
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
def list_interfaces(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("interfaces:read"))):
    return interface_crud.list(db, skip, limit)


@router.get("/interfaces/{item_id}", response_model=InterfaceRead)
def get_interface(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("interfaces:read"))):
    return interface_crud.get(db, item_id)


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
def list_device_metrics(device_id: int | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("device_metrics:read"))):
    query = db.query(DeviceMetric)
    if device_id:
        query = query.filter(DeviceMetric.device_id == device_id)
    return query.order_by(DeviceMetric.created_at.desc()).offset(skip).limit(min(limit, 500)).all()


@router.post("/device-metrics", response_model=DeviceMetricRead, status_code=status.HTTP_201_CREATED)
def create_device_metric(payload: DeviceMetricCreate, db: Session = Depends(get_db), _: User = Depends(require_permission("device_metrics:create"))):
    return metric_crud.create(db, payload)


@router.get("/device-metrics/{item_id}", response_model=DeviceMetricRead)
def get_device_metric(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("device_metrics:read"))):
    return metric_crud.get(db, item_id)


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
def list_alerts(status_filter: str | None = None, skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("alerts:read"))):
    query = db.query(Alert).filter(Alert.deleted_at.is_(None))
    if status_filter:
        query = query.filter(Alert.status == status_filter)
    return query.order_by(Alert.created_at.desc()).offset(skip).limit(min(limit, 500)).all()


@router.post("/alerts", response_model=AlertRead, status_code=status.HTTP_201_CREATED)
def create_alert(payload: AlertCreate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:create"))):
    item = alert_crud.create(db, payload)
    db.add(Event(device_id=item.device_id, event_type="ALERT_CREATED", description=item.title))
    db.commit()
    db.refresh(item)
    audit(db, current_user.id, "CREATE", "alerts")
    return item


@router.get("/alerts/{item_id}", response_model=AlertRead)
def get_alert(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("alerts:read"))):
    return alert_crud.get(db, item_id)


@router.patch("/alerts/{item_id}", response_model=AlertRead)
def update_alert(item_id: int, payload: AlertUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:update"))):
    item = alert_crud.update(db, item_id, payload)
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
    result = alert_crud.delete(db, item_id)
    audit(db, current_user.id, "DELETE", "alerts")
    return result


@router.post("/alerts/{item_id}/acknowledge", response_model=AlertRead)
def acknowledge_alert(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:update"))):
    item = alert_crud.update(db, item_id, {"status": "acknowledged", "acknowledged_by": current_user.id})
    audit(db, current_user.id, "ACKNOWLEDGE", "alerts")
    return item


@router.post("/alerts/{item_id}/resolve", response_model=AlertRead)
def resolve_alert(item_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("alerts:update"))):
    item = alert_crud.update(db, item_id, {"status": "resolved", "resolved_at": datetime.utcnow()})
    audit(db, current_user.id, "RESOLVE", "alerts")
    return item


# ---------------------------------------------------------------- Events
@router.get("/events", response_model=list[EventRead])
def list_events(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("events:read"))):
    return (
        db.query(Event)
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
@router.get("/audit-logs", response_model=list[AuditLogRead])
def list_audit_logs(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), _: User = Depends(require_permission("audit_logs:read"))):
    return db.query(AuditLog).order_by(AuditLog.timestamp.desc()).offset(skip).limit(min(limit, 500)).all()


@router.get("/audit-logs/{item_id}", response_model=AuditLogRead)
def get_audit_log(item_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("audit_logs:read"))):
    return audit_crud.get(db, item_id)


# ---------------------------------------------------------------- Dashboard
@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(db: Session = Depends(get_db), _: User = Depends(require_permission("dashboard:read"))):
    total_devices = db.query(Device).filter(Device.deleted_at.is_(None)).count()
    online_devices = db.query(Device).filter(Device.deleted_at.is_(None), Device.status == "online").count()
    offline_devices = db.query(Device).filter(Device.deleted_at.is_(None), Device.status == "offline").count()
    active_alerts = db.query(Alert).filter(Alert.status.in_(["open", "acknowledged"])).count()
    critical_alerts = db.query(Alert).filter(Alert.severity == "critical", Alert.status != "resolved").count()
    since = datetime.utcnow() - timedelta(hours=24)
    recent_events = db.query(Event).filter(Event.timestamp >= since).count()
    return DashboardSummary(
        total_devices=total_devices,
        online_devices=online_devices,
        offline_devices=offline_devices,
        active_alerts=active_alerts,
        critical_alerts=critical_alerts,
        recent_events=recent_events,
    )


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
        if payload.max_hosts < 1 or payload.max_hosts > 1024:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="max_hosts must be between 1 and 1024")
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
