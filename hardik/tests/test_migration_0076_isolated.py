from types import SimpleNamespace

import pytest
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID

from backend.database import migrate_0076 as migration
from backend.windows_monitoring.models import WindowsHelperChallenge


class FakeResult:
    def __init__(self, row=None): self._row = row
    def first(self): return self._row


class FakeConnection:
    def __init__(self, applied=False):
        self.applied = applied
        self.statements = []
        self.engine = SimpleNamespace(url=SimpleNamespace(database="postgres"))

    def execute(self, statement, params=None):
        sql = str(statement)
        self.statements.append((sql, params))
        if "FROM schema_migrations" in sql:
            return FakeResult((1,) if self.applied else None)
        return FakeResult()


def test_model_declares_challenge_table_constraints_and_indexes():
    table = WindowsHelperChallenge.__table__
    assert table.name == migration.CHALLENGE_TABLE
    assert {tuple(const.columns.keys()) for const in table.constraints if const.__class__.__name__ == "UniqueConstraint"} >= {
        ("challenge_id",), ("device_id", "collection_id")
    }
    assert {index.name for index in table.indexes} >= {
        "ix_windows_helper_challenges_device_expiry",
        "ix_windows_helper_challenges_collection",
    }


def test_scope_is_not_registered_in_application_migration_list():
    from backend.database.migrations import MIGRATIONS
    assert migration.MIGRATION_ID not in {item.migration_id for item in MIGRATIONS}


@pytest.mark.parametrize("actual, expected, length, timezone", [
    (Integer(), Integer, None, None), (UUID(), UUID, None, None),
    (String(64), String, 64, None), (DateTime(timezone=True), DateTime, None, True),
    (TIMESTAMP(timezone=True), DateTime, None, True),
])
def test_structured_type_validation(actual, expected, length, timezone):
    assert migration._type_matches(actual, expected, length, timezone)


def test_create_path_isolated_to_challenge_table():
    connection = FakeConnection()
    migration._create_table(connection)
    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "CREATE TABLE windows_helper_challenges" in sql
    assert "windows_helper_credentials" not in sql
    assert "windows_helper_submissions" not in sql


def test_apply_acquires_lock_before_creation(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(migration, "_table_names", lambda _: {"devices", "sites", "schema_migrations"})
    columns = {
        "devices": [{"name": "id", "type": Integer(), "nullable": False}],
        "sites": [{"name": "id", "type": Integer(), "nullable": False}],
        "schema_migrations": [{"name": "migration_id", "type": String(255), "nullable": False}],
    }
    monkeypatch.setattr(migration, "inspect", lambda _: SimpleNamespace(
        get_pk_constraint=lambda table: {"constrained_columns": ["id" if table != "schema_migrations" else "migration_id"]},
        get_columns=lambda table: columns[table], get_unique_constraints=lambda table: [],
        get_foreign_keys=lambda table: [], get_indexes=lambda table: [],
    ))
    monkeypatch.setattr(migration, "_validate_created_schema", lambda _: None)

    class Engine:
        def begin(self):
            class Context:
                def __enter__(self): return connection
                def __exit__(self, *_): return False
            return Context()

    migration.apply_0076(Engine())
    lock_index = next(i for i, (sql, _) in enumerate(connection.statements) if "pg_advisory_xact_lock" in sql)
    create_index = next(i for i, (sql, _) in enumerate(connection.statements) if "CREATE TABLE" in sql)
    assert lock_index < create_index
    assert any("schema_migrations" in sql and "INSERT" in sql for sql, _ in connection.statements)


def test_applied_migration_is_rejected_explicitly(monkeypatch):
    connection = FakeConnection(applied=True)
    monkeypatch.setattr(migration, "_table_names", lambda _: {"devices", "sites", "schema_migrations", migration.CHALLENGE_TABLE})
    monkeypatch.setattr(migration, "_validate_parents", lambda _: None)
    monkeypatch.setattr(migration, "_validate_created_schema", lambda _: None)

    class Engine:
        def begin(self):
            class Context:
                def __enter__(self): return connection
                def __exit__(self, *_): return False
            return Context()

    with pytest.raises(RuntimeError, match="already applied"):
        migration.apply_0076(Engine())
