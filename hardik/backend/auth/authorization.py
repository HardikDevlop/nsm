"""Centralized role-hierarchy authorization helpers.

This module only evaluates authority relationships. Endpoint permission checks
and resource/site scope remain separate concerns.
"""

from typing import Any


def get_authority_level(user: Any) -> int:
    """Return a user's role authority level, denying safely when unavailable."""
    role = getattr(user, "role", None)
    level = getattr(role, "authority_level", None)
    return level if isinstance(level, int) else 0


def has_higher_authority(actor: Any, target: Any) -> bool:
    """Return true only when actor has strictly greater authority than target."""
    if actor is None or target is None:
        return False
    if getattr(actor, "id", None) == getattr(target, "id", None):
        return False
    actor_role = getattr(actor, "role", None)
    target_role = getattr(target, "role", None)
    if actor_role is None or target_role is None:
        return False
    return get_authority_level(actor) > get_authority_level(target)


def can_manage_user(actor: Any, target: Any) -> bool:
    """Return whether actor may perform hierarchy-sensitive actions on target."""
    return has_higher_authority(actor, target)


def can_assign_role(actor: Any, role: Any) -> bool:
    """Return whether actor may assign the role through normal user management."""
    if actor is None or role is None:
        return False
    if not getattr(role, "is_assignable", False):
        return False
    actor_level = get_authority_level(actor)
    role_level = getattr(role, "authority_level", None)
    return isinstance(role_level, int) and role_level < actor_level


def can_modify_role(actor: Any, target_role: Any) -> bool:
    """Return whether actor may modify permissions on a non-system lower role."""
    if actor is None or target_role is None:
        return False
    if getattr(target_role, "is_system_role", False):
        return False
    actor_role = getattr(actor, "role", None)
    target_level = getattr(target_role, "authority_level", None)
    return actor_role is not None and isinstance(target_level, int) and get_authority_level(actor) > target_level


def can_create_role(actor: Any, authority_level: Any) -> bool:
    """Return whether actor may create a normal role at the requested level."""
    if actor is None or not isinstance(authority_level, int):
        return False
    return authority_level < get_authority_level(actor)


def can_manage_permission_definition(actor: Any) -> bool:
    """Only the protected Super Admin role may change permission definitions."""
    role = getattr(actor, "role", None) if actor is not None else None
    return (
        role is not None
        and getattr(role, "role_name", None) == "Super Admin"
        and getattr(role, "is_system_role", False) is True
        and get_authority_level(actor) == 100
    )


def is_super_admin(user: Any) -> bool:
    role = getattr(user, "role", None) if user is not None else None
    return (
        role is not None
        and getattr(role, "role_name", None) == "Super Admin"
        and getattr(role, "is_system_role", False) is True
        and get_authority_level(user) == 100
    )


def can_view_security_audit(actor: Any) -> bool:
    """Only Super Admin and Admin may access security-wide audit views."""
    if is_super_admin(actor):
        return True
    role = getattr(actor, "role", None) if actor is not None else None
    return (
        role is not None
        and getattr(role, "role_name", None) == "Admin"
        and get_authority_level(actor) == 80
    )


def can_view_audit_actor(actor: Any, target: Any) -> bool:
    """Apply hierarchy visibility; legacy actor-less records are Super Admin-only."""
    if is_super_admin(actor):
        return True
    return can_view_security_audit(actor) and target is not None and can_manage_user(actor, target)


def get_accessible_site_ids(user: Any) -> set[int] | None:
    """Return assigned site IDs, or None for the protected Super Admin bypass."""
    if user is None or getattr(user, "role", None) is None:
        return set()
    if is_super_admin(user):
        return None
    sites = getattr(user, "sites", None)
    if not sites:
        return set()
    return {site.id for site in sites if isinstance(getattr(site, "id", None), int)}


def can_access_site(user: Any, site_id: Any) -> bool:
    """Return whether user may access a site under the current scope foundation."""
    # The protected Super Admin bypass is unconditional, including legacy
    # devices/resources whose site_id is currently NULL.
    if user is not None and is_super_admin(user):
        return True
    if user is None or not isinstance(site_id, int) or isinstance(site_id, bool):
        return False
    accessible = get_accessible_site_ids(user)
    return accessible is None or site_id in accessible
