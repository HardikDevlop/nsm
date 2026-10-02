from sqlalchemy import JSON

from backend.database.migrations import MIGRATIONS
from backend.models import AuditLog


def test_audit_log_has_nullable_context_fields():
    expected = {
        "actor_username", "actor_role", "resource_type", "resource_id",
        "target_user_id", "site_id", "request_method", "request_path",
        "source_ip", "user_agent", "failure_reason", "old_values",
        "new_values", "metadata_json",
    }
    columns = AuditLog.__table__.columns
    assert expected <= set(columns.keys())
    assert all(columns[name].nullable for name in expected)
    assert isinstance(columns["old_values"].type, JSON)
    assert isinstance(columns["new_values"].type, JSON)
    assert isinstance(columns["metadata_json"].type, JSON)


def test_audit_log_migration_is_registered():
    migration = next(item for item in MIGRATIONS if item.migration_id == "20260930_0052_audit_log_context_fields")
    assert "audit" in migration.description.lower()
