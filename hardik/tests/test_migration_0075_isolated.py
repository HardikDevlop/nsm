from types import SimpleNamespace

import pytest
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, JSON, SmallInteger, String
from sqlalchemy.dialects.postgresql import BOOLEAN, INTEGER, JSONB, TIMESTAMP, UUID

from backend.database import migrate_0075 as migration


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


def fake_inspector(_connection):
    return SimpleNamespace(
        get_table_names=lambda: {"devices", "sites", "schema_migrations"},
        get_pk_constraint=lambda table: {"constrained_columns": ["id" if table != "schema_migrations" else "migration_id"]},
        get_columns=lambda table: [],
        get_unique_constraints=lambda table: [],
        get_indexes=lambda table: [],
    )


def test_scope_and_registration_are_explicit():
    assert migration.MIGRATION_ID == "20261103_0075_windows_helper_authentication"
    assert migration.HELPER_TABLES == ("windows_helper_credentials", "windows_helper_submissions")


@pytest.mark.parametrize("actual, expected, length, timezone", [
    (String(16), String, 16, None), (String(64), String, 64, None),
    (Integer(), Integer, None, None), (INTEGER(), Integer, None, None), (BOOLEAN(), Boolean, None, None), (UUID(), UUID, None, None),
    (JSON(), JSON, None, None), (Boolean(), Boolean, None, None),
    (DateTime(), DateTime, None, False), (TIMESTAMP(), DateTime, None, False), (DateTime(timezone=True), DateTime, None, True), (TIMESTAMP(timezone=True), DateTime, None, True),
])
def test_structured_type_validation_accepts_expected_types(actual, expected, length, timezone):
    assert migration._type_matches(actual, expected, length, timezone)


def test_structured_type_validation_rejects_lengths_jsonb_and_timezone():
    assert not migration._type_matches(String(32), String, 16, None)
    assert not migration._type_matches(JSONB(), JSON, None, None)
    assert not migration._type_matches(DateTime(timezone=True), DateTime, None, False)
    assert not migration._type_matches(BigInteger(), Integer, None, None)
    assert not migration._type_matches(SmallInteger(), Integer, None, None)


def test_schema_validator_checks_foreign_keys_and_index_shape(monkeypatch):
    columns = {
        "windows_helper_credentials": [
            {"name": "id", "type": INTEGER(), "nullable": False, "default": "nextval('windows_helper_credentials_id_seq'::regclass)"}, {"name": "device_id", "type": INTEGER(), "nullable": False}, {"name": "site_id", "type": INTEGER(), "nullable": False},
            {"name": "token_prefix", "type": String(16), "nullable": False}, {"name": "token_hash", "type": String(64), "nullable": False},
            {"name": "created_at", "type": DateTime(), "nullable": False}, {"name": "expires_at", "type": DateTime(), "nullable": False},
            {"name": "revoked_at", "type": DateTime(), "nullable": True}, {"name": "last_used_at", "type": DateTime(), "nullable": True}, {"name": "is_active", "type": Boolean(), "nullable": False},
        ],
        "windows_helper_submissions": [
            {"name": "id", "type": INTEGER(), "nullable": False, "default": "nextval('windows_helper_submissions_id_seq'::regclass)"}, {"name": "collection_id", "type": UUID(), "nullable": False}, {"name": "device_id", "type": INTEGER(), "nullable": False}, {"name": "session_id", "type": INTEGER(), "nullable": False},
            {"name": "collected_at", "type": DateTime(timezone=True), "nullable": False}, {"name": "evidence", "type": JSON(), "nullable": False}, {"name": "expires_at", "type": DateTime(), "nullable": False}, {"name": "created_at", "type": DateTime(), "nullable": False},
        ],
    }
    indexes = {
        "windows_helper_credentials": [
            {"name": "ix_windows_helper_credentials_device_active", "column_names": ["device_id", "is_active"], "unique": False, "dialect_options": {}},
            {"name": "ix_windows_helper_credentials_site_id", "column_names": ["site_id"], "unique": False, "dialect_options": {}},
            {"name": "ix_windows_helper_credentials_expires_at", "column_names": ["expires_at"], "unique": False, "dialect_options": {}},
        ],
        "windows_helper_submissions": [
            {"name": "ix_windows_helper_submissions_device_id", "column_names": ["device_id"], "unique": False, "dialect_options": {}},
            {"name": "ix_windows_helper_submission_expiry", "column_names": ["expires_at"], "unique": False, "dialect_options": {}},
        ],
    }
    fks = {
        "windows_helper_credentials": [{"constrained_columns": ["device_id"], "referred_table": "devices", "referred_columns": ["id"], "options": {"ondelete": "CASCADE"}}, {"constrained_columns": ["site_id"], "referred_table": "sites", "referred_columns": ["id"], "options": {"ondelete": "CASCADE"}}],
        "windows_helper_submissions": [{"constrained_columns": ["device_id"], "referred_table": "devices", "referred_columns": ["id"], "options": {"ondelete": "CASCADE"}}],
    }
    class Inspector:
        def get_columns(self, table): return columns[table]
        def get_pk_constraint(self, table): return {"constrained_columns": ["id"]}
        def get_unique_constraints(self, table): return [{"column_names": ["token_prefix"]}] if table.endswith("credentials") else [{"column_names": ["collection_id"]}]
        def get_foreign_keys(self, table): return fks[table]
        def get_indexes(self, table): return indexes[table]
    monkeypatch.setattr(migration, "inspect", lambda _: Inspector())
    migration._validate_created_schema(FakeConnection())
    indexes["windows_helper_credentials"][0]["column_names"] = ["site_id", "device_id"]
    with pytest.raises(RuntimeError, match="index"):
        migration._validate_created_schema(FakeConnection())


def test_partial_schema_is_rejected(monkeypatch):
    monkeypatch.setattr(migration, "_table_names", lambda _: {"devices", "sites", "schema_migrations", "windows_helper_credentials"})
    with pytest.raises(RuntimeError, match="partial"):
        migration._validate_existing_or_absent(FakeConnection(), applied=False)


def test_missing_parent_is_rejected(monkeypatch):
    monkeypatch.setattr(migration, "_table_names", lambda _: {"sites", "schema_migrations"})
    monkeypatch.setattr(migration, "inspect", fake_inspector)
    with pytest.raises(RuntimeError, match="missing"):
        migration._validate_parents(FakeConnection())


def test_create_path_contains_only_helper_tables_and_indexes(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(migration, "_table_names", lambda _: {"devices", "sites", "schema_migrations"})
    migration._create_tables(connection)
    sql = "\n".join(statement for statement, _ in connection.statements)
    assert "CREATE TABLE windows_helper_credentials" in sql
    assert "CREATE TABLE windows_helper_submissions" in sql
    assert "windows_process_snapshots" not in sql
    assert "windows_credentials" not in sql


def test_apply_acquires_advisory_lock_before_schema_work(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setattr(migration, "_table_names", lambda _: {"devices", "sites", "schema_migrations"})
    monkeypatch.setattr(migration, "inspect", fake_inspector)
    monkeypatch.setattr(migration, "_validate_created_schema", lambda _: None)
    class Engine:
        def begin(self):
            class Context:
                def __enter__(self): return connection
                def __exit__(self, *_): return False
            return Context()
    migration.apply_0075(Engine())
    lock_index = next(i for i, (sql, _) in enumerate(connection.statements) if "pg_advisory_xact_lock" in sql)
    create_index = next(i for i, (sql, _) in enumerate(connection.statements) if "CREATE TABLE" in sql)
    assert lock_index < create_index
    assert any("schema_migrations" in sql and "INSERT" in sql for sql, _ in connection.statements)
