from types import SimpleNamespace

import pytest

from backend.auth.authorization import can_access_site, can_assign_role, can_create_role, can_modify_role, can_manage_user, can_view_audit_actor, can_view_security_audit, get_accessible_site_ids, get_authority_level, has_higher_authority


def user(user_id: int, role: str, level: int | None):
    role_obj = None if level is None else SimpleNamespace(role_name=role, authority_level=level, is_system_role=(role == "Super Admin"))
    return SimpleNamespace(id=user_id, role=role_obj)


def scoped_user(user_id: int, role: str, level: int | None, site_ids: list[int]):
    result = user(user_id, role, level)
    result.sites = [SimpleNamespace(id=site_id) for site_id in site_ids]
    return result


@pytest.mark.parametrize(
    ("actor", "target", "expected"),
    [
        (user(1, "Super Admin", 100), user(2, "Admin", 80), True),
        (user(1, "Super Admin", 100), user(3, "Operator", 50), True),
        (user(1, "Super Admin", 100), user(4, "Viewer", 10), True),
        (user(2, "Admin", 80), user(3, "Operator", 50), True),
        (user(2, "Admin", 80), user(4, "Viewer", 10), True),
        (user(2, "Admin", 80), user(5, "Admin", 80), False),
        (user(2, "Admin", 80), user(1, "Super Admin", 100), False),
        (user(3, "Operator", 50), user(5, "Operator", 50), False),
        (user(3, "Operator", 50), user(2, "Admin", 80), False),
        (user(4, "Viewer", 10), user(3, "Operator", 50), False),
        (user(2, "Admin", 80), user(2, "Admin", 80), False),
    ],
)
def test_hierarchy_management_rule(actor, target, expected):
    assert has_higher_authority(actor, target) is expected
    assert can_manage_user(actor, target) is expected


def test_missing_roles_deny_by_default():
    actor = user(1, "Admin", None)
    target = user(2, "Viewer", 10)
    assert get_authority_level(actor) == 0
    assert not can_manage_user(actor, target)
    assert not can_manage_user(user(1, "Admin", 80), user(2, "Viewer", None))
    assert not can_manage_user(None, target)


def test_role_assignment_requires_lower_assignable_role():
    admin = user(1, "Admin", 80)
    assert can_assign_role(admin, SimpleNamespace(authority_level=50, is_assignable=True))
    assert not can_assign_role(admin, SimpleNamespace(authority_level=80, is_assignable=True))
    assert not can_assign_role(admin, SimpleNamespace(authority_level=100, is_assignable=False))
    assert not can_assign_role(admin, SimpleNamespace(authority_level=10, is_assignable=False))


def test_role_permission_modification_requires_higher_non_system_role():
    admin = user(1, "Admin", 80)
    super_admin = user(2, "Super Admin", 100)
    assert can_modify_role(admin, SimpleNamespace(authority_level=50, is_system_role=False))
    assert not can_modify_role(admin, SimpleNamespace(authority_level=80, is_system_role=False))
    assert not can_modify_role(admin, SimpleNamespace(authority_level=100, is_system_role=True))
    assert can_modify_role(super_admin, SimpleNamespace(authority_level=80, is_system_role=False))
    assert not can_modify_role(super_admin, SimpleNamespace(authority_level=100, is_system_role=True))
    assert not can_modify_role(None, SimpleNamespace(authority_level=10, is_system_role=False))


def test_role_crud_authority_rules():
    admin = user(1, "Admin", 80)
    super_admin = user(2, "Super Admin", 100)
    assert can_create_role(admin, 50)
    assert not can_create_role(admin, 80)
    assert not can_create_role(admin, 100)
    assert can_create_role(super_admin, 80)
    assert can_modify_role(admin, SimpleNamespace(authority_level=50, is_system_role=False))
    assert not can_modify_role(admin, SimpleNamespace(authority_level=80, is_system_role=False))
    assert not can_modify_role(admin, SimpleNamespace(authority_level=100, is_system_role=True))
    assert not can_modify_role(admin, SimpleNamespace(authority_level=10, is_system_role=True))


def test_permission_definition_management_requires_protected_super_admin():
    assert not __import__("backend.auth.authorization", fromlist=["can_manage_permission_definition"]).can_manage_permission_definition(None)
    assert not __import__("backend.auth.authorization", fromlist=["can_manage_permission_definition"]).can_manage_permission_definition(user(1, "Admin", 80))


def test_audit_visibility_hierarchy():
    super_admin = user(1, "Super Admin", 100)
    admin = user(2, "Admin", 80)
    operator = user(3, "Operator", 50)
    viewer = user(4, "Viewer", 10)
    assert can_view_security_audit(super_admin)
    assert can_view_audit_actor(super_admin, admin)
    assert can_view_audit_actor(admin, operator)
    assert can_view_audit_actor(admin, viewer)
    assert not can_view_audit_actor(admin, admin)
    assert not can_view_audit_actor(admin, super_admin)
    assert not can_view_security_audit(operator)
    assert not can_view_security_audit(viewer)
    assert not can_view_audit_actor(admin, None)


def test_site_scope_super_admin_bypasses_assignments():
    admin = scoped_user(1, "Super Admin", 100, [])
    assert get_accessible_site_ids(admin) is None
    assert can_access_site(admin, 1)
    assert can_access_site(admin, 999)


@pytest.mark.parametrize("role, level", [("Admin", 80), ("Operator", 50), ("Viewer", 10)])
def test_site_scope_assigned_and_unassigned(role, level):
    scoped = scoped_user(1, role, level, [10, 20])
    assert get_accessible_site_ids(scoped) == {10, 20}
    assert can_access_site(scoped, 10)
    assert can_access_site(scoped, 20)
    assert not can_access_site(scoped, 30)


def test_site_scope_missing_role_and_zero_sites_deny():
    assert get_accessible_site_ids(user(1, "Admin", None)) == set()
    assert not can_access_site(user(1, "Admin", None), 10)
    viewer = scoped_user(2, "Viewer", 10, [])
    assert get_accessible_site_ids(viewer) == set()
    assert not can_access_site(viewer, 10)


def test_site_scope_multiple_assignments_and_invalid_ids():
    scoped = scoped_user(1, "Operator", 50, [1, 2, 3])
    assert all(can_access_site(scoped, site_id) for site_id in (1, 2, 3))
    assert not can_access_site(scoped, None)
    assert not can_access_site(scoped, True)
