"""Seed default RBAC data: permissions for every module, four base roles,
and the default admin account (admin@gmail.com / admin123)."""

from sqlalchemy.orm import Session

from backend.auth.security import hash_password
from backend.models import Permission, Role, User

CRUD_ACTIONS = ("create", "read", "update", "delete")

CRUD_MODULES = [
    "roles",
    "permissions",
    "users",
    "organizations",
    "sites",
    "vendors",
    "device_types",
    "devices",
    "device_credentials",
    "interfaces",
    "monitoring_jobs",
    "device_metrics",
    "thresholds",
    "alerts",
    "events",
    "notifications",
    "reports",
    "linux_servers",
]

EXTRA_PERMISSIONS = [
    ("audit_logs", "read"),
    ("dashboard", "read"),
    ("discovery", "execute"),
    ("monitoring", "execute"),
    ("topology", "read"),
    # Frontend page-level permissions
    ("forensics", "read"),
    ("compliance", "read"),
    ("packet_analysis", "read"),
    ("firewall", "read"),
    ("nginx", "read"),
    ("server_monitoring", "read"),
    ("isp", "read"),
    ("incidents", "read"),
    ("attack_path", "read"),
    ("device_monitoring", "read"),
    ("flows", "read"),
    ("apm", "read"),
    ("apm", "ingest"),
    ("apm", "manage"),
    ("apm", "raw:read"),
    ("cmdb", "read"),
    ("cmdb", "manage"),
    ("rca", "read"),
    ("rca", "execute"),
    ("rca", "manage"),
    ("incidents", "create"),
    ("incidents", "update"),
    ("incidents", "manage"),
    ("problems", "read"),
    ("problems", "create"),
    ("problems", "update"),
    ("problems", "manage"),
    ("changes", "read"),
    ("changes", "create"),
    ("changes", "update"),
    ("changes", "approve"),
    ("changes", "manage"),
    ("knowledge", "read"),
    ("knowledge", "create"),
    ("knowledge", "update"),
    ("knowledge", "manage"),
    ("config_backups", "read"),
    ("config_backups", "execute"),
    ("config_backups", "manage"),
    ("config_compliance", "read"),
    ("config_compliance", "execute"),
    ("config_compliance", "manage"),
    ("availability", "read"),
    ("virtualization", "read"),
    ("virtualization", "manage"),
    ("qos", "read"),
    ("qos", "ingest"),
    ("bgp", "read"),
    ("bgp", "ingest"),
    ("syslog", "read"),
    ("syslog", "manage"),
]

OPERATOR_CODES = {
    f"{module}:read" for module in CRUD_MODULES
} | {
    "devices:create", "devices:update",
    "device_credentials:create", "device_credentials:update",
    "interfaces:create", "interfaces:update",
    "monitoring_jobs:create", "monitoring_jobs:update",
    "device_metrics:create", "device_metrics:update",
    "alerts:create", "alerts:update",
    "events:create",
    "notifications:create", "notifications:update",
    "reports:create",
    "audit_logs:read", "dashboard:read", "topology:read",
    "discovery:execute", "monitoring:execute",
    # Frontend page-level permissions
    "forensics:read", "compliance:read", "packet_analysis:read",
    "firewall:read", "nginx:read", "server_monitoring:read",
    "isp:read", "incidents:read", "attack_path:read",
    "device_monitoring:read",
    "flows:read",
    "apm:read", "apm:ingest", "apm:manage", "apm:raw:read",
    "cmdb:read", "cmdb:manage",
    "rca:read", "rca:execute", "rca:manage",
    "incidents:read", "incidents:create", "incidents:update", "incidents:manage",
    "problems:read", "problems:create", "problems:update", "problems:manage",
    "changes:read", "changes:create", "changes:update", "changes:approve", "changes:manage",
    "knowledge:read", "knowledge:create", "knowledge:update", "knowledge:manage",
    "config_backups:read", "config_backups:execute", "config_backups:manage", "config_compliance:read", "config_compliance:execute", "config_compliance:manage",
}

VIEWER_CODES = {f"{module}:read" for module in CRUD_MODULES} | {
    "audit_logs:read",
    "dashboard:read",
    "topology:read",
    # Frontend page-level permissions
    "forensics:read", "compliance:read", "packet_analysis:read",
    "firewall:read", "nginx:read", "server_monitoring:read",
    "isp:read", "incidents:read", "attack_path:read",
    "device_monitoring:read",
    "flows:read",
    "apm:read",
    "cmdb:read",
    "rca:read",
    "incidents:read",
    "problems:read",
    "changes:read",
    "knowledge:read",
    "config_backups:read",
}


def _module_label(module: str) -> str:
    return module.replace("_", " ").title()


def seed_rbac(db: Session) -> None:
    # 1. Permissions
    wanted: list[tuple[str, str]] = [
        (module, action) for module in CRUD_MODULES for action in CRUD_ACTIONS
    ] + EXTRA_PERMISSIONS
    existing = {perm.code: perm for perm in db.query(Permission).all()}
    for module, action in wanted:
        code = f"{module}:{action}"
        if code not in existing:
            permission = Permission(
                code=code,
                name=f"{_module_label(module)} {action.title()}",
                module=module,
                action=action,
                description=f"Can {action} {_module_label(module).lower()}",
            )
            db.add(permission)
            existing[code] = permission
    db.flush()

    # 2. Roles
    all_permissions = list(existing.values())
    role_map = {role.role_name: role for role in db.query(Role).all()}
    # Only a completely fresh database gets the bundled Operator/Viewer
    # roles. After that, role management is authoritative: deleting a role
    # must not cause startup seeding to recreate it.
    fresh_roles = not role_map

    def ensure_role(name: str, codes: set[str] | None, authority_level: int, is_system_role: bool, is_assignable: bool) -> Role:
        role = role_map.get(name)
        if role is None:
            role = Role(role_name=name, authority_level=authority_level, is_system_role=is_system_role, is_assignable=is_assignable)
            db.add(role)
            role_map[name] = role
            if codes is None:
                role.permissions = all_permissions
            else:
                role.permissions = [perm for code, perm in existing.items() if code in codes]
        else:
            role.authority_level = authority_level
            role.is_system_role = is_system_role
            role.is_assignable = is_assignable
        return role

    super_admin_role = ensure_role("Super Admin", None, 100, True, False)
    super_admin_role.permissions = all_permissions
    admin_role = ensure_role("Admin", None, 80, False, True)
    # Keep Admin aligned with the full permission catalog on every seed run.
    # Without this, older databases can miss newer module permissions even
    # though the Admin role already exists.
    admin_role.permissions = all_permissions
    if fresh_roles:
        ensure_role("Operator", OPERATOR_CODES, 50, False, True)
        ensure_role("Viewer", VIEWER_CODES, 10, False, True)
    db.flush()

    # 3. Default admin user
    admin = db.query(User).filter(User.email == "admin@gmail.com").first()
    if admin is None:
        db.add(
            User(
                name="Administrator",
                email="admin@gmail.com",
                password_hash=hash_password("admin123"),
                role_id=admin_role.id,
                status="active",
            )
        )
    else:
        # The existing administrator is the initial protected Super Admin.
        # This is idempotent and never changes the password during startup.
        admin.role_id = super_admin_role.id
        admin.status = "active"
        admin.max_concurrent_sessions = 3
    db.commit()


# ---------------------------------------------------------------------------
# Seed Agnigate OUIs and product catalog
# ---------------------------------------------------------------------------

_AGNIGATE_OUIS = [
    {"oui": "98:a8:78", "manufacturer": "Agnigate Technologies Private Limited", "vendor_key": "agnigate"},
    # Add more Agnigate OUI blocks here as they are registered
]

_AGNIGATE_PRODUCTS = [
    {
        "vendor_key":          "agnigate",
        "product_name":        "AGNI3000-P-120",
        "product_family":      "Firewall",
        "device_type":         "firewall",
        "roles":               ["firewall", "vpn", "sdwan"],
        "model_pattern":       r"AGNI\d{4}-P-\d+",
        "descr_keywords":      ["agnigate", "agni"],
        "default_capabilities": {
            "firewall": True, "vpn": True, "sdwan": True, "routing": True,
        },
    },
    {
        "vendor_key":          "agnigate",
        "product_name":        "AGNI1000-SW",
        "product_family":      "Switch",
        "device_type":         "switch",
        "roles":               ["switch"],
        "model_pattern":       r"AGNI\d{4}-SW",
        "descr_keywords":      ["agnigate", "agni"],
        "default_capabilities": {
            "vlan": True, "lldp": True, "mac_table": True,
        },
    },
    {
        "vendor_key":          "agnigate",
        "product_name":        "AGNI500-AP",
        "product_family":      "Access Point",
        "device_type":         "access_point",
        "roles":               ["access_point", "wireless"],
        "model_pattern":       r"AGNI\d{3}-AP",
        "descr_keywords":      ["agnigate", "agni"],
        "default_capabilities": {
            "wireless": True, "access_point": True,
        },
    },
]


def seed_ouis_and_products(db: Session) -> None:
    """Idempotently seed Agnigate OUIs and product catalog entries."""
    from backend.models.identity import VendorOUI, DeviceProduct  # noqa

    # OUIs
    for entry in _AGNIGATE_OUIS:
        existing = db.query(VendorOUI).filter(VendorOUI.oui == entry["oui"]).first()
        if existing is None:
            db.add(VendorOUI(**entry, source="seed"))

    # Products
    for prod in _AGNIGATE_PRODUCTS:
        existing = db.query(DeviceProduct).filter(
            DeviceProduct.vendor_key == prod["vendor_key"],
            DeviceProduct.product_name == prod["product_name"],
        ).first()
        if existing is None:
            db.add(DeviceProduct(**prod))

    db.commit()
