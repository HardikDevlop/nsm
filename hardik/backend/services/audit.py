"""Centralized structured audit-event recording and secret redaction."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy.orm import Session

from backend.models import AuditLog

_REDACTED = "[REDACTED]"
_SENSITIVE_KEY_PARTS = (
    "password", "token", "secret", "community", "api_key",
    "authorization", "credential",
)


def redact_sensitive(value: Any) -> Any:
    """Recursively copy JSON-like data while redacting sensitive keys."""
    if isinstance(value, Mapping):
        return {
            key: _REDACTED if any(part in str(key).lower() for part in _SENSITIVE_KEY_PARTS)
            else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return [redact_sensitive(item) for item in value]
    return value


def record_audit_event(
    db: Session,
    *,
    actor: Any = None,
    action: str,
    resource_type: str | None = None,
    resource_id: int | None = None,
    target_user_id: int | None = None,
    site_id: int | None = None,
    outcome: str = "success",
    request_method: str | None = None,
    request_path: str | None = None,
    source_ip: str | None = None,
    user_agent: str | None = None,
    failure_reason: str | None = None,
    old_values: Mapping[str, Any] | None = None,
    new_values: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> AuditLog | None:
    """Persist one structured audit event without exposing secret values."""
    role = getattr(actor, "role", None)
    resource_name = resource_type or "unknown"
    if resource_id is not None:
        resource_name = f"{resource_name}:{resource_id}"
    entry = AuditLog(
        user_id=getattr(actor, "id", None),
        action=action,
        resource_name=resource_name,
        outcome=outcome,
        actor_username=getattr(actor, "email", None) or getattr(actor, "name", None),
        actor_role=getattr(role, "role_name", None),
        resource_type=resource_type,
        resource_id=resource_id,
        target_user_id=target_user_id,
        site_id=site_id,
        request_method=request_method,
        request_path=request_path,
        source_ip=source_ip,
        user_agent=user_agent,
        failure_reason=failure_reason,
        old_values=redact_sensitive(old_values) if old_values is not None else None,
        new_values=redact_sensitive(new_values) if new_values is not None else None,
        metadata_json=redact_sensitive(metadata) if metadata is not None else None,
    )
    try:
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry
    except Exception:
        db.rollback()
        return None


# Explicit alias for callers that prefer an audit-specific verb.
create_audit_event = record_audit_event
