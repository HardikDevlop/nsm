"""Read-only authorization baseline for the current NMS RBAC implementation.

These tests intentionally capture current behavior.  They do not add scope,
hierarchy, or privilege-escalation protection.
"""

from collections.abc import Generator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.api.routes import router
from backend.auth.security import create_access_token, hash_password
from backend.database.session import Base, get_db
from backend.main import app
from backend.models import AuditLog, Device, Organization, Permission, Role, Site, User


PERMISSIONS = {
    "Admin": {
        "users:read", "users:create", "users:update", "users:delete",
        "roles:read", "roles:create", "roles:update", "roles:delete",
        "permissions:read", "permissions:create", "permissions:update", "permissions:delete",
        "organizations:read", "organizations:create", "organizations:update", "organizations:delete",
        "sites:read", "sites:create", "sites:update", "sites:delete",
        "devices:read", "devices:create", "devices:update", "devices:delete",
        "discovery:execute", "monitoring:execute", "topology:read",
        "alerts:read", "alerts:create", "alerts:update", "alerts:delete",
        "reports:read", "reports:create", "reports:update", "reports:delete",
        "audit_logs:read",
    },
    "Operator": {
        "dashboard:read", "devices:read", "devices:create", "devices:update",
        "sites:read", "discovery:execute", "monitoring:execute", "topology:read",
        "alerts:read", "alerts:update", "reports:read", "audit_logs:read",
    },
    "Viewer": {
        "dashboard:read", "devices:read", "sites:read", "topology:read",
        "alerts:read", "reports:read", "audit_logs:read",
    },
}


@pytest.fixture()
def security_context() -> Generator[dict, None, None]:
    """Provide a disposable database and an application using that database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = SessionLocal()
    try:
        permissions = {}
        for code in sorted(set().union(*PERMISSIONS.values())):
            module, action = code.split(":", 1)
            permissions[code] = Permission(
                code=code, name=code, module=module, action=action,
            )
        db.add_all(permissions.values())
        db.flush()

        roles = {}
        role_levels = {"Admin": 80, "Operator": 50, "Viewer": 10}
        for name, codes in PERMISSIONS.items():
            role = Role(role_name=name, authority_level=role_levels[name], is_system_role=False, is_assignable=True)
            role.permissions = [permissions[code] for code in codes]
            roles[name] = role
            db.add(role)
        db.flush()

        users = {}
        for name in PERMISSIONS:
            user = User(
                name=f"Test {name}",
                email=f"{name.lower()}@example.com",
                password_hash=hash_password("test-password"),
                role_id=roles[name].id,
                status="active",
            )
            users[name] = user
            db.add(user)
        db.flush()

        org = Organization(name="Authorization Test Organization")
        db.add(org)
        db.flush()
        site_a = Site(organization_id=org.id, name="Site A")
        site_b = Site(organization_id=org.id, name="Site B")
        db.add_all([site_a, site_b])
        db.flush()
        device_a = Device(site_id=site_a.id, hostname="device-a", ip_address="192.0.2.10")
        device_b = Device(site_id=site_b.id, hostname="device-b", ip_address="192.0.2.11")
        db.add_all([device_a, device_b])
        users["Admin"].sites.append(site_a)
        users["Operator"].sites.append(site_a)
        users["Viewer"].sites.append(site_a)
        db.commit()

        def override_db():
            yield db

        app.dependency_overrides[get_db] = override_db
        client = TestClient(app, raise_server_exceptions=True)
        tokens = {
            name: create_access_token(user.email) for name, user in users.items()
        }
        yield {
            "client": client,
            "db": db,
            "users": users,
            "roles": roles,
            "permissions": permissions,
            "site_a": site_a,
            "site_b": site_b,
            "device_a": device_a,
            "device_b": device_b,
            "tokens": tokens,
        }
    finally:
        app.dependency_overrides.pop(get_db, None)
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def request(ctx, role: str, method: str, path: str, **kwargs):
    headers = {"Authorization": f"Bearer {ctx['tokens'][role]}"}
    return ctx["client"].request(method, path, headers=headers, **kwargs)


def test_authentication_boundary_and_permission_denial(security_context):
    ctx = security_context
    client = ctx["client"]

    assert client.get("/api/v1/users").status_code == 401
    assert request(ctx, "Viewer", "get", "/api/v1/users").status_code == 403
    assert request(ctx, "Admin", "get", "/api/v1/users").status_code == 200


@pytest.mark.parametrize("role, expected", [("Admin", 200), ("Operator", 403), ("Viewer", 403)])
def test_role_management_permission_baseline(security_context, role, expected):
    response = request(security_context, role, "get", "/api/v1/roles")
    assert response.status_code == expected


@pytest.mark.parametrize("role, expected", [("Admin", 200), ("Operator", 403), ("Viewer", 403)])
def test_permission_management_permission_baseline(security_context, role, expected):
    response = request(security_context, role, "get", "/api/v1/permissions")
    assert response.status_code == expected


@pytest.mark.parametrize("role, expected", [("Admin", 200), ("Operator", 200), ("Viewer", 200)])
def test_sites_and_devices_read_permission_baseline(security_context, role, expected):
    ctx = security_context
    assert request(ctx, role, "get", "/api/v1/sites").status_code == expected
    assert request(ctx, role, "get", "/api/v1/devices").status_code == expected


def test_cross_site_device_read_is_scope_restricted(security_context):
    ctx = security_context
    response = request(ctx, "Operator", "get", f"/api/v1/devices/{ctx['device_b'].id}")
    assert response.status_code == 404


def test_cross_site_device_update_is_scope_restricted(security_context):
    ctx = security_context
    response = request(
        ctx, "Operator", "patch", f"/api/v1/devices/{ctx['device_b'].id}",
        json={"hostname": "device-b-updated-by-operator"},
    )
    assert response.status_code == 404


def test_scoped_device_list_hides_unassigned_sites(security_context):
    ctx = security_context
    response = request(ctx, "Operator", "get", "/api/v1/devices")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [ctx["device_a"].id]


def test_user_management_escalation_baseline(security_context):
    ctx = security_context
    viewer = request(ctx, "Viewer", "get", "/api/v1/users")
    operator = request(ctx, "Operator", "get", "/api/v1/users")
    assert viewer.status_code == 403
    assert operator.status_code == 403

    # The current seeded Operator has no user-management permission. This
    # records the permission boundary without asserting future hierarchy rules.
    assert request(ctx, "Admin", "post", "/api/v1/users", json={
        "name": "Created Test User", "email": "created@example.com",
        "password": "test-password", "role_id": ctx["roles"]["Viewer"].id,
    }).status_code == 201


def test_admin_can_currently_modify_another_admin(security_context):
    ctx = security_context
    other_admin = User(
        name="Second Admin", email="second-admin@example.com",
        password_hash=hash_password("test-password"),
        role_id=ctx["roles"]["Admin"].id, status="active",
    )
    ctx["db"].add(other_admin)
    ctx["db"].commit()
    response = request(ctx, "Admin", "patch", f"/api/v1/users/{other_admin.id}", json={"name": "Changed"})
    assert response.status_code == 403


def test_admin_can_replace_role_permissions_currently(security_context):
    ctx = security_context
    role_id = ctx["roles"]["Viewer"].id
    permission_id = ctx["permissions"]["users:delete"].id
    response = request(ctx, "Admin", "put", f"/api/v1/roles/{role_id}/permissions", json={"permission_ids": [permission_id]})
    assert response.status_code == 200


def test_audit_visibility_and_no_public_mutation_routes(security_context):
    ctx = security_context
    assert request(ctx, "Viewer", "get", "/api/v1/audit-logs").status_code == 403
    assert request(ctx, "Viewer", "get", "/api/v1/audit-logs/users").status_code == 403
    assert request(ctx, "Viewer", "patch", "/api/v1/audit-logs/1", json={"action": "tampered"}).status_code == 405
    assert request(ctx, "Viewer", "delete", "/api/v1/audit-logs/1").status_code == 405


@pytest.mark.parametrize("status", ["inactive", "blocked", "locked"])
def test_non_active_users_are_rejected(security_context, status):
    ctx = security_context
    user = ctx["users"]["Viewer"]
    user.status = status
    ctx["db"].commit()
    assert request(ctx, "Viewer", "get", "/api/v1/auth/me").status_code == 403


def test_invalid_jwt_is_rejected(security_context):
    response = security_context["client"].get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer not-a-valid-jwt"}
    )
    assert response.status_code == 401


def _add_super_admin(ctx):
    role = Role(role_name="Super Admin", authority_level=100, is_system_role=True, is_assignable=False)
    role.permissions = list(ctx["roles"]["Admin"].permissions)
    ctx["db"].add(role)
    ctx["db"].flush()
    user = User(name="Test Super Admin", email="superadmin@example.com", password_hash=hash_password("test-password"), role_id=role.id, status="active")
    ctx["db"].add(user)
    ctx["db"].commit()
    ctx["tokens"]["Super Admin"] = create_access_token(user.email)
    ctx["roles"]["Super Admin"] = role
    return role


@pytest.mark.parametrize("actor, target_role, expected", [
    ("Super Admin", "Admin", 201),
    ("Super Admin", "Operator", 201),
    ("Admin", "Operator", 201),
    ("Admin", "Viewer", 201),
    ("Admin", "Admin", 403),
])
def test_user_creation_hierarchy(security_context, actor, target_role, expected):
    ctx = security_context
    if actor == "Super Admin":
        _add_super_admin(ctx)
    response = request(ctx, actor, "post", "/api/v1/users", json={
        "name": f"Created {actor} {target_role}",
        "email": f"created-{actor.lower().replace(' ', '-')}-{target_role.lower()}@example.com",
        "password": "test-password",
        "role_id": ctx["roles"][target_role].id,
    })
    assert response.status_code == expected


def test_admin_cannot_create_super_admin(security_context):
    ctx = security_context
    super_admin_role = _add_super_admin(ctx)
    response = request(ctx, "Admin", "post", "/api/v1/users", json={
        "name": "Escalated User", "email": "escalated@example.com",
        "password": "test-password", "role_id": super_admin_role.id,
    })
    assert response.status_code == 403


def test_operator_cannot_create_user_without_users_create_permission(security_context):
    ctx = security_context
    response = request(ctx, "Operator", "post", "/api/v1/users", json={
        "name": "Operator Created", "email": "operator-created@example.com",
        "password": "test-password", "role_id": ctx["roles"]["Viewer"].id,
    })
    assert response.status_code == 403


def test_non_assignable_role_cannot_be_created_normally(security_context):
    ctx = security_context
    protected_role = Role(role_name="Protected", authority_level=10, is_system_role=True, is_assignable=False)
    ctx["db"].add(protected_role)
    ctx["db"].commit()
    response = request(ctx, "Admin", "post", "/api/v1/users", json={
        "name": "Protected Target", "email": "protected@example.com",
        "password": "test-password", "role_id": protected_role.id,
    })
    assert response.status_code == 403


def test_role_permission_replacement_enforces_hierarchy(security_context):
    ctx = security_context
    permission_id = ctx["permissions"]["devices:read"].id
    response = request(ctx, "Admin", "put", f"/api/v1/roles/{ctx['roles']['Operator'].id}/permissions", json={"permission_ids": [permission_id]})
    assert response.status_code == 200
    response = request(ctx, "Admin", "put", f"/api/v1/roles/{ctx['roles']['Admin'].id}/permissions", json={"permission_ids": [permission_id]})
    assert response.status_code == 403


def test_super_admin_can_modify_lower_role_but_not_system_role(security_context):
    ctx = security_context
    super_role = _add_super_admin(ctx)
    permission_id = ctx["permissions"]["devices:read"].id
    response = request(ctx, "Super Admin", "put", f"/api/v1/roles/{ctx['roles']['Admin'].id}/permissions", json={"permission_ids": [permission_id]})
    assert response.status_code == 200
    response = request(ctx, "Super Admin", "put", f"/api/v1/roles/{super_role.id}/permissions", json={"permission_ids": [permission_id]})
    assert response.status_code == 404


def test_operator_and_viewer_remain_blocked_from_role_permission_replacement(security_context):
    ctx = security_context
    permission_id = ctx["permissions"]["devices:read"].id
    for actor in ("Operator", "Viewer"):
        response = request(ctx, actor, "put", f"/api/v1/roles/{ctx['roles']['Viewer'].id}/permissions", json={"permission_ids": [permission_id]})
        assert response.status_code == 403


def test_role_crud_endpoints_enforce_hierarchy(security_context):
    ctx = security_context
    create = request(ctx, "Admin", "post", "/api/v1/roles", json={"role_name": "Too High", "authority_level": 80})
    assert create.status_code == 403
    create = request(ctx, "Admin", "post", "/api/v1/roles", json={"role_name": "Lower Role", "authority_level": 20})
    assert create.status_code == 201
    lower_id = create.json()["id"]
    update = request(ctx, "Admin", "patch", f"/api/v1/roles/{lower_id}", json={"authority_level": 80})
    assert update.status_code == 403
    update = request(ctx, "Admin", "patch", f"/api/v1/roles/{lower_id}", json={"role_name": "Renamed Lower"})
    assert update.status_code == 200
    assert request(ctx, "Admin", "delete", f"/api/v1/roles/{ctx['roles']['Admin'].id}").status_code == 403


def test_super_admin_role_is_not_deletable(security_context):
    ctx = security_context
    super_role = _add_super_admin(ctx)
    assert request(ctx, "Admin", "delete", f"/api/v1/roles/{super_role.id}").status_code == 404


def test_super_admin_can_manage_permission_definitions(security_context):
    ctx = security_context
    _add_super_admin(ctx)
    create = request(ctx, "Super Admin", "post", "/api/v1/permissions", json={
        "code": "test:permission", "name": "Test Permission", "module": "test", "action": "permission",
    })
    assert create.status_code == 201
    permission_id = create.json()["id"]
    assert request(ctx, "Super Admin", "patch", f"/api/v1/permissions/{permission_id}", json={"name": "Updated Permission"}).status_code == 200
    assert request(ctx, "Super Admin", "delete", f"/api/v1/permissions/{permission_id}").status_code == 200


@pytest.mark.parametrize("actor", ["Admin", "Operator", "Viewer"])
def test_non_super_admin_cannot_manage_permission_definitions(security_context, actor):
    ctx = security_context
    permission_id = ctx["permissions"]["devices:read"].id
    payload = {"code": f"blocked:{actor.lower()}", "name": "Blocked", "module": "blocked", "action": "create"}
    create = request(ctx, actor, "post", "/api/v1/permissions", json=payload)
    assert create.status_code == 403
    update = request(ctx, actor, "patch", f"/api/v1/permissions/{permission_id}", json={"name": "Blocked Update"})
    assert update.status_code == 403
    delete = request(ctx, actor, "delete", f"/api/v1/permissions/{permission_id}")
    assert delete.status_code == 403


@pytest.mark.parametrize("status", ["active", "disabled", "blocked", "locked"])
def test_user_statuses_are_standardized_and_auth_enforced(security_context, status):
    ctx = security_context
    user = ctx["users"]["Viewer"]
    user.status = status
    ctx["db"].commit()
    expected = 200 if status == "active" else 403
    assert request(ctx, "Viewer", "get", "/api/v1/auth/me").status_code == expected


def test_arbitrary_user_status_cannot_be_saved(security_context):
    ctx = security_context
    response = request(ctx, "Admin", "post", "/api/v1/users", json={
        "name": "Invalid Status", "email": "invalid-status@example.com",
        "password": "test-password", "role_id": ctx["roles"]["Viewer"].id, "status": "suspended",
    })
    assert response.status_code == 422


def test_explicit_user_status_control_and_audit(security_context):
    ctx = security_context
    response = request(ctx, "Admin", "patch", f"/api/v1/users/{ctx['users']['Operator'].id}/status", json={"status": "blocked"})
    assert response.status_code == 200
    audit_rows = ctx["db"].query(__import__("backend.models", fromlist=["AuditLog"]).AuditLog).all()
    assert any(row.action == "USER_STATUS_CHANGED" and row.new_values.get("status") == "blocked" for row in audit_rows)
    assert request(ctx, "Admin", "patch", f"/api/v1/users/{ctx['users']['Operator'].id}/status", json={"status": "active"}).status_code == 200


@pytest.mark.parametrize("target", ["Admin"])
def test_admin_cannot_change_equal_or_higher_user_status(security_context, target):
    ctx = security_context
    response = request(ctx, "Admin", "patch", f"/api/v1/users/{ctx['users'][target].id}/status", json={"status": "blocked"})
    assert response.status_code == 403


def test_self_status_change_is_denied(security_context):
    ctx = security_context
    response = request(ctx, "Admin", "patch", f"/api/v1/users/{ctx['users']['Admin'].id}/status", json={"status": "blocked"})
    assert response.status_code == 403


@pytest.mark.parametrize("actor", ["Operator", "Viewer"])
def test_operator_and_viewer_cannot_change_user_status(security_context, actor):
    ctx = security_context
    response = request(ctx, actor, "patch", f"/api/v1/users/{ctx['users']['Viewer'].id}/status", json={"status": "blocked"})
    assert response.status_code == 403


def test_status_changes_cannot_bypass_explicit_endpoint(security_context):
    ctx = security_context
    response = request(ctx, "Admin", "patch", f"/api/v1/users/{ctx['users']['Operator'].id}", json={"status": "blocked"})
    assert response.status_code == 200
    assert response.json()["status"] == "active"


def test_failed_login_locks_after_five_attempts_and_audits(security_context):
    ctx = security_context
    for _ in range(4):
        assert ctx["client"].post("/api/v1/auth/login", json={"email": "viewer@example.com", "password": "wrong-password"}).status_code == 401
    user = ctx["users"]["Viewer"]
    assert user.failed_login_attempts == 4
    assert ctx["client"].post("/api/v1/auth/login", json={"email": "viewer@example.com", "password": "wrong-password"}).status_code == 401
    ctx["db"].refresh(user)
    assert user.status == "locked"
    assert user.failed_login_attempts == 5
    assert user.locked_until is not None
    assert any(row.action == "ACCOUNT_LOCKED" for row in ctx["db"].query(AuditLog).all())


def test_expired_lock_auto_unlocks_and_success_resets_login_state(security_context):
    ctx = security_context
    user = ctx["users"]["Viewer"]
    user.status = "locked"
    user.failed_login_attempts = 5
    user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    ctx["db"].commit()
    response = ctx["client"].post("/api/v1/auth/login", json={"email": "viewer@example.com", "password": "test-password"})
    assert response.status_code == 200
    ctx["db"].refresh(user)
    assert user.status == "active"
    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    assert user.last_login_at is not None


@pytest.mark.parametrize("status", ["blocked", "disabled"])
def test_permanent_non_active_statuses_never_auto_unlock(security_context, status):
    ctx = security_context
    user = ctx["users"]["Viewer"]
    user.status = status
    user.failed_login_attempts = 5
    user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
    ctx["db"].commit()
    assert ctx["client"].post("/api/v1/auth/login", json={"email": "viewer@example.com", "password": "test-password"}).status_code == 401
    ctx["db"].refresh(user)
    assert user.status == status


def test_successful_login_resets_failed_attempts_and_updates_last_login(security_context):
    ctx = security_context
    user = ctx["users"]["Viewer"]
    user.failed_login_attempts = 3
    ctx["db"].commit()
    assert ctx["client"].post("/api/v1/auth/login", json={"email": "viewer@example.com", "password": "test-password"}).status_code == 200
    ctx["db"].refresh(user)
    assert user.failed_login_attempts == 0
    assert user.last_login_at is not None


def _seed_audit_visibility_rows(ctx):
    ctx["db"].add_all([
        AuditLog(user_id=ctx["users"]["Operator"].id, action="OPERATOR_EVENT", resource_name="user:operator"),
        AuditLog(user_id=ctx["users"]["Viewer"].id, action="VIEWER_EVENT", resource_name="user:viewer"),
        AuditLog(user_id=ctx["users"]["Admin"].id, action="ADMIN_EVENT", resource_name="user:admin"),
        AuditLog(user_id=None, action="LEGACY_EVENT", resource_name="legacy"),
    ])
    ctx["db"].commit()


def test_audit_visibility_filters_by_hierarchy_and_legacy_safety(security_context):
    ctx = security_context
    _seed_audit_visibility_rows(ctx)
    admin_rows = request(ctx, "Admin", "get", "/api/v1/audit-logs").json()
    actions = {row["action"] for row in admin_rows}
    assert "OPERATOR_EVENT" in actions and "VIEWER_EVENT" in actions
    assert "ADMIN_EVENT" not in actions and "LEGACY_EVENT" not in actions
    assert request(ctx, "Admin", "get", "/api/v1/audit-logs/users").status_code == 200
    assert request(ctx, "Admin", "get", "/api/v1/audit-logs", params={"user_id": ctx["users"]["Admin"].id}).json() == []


def test_super_admin_sees_all_audit_records(security_context):
    ctx = security_context
    _add_super_admin(ctx)
    _seed_audit_visibility_rows(ctx)
    response = request(ctx, "Super Admin", "get", "/api/v1/audit-logs")
    actions = {row["action"] for row in response.json()}
    assert {"OPERATOR_EVENT", "VIEWER_EVENT", "ADMIN_EVENT", "LEGACY_EVENT"} <= actions


@pytest.mark.parametrize("actor", ["Operator", "Viewer"])
def test_operator_and_viewer_cannot_access_security_audit(security_context, actor):
    ctx = security_context
    assert request(ctx, actor, "get", "/api/v1/audit-logs").status_code == 403
    assert request(ctx, actor, "get", "/api/v1/audit-logs/users").status_code == 403


def test_audit_log_filters_pagination_and_ordering(security_context):
    ctx = security_context
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = [
        AuditLog(user_id=ctx["users"]["Operator"].id, action="FILTER_A", resource_name="device:1", outcome="success", resource_type="device", resource_id=1, source_ip="192.0.2.1", timestamp=now - timedelta(minutes=1)),
        AuditLog(user_id=ctx["users"]["Viewer"].id, action="FILTER_B", resource_name="user:2", outcome="failure", resource_type="user", resource_id=2, source_ip="192.0.2.2", timestamp=now - timedelta(minutes=2)),
        AuditLog(user_id=ctx["users"]["Operator"].id, action="FILTER_A", resource_name="device:3", outcome="success", resource_type="device", resource_id=3, source_ip="192.0.2.1", timestamp=now - timedelta(minutes=3)),
    ]
    ctx["db"].add_all(rows); ctx["db"].commit()
    base = "/api/v1/audit-logs"
    assert all(row["action"] == "FILTER_A" for row in request(ctx, "Admin", "get", base, params={"action": "FILTER_A"}).json())
    assert all(row["user_id"] == ctx["users"]["Operator"].id for row in request(ctx, "Admin", "get", base, params={"user_id": ctx["users"]["Operator"].id}).json())
    assert all(row["outcome"] == "failure" for row in request(ctx, "Admin", "get", base, params={"outcome": "failure"}).json())
    assert [row["action"] for row in request(ctx, "Admin", "get", base, params={"resource_type": "device", "resource_id": 1, "source_ip": "192.0.2.1"}).json()] == ["FILTER_A"]
    date_rows = request(ctx, "Admin", "get", base, params={"start_date": (now - timedelta(minutes=2, seconds=30)).isoformat(), "end_date": (now - timedelta(seconds=30)).isoformat()}).json()
    assert {row["action"] for row in date_rows} >= {"FILTER_A", "FILTER_B"}
    page = request(ctx, "Admin", "get", base, params={"action": "FILTER_A", "limit": 1, "offset": 0}).json()
    next_page = request(ctx, "Admin", "get", base, params={"action": "FILTER_A", "limit": 1, "offset": 1}).json()
    assert len(page) == 1 and len(next_page) == 1 and page[0]["timestamp"] >= next_page[0]["timestamp"]
    assert request(ctx, "Admin", "get", base, params={"start_date": now.isoformat(), "end_date": (now - timedelta(days=1)).isoformat()}).status_code == 400


def test_admin_filters_cannot_reach_higher_authority_audit_rows(security_context):
    ctx = security_context
    ctx["db"].add(AuditLog(user_id=ctx["users"]["Admin"].id, action="HIGH_EVENT", resource_name="user:1", resource_type="user", resource_id=ctx["users"]["Admin"].id))
    ctx["db"].commit()
    response = request(ctx, "Admin", "get", "/api/v1/audit-logs", params={"action": "HIGH_EVENT", "user_id": ctx["users"]["Admin"].id})
    assert response.status_code == 200 and response.json() == []


def test_audit_summary_uses_hierarchy_and_database_counts(security_context):
    ctx = security_context
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    ctx["db"].add_all([
        AuditLog(user_id=ctx["users"]["Operator"].id, action="LOGIN_SUCCESS", resource_name="user:operator", outcome="success", timestamp=now - timedelta(minutes=1)),
        AuditLog(user_id=ctx["users"]["Operator"].id, action="LOGIN_FAILED", resource_name="user:operator", outcome="failure", timestamp=now - timedelta(minutes=2)),
        AuditLog(user_id=ctx["users"]["Operator"].id, action="ACCOUNT_LOCKED", resource_name="user:operator", outcome="failure", timestamp=now - timedelta(minutes=3)),
        AuditLog(user_id=ctx["users"]["Viewer"].id, action="USER_STATUS_CHANGED", resource_name="user:viewer", outcome="success", timestamp=now - timedelta(minutes=4)),
        AuditLog(user_id=ctx["users"]["Admin"].id, action="LOGIN_SUCCESS", resource_name="user:admin", outcome="success", timestamp=now - timedelta(minutes=5)),
        AuditLog(user_id=None, action="LOGIN_SUCCESS", resource_name="legacy", outcome="success", timestamp=now - timedelta(minutes=6)),
    ])
    ctx["db"].commit()
    summary = request(ctx, "Admin", "get", "/api/v1/audit-logs/summary").json()
    assert summary == {"total_activities": 4, "successful_actions": 2, "failed_actions": 2, "login_success": 1, "login_failed": 1, "account_locked": 1, "user_status_changes": 1}
    assert request(ctx, "Admin", "get", "/api/v1/audit-logs/summary", params={"start_date": now.isoformat(), "end_date": (now - timedelta(days=1)).isoformat()}).status_code == 400


def test_super_admin_summary_includes_legacy_and_admin_activity(security_context):
    ctx = security_context
    _add_super_admin(ctx)
    ctx["db"].add_all([
        AuditLog(user_id=ctx["users"]["Admin"].id, action="LOGIN_SUCCESS", resource_name="user:admin", outcome="success"),
        AuditLog(user_id=None, action="LOGIN_FAILED", resource_name="legacy", outcome="failure"),
    ])
    ctx["db"].commit()
    summary = request(ctx, "Super Admin", "get", "/api/v1/audit-logs/summary").json()
    assert summary["login_success"] >= 1 and summary["login_failed"] >= 1


@pytest.mark.parametrize("actor", ["Operator", "Viewer"])
def test_operator_and_viewer_cannot_view_audit_summary(security_context, actor):
    assert request(security_context, actor, "get", "/api/v1/audit-logs/summary").status_code == 403


def test_site_scope_list_detail_and_mutation_protection(security_context):
    ctx = security_context
    site_a = ctx["site_a"]
    site_b = ctx["site_b"]

    assert [item["id"] for item in request(ctx, "Admin", "get", "/api/v1/sites").json()] == [site_a.id]
    assert request(ctx, "Admin", "get", f"/api/v1/sites/{site_a.id}").status_code == 200
    assert request(ctx, "Admin", "get", f"/api/v1/sites/{site_b.id}").status_code == 404
    assert request(ctx, "Admin", "patch", f"/api/v1/sites/{site_b.id}", json={"name": "blocked"}).status_code == 404
    assert request(ctx, "Admin", "delete", f"/api/v1/sites/{site_b.id}").status_code == 404


@pytest.mark.parametrize("role", ["Operator", "Viewer"])
def test_site_scope_operator_viewer_assigned_vs_unassigned(security_context, role):
    ctx = security_context
    assert [item["id"] for item in request(ctx, role, "get", "/api/v1/sites").json()] == [ctx["site_a"].id]
    assert request(ctx, role, "get", f"/api/v1/sites/{ctx['site_a'].id}").status_code == 200
    assert request(ctx, role, "get", f"/api/v1/sites/{ctx['site_b'].id}").status_code == 404


def test_zero_site_user_has_empty_site_list(security_context):
    ctx = security_context
    ctx["users"]["Viewer"].sites.clear()
    ctx["db"].commit()
    assert request(ctx, "Viewer", "get", "/api/v1/sites").json() == []


def test_super_admin_site_scope_bypass(security_context):
    ctx = security_context
    super_role = Role(
        role_name="Super Admin", authority_level=100,
        is_system_role=True, is_assignable=False,
        permissions=list(ctx["roles"]["Admin"].permissions),
    )
    super_user = User(
        name="Test Super Admin", email="super@example.com",
        password_hash=hash_password("test-password"), role=super_role, status="active",
    )
    ctx["db"].add(super_user)
    ctx["db"].commit()
    headers = {"Authorization": f"Bearer {create_access_token(super_user.email)}"}
    assert {item["id"] for item in ctx["client"].get("/api/v1/sites", headers=headers).json()} == {ctx["site_a"].id, ctx["site_b"].id}
    assert ctx["client"].get(f"/api/v1/sites/{ctx['site_b'].id}", headers=headers).status_code == 200


def test_cross_site_snmp_and_monitoring_data_are_scope_restricted(security_context):
    ctx = security_context
    device_b_id = ctx["device_b"].id
    snmp = request(ctx, "Operator", "get", f"/api/v1/snmp/devices/{device_b_id}/overview")
    assert snmp.status_code == 404
    monitoring = request(ctx, "Operator", "post", "/api/v1/monitoring/data", json={"device_id": device_b_id})
    assert monitoring.status_code == 404


def test_user_site_assignment_replacement_and_scope(security_context):
    ctx = security_context
    admin = ctx["users"]["Admin"]
    operator = ctx["users"]["Operator"]
    response = request(ctx, "Admin", "put", f"/api/v1/users/{operator.id}/sites", json={"site_ids": [ctx["site_a"].id]})
    assert response.status_code == 200
    assert response.json() == {"site_ids": [ctx["site_a"].id]}
    assert request(ctx, "Admin", "get", f"/api/v1/users/{operator.id}/sites").json() == {"site_ids": [ctx["site_a"].id]}
    response = request(ctx, "Admin", "put", f"/api/v1/users/{operator.id}/sites", json={"site_ids": []})
    assert response.status_code == 200
    assert response.json() == {"site_ids": []}


def test_user_site_assignment_hierarchy_and_admin_subset(security_context):
    ctx = security_context
    operator = ctx["users"]["Operator"]
    admin = ctx["users"]["Admin"]
    assert request(ctx, "Operator", "put", f"/api/v1/users/{operator.id}/sites", json={"site_ids": [ctx["site_a"].id]}).status_code == 403
    assert request(ctx, "Admin", "put", f"/api/v1/users/{admin.id}/sites", json={"site_ids": [ctx["site_a"].id]}).status_code == 403
    assert request(ctx, "Admin", "put", f"/api/v1/users/{operator.id}/sites", json={"site_ids": [ctx["site_b"].id]}).status_code == 403
    assert request(ctx, "Admin", "put", f"/api/v1/users/{operator.id}/sites", json={"site_ids": [99999]}).status_code == 400
    assert request(ctx, "Admin", "put", f"/api/v1/users/{operator.id}/sites", json={"site_ids": [ctx["site_a"].id, ctx["site_a"].id]}).status_code == 200


def test_seeded_super_admin_has_complete_permission_catalog():
    from backend.seed import seed_rbac
    from backend.models import Permission, Role, User
    from backend.database.session import SessionLocal

    db = SessionLocal()
    try:
        seed_rbac(db)
        role = db.query(Role).filter(Role.role_name == "Super Admin").one()
        catalog = {permission.code for permission in db.query(Permission).all()}
        assert {permission.code for permission in role.permissions} == catalog
        assert role.authority_level == 100
        assert role.is_system_role is True
        assert role.is_assignable is False
        user = db.query(User).filter(User.email == "admin@gmail.com").one()
        assert user.role_id == role.id
        assert user.status == "active"
    finally:
        db.close()


def test_protected_super_admin_is_hidden_and_non_leaking(security_context):
    ctx = security_context
    role = Role(role_name="Super Admin", authority_level=100, is_system_role=True, is_assignable=False)
    role.permissions = list(ctx["roles"]["Admin"].permissions)
    ctx["db"].add(role)
    ctx["db"].flush()
    protected = User(name="Protected Super Admin", email="protected-super@example.com", password_hash=hash_password("test-password"), role_id=role.id, status="active")
    ctx["db"].add(protected)
    ctx["db"].commit()
    ctx["tokens"]["Protected Super Admin"] = create_access_token(protected.email)

    users = request(ctx, "Admin", "get", "/api/v1/users").json()
    roles = request(ctx, "Admin", "get", "/api/v1/roles").json()
    assert all(item["email"] != protected.email for item in users)
    assert all(item["role_name"] != "Super Admin" for item in roles)
    assert request(ctx, "Admin", "get", f"/api/v1/users/{protected.id}").status_code == 404
    assert request(ctx, "Admin", "patch", f"/api/v1/users/{protected.id}", json={"name": "nope"}).status_code == 404
    assert request(ctx, "Admin", "delete", f"/api/v1/users/{protected.id}").status_code == 404
    assert request(ctx, "Admin", "patch", f"/api/v1/users/{protected.id}/status", json={"status": "blocked"}).status_code == 404
    assert request(ctx, "Admin", "post", f"/api/v1/users/{protected.id}/role", json={"role_id": ctx["roles"]["Viewer"].id}).status_code == 404
    assert request(ctx, "Admin", "get", f"/api/v1/users/{protected.id}/sites").status_code == 404
    assert request(ctx, "Admin", "put", f"/api/v1/users/{protected.id}/sites", json={"site_ids": []}).status_code == 404
    assert request(ctx, "Admin", "get", f"/api/v1/roles/{role.id}").status_code == 404
    assert request(ctx, "Admin", "patch", f"/api/v1/roles/{role.id}", json={"role_name": "nope"}).status_code == 404
    assert request(ctx, "Admin", "delete", f"/api/v1/roles/{role.id}").status_code == 404
    assert request(ctx, "Admin", "get", f"/api/v1/roles/{role.id}/permissions").status_code == 404
    assert request(ctx, "Admin", "put", f"/api/v1/roles/{role.id}/permissions", json={"permission_ids": []}).status_code == 404
