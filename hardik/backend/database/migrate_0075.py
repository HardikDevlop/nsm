"""Isolated, opt-in migration runner for Windows helper authentication.

This module is intentionally separate from ``backend.init_db``. Importing it
does not connect to PostgreSQL or execute anything. CLI default is dry-run.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, JSON, SmallInteger, String, create_engine, inspect, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.engine import Connection, Engine

MIGRATION_ID = "20261103_0075_windows_helper_authentication"
DESCRIPTION = "Create device-bound Windows helper credentials and replay records"
LOCK_KEY = "agnigate:nms:migration:" + MIGRATION_ID
REQUIRED_PARENTS = {"devices": "id", "sites": "id", "schema_migrations": "migration_id"}
HELPER_TABLES = ("windows_helper_credentials", "windows_helper_submissions")

EXPECTED = {
    "windows_helper_credentials": {
        "id": (Integer, None, False), "device_id": (Integer, None, False), "site_id": (Integer, None, False),
        "token_prefix": (String, 16, False), "token_hash": (String, 64, False),
        "created_at": (DateTime, False, False), "expires_at": (DateTime, False, False),
        "revoked_at": (DateTime, False, True), "last_used_at": (DateTime, False, True),
        "is_active": (Boolean, None, False),
    },
    "windows_helper_submissions": {
        "id": (Integer, None, False), "collection_id": (UUID, None, False), "device_id": (Integer, None, False),
        "session_id": (Integer, None, False), "collected_at": (DateTime, True, False),
        "evidence": (JSON, None, False), "expires_at": (DateTime, False, False),
        "created_at": (DateTime, False, False),
    },
}

def _type_matches(actual: Any, expected: type, length: int | None, timezone: bool | None) -> bool:
    """Compare reflected SQLAlchemy types structurally, not by display string."""
    if expected is String:
        return isinstance(actual, String) and not isinstance(actual, (JSON, JSONB)) and actual.length == length
    if expected is Integer:
        return isinstance(actual, Integer) and not isinstance(actual, (BigInteger, SmallInteger))
    if expected is Boolean:
        return isinstance(actual, Boolean)
    if expected is UUID:
        return isinstance(actual, UUID)
    if expected is JSON:
        return isinstance(actual, JSON) and not isinstance(actual, JSONB)
    if expected is DateTime:
        return isinstance(actual, DateTime) and actual.timezone is timezone
    return False

def _table_names(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names())

def _validate_parents(connection: Connection) -> None:
    names = _table_names(connection)
    missing = sorted(set(REQUIRED_PARENTS) - names)
    if missing:
        raise RuntimeError(f"required parent tables are missing: {', '.join(missing)}")
    inspector = inspect(connection)
    for table, column in REQUIRED_PARENTS.items():
        pk = inspector.get_pk_constraint(table).get("constrained_columns") or []
        if pk != [column]:
            raise RuntimeError(f"{table}.{column} is not the expected single-column primary key")

def _migration_applied(connection: Connection) -> bool:
    return connection.execute(text("SELECT 1 FROM schema_migrations WHERE migration_id = :id"), {"id": MIGRATION_ID}).first() is not None

def _validate_existing_or_absent(connection: Connection, *, applied: bool) -> None:
    names = _table_names(connection)
    present = [name for name in HELPER_TABLES if name in names]
    if not applied and present:
        raise RuntimeError(f"partial or unexpected helper schema exists: {', '.join(present)}")
    if applied and set(present) != set(HELPER_TABLES):
        raise RuntimeError("0075 is recorded but one or more required helper tables are missing")

def _create_tables(connection: Connection) -> None:
    connection.execute(text("""
        CREATE TABLE windows_helper_credentials (
            id SERIAL PRIMARY KEY,
            device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
            token_prefix VARCHAR(16) NOT NULL,
            token_hash VARCHAR(64) NOT NULL,
            created_at TIMESTAMP NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            revoked_at TIMESTAMP,
            last_used_at TIMESTAMP,
            is_active BOOLEAN NOT NULL,
            CONSTRAINT uq_windows_helper_credentials_prefix UNIQUE (token_prefix)
        )
    """))
    connection.execute(text("""
        CREATE TABLE windows_helper_submissions (
            id SERIAL PRIMARY KEY,
            collection_id UUID NOT NULL,
            device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            session_id INTEGER NOT NULL,
            collected_at TIMESTAMPTZ NOT NULL,
            evidence JSON NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP NOT NULL,
            CONSTRAINT uq_windows_helper_submission_collection UNIQUE (collection_id)
        )
    """))
    connection.execute(text("CREATE INDEX ix_windows_helper_credentials_device_active ON windows_helper_credentials (device_id, is_active)"))
    connection.execute(text("CREATE INDEX ix_windows_helper_credentials_site_id ON windows_helper_credentials (site_id)"))
    connection.execute(text("CREATE INDEX ix_windows_helper_credentials_expires_at ON windows_helper_credentials (expires_at)"))
    connection.execute(text("CREATE INDEX ix_windows_helper_submissions_device_id ON windows_helper_submissions (device_id)"))
    connection.execute(text("CREATE INDEX ix_windows_helper_submission_expiry ON windows_helper_submissions (expires_at)"))

def _validate_created_schema(connection: Connection) -> None:
    inspector = inspect(connection)
    for table, expected in EXPECTED.items():
        actual = {c["name"]: (c["type"], c["nullable"]) for c in inspector.get_columns(table)}
        for column, (kind, *spec) in expected.items():
            length = spec[0] if kind is String else None
            timezone = spec[0] if kind is DateTime else None
            nullable = spec[-1]
            if column not in actual:
                raise RuntimeError(f"schema mismatch: table={table} column={column} expected_type={kind.__name__} actual_type=<missing> expected_nullable={nullable} actual_nullable=<missing> condition=missing_column")
            actual_type, actual_nullable = actual[column]
            if actual_nullable != nullable:
                raise RuntimeError(f"schema mismatch: table={table} column={column} expected_type={kind.__name__} actual_type={actual_type} expected_nullable={nullable} actual_nullable={actual_nullable} condition=nullability")
            if not _type_matches(actual_type, kind, length, timezone):
                expected_label = kind.__name__ + (f"({length})" if length is not None else (f"(timezone={timezone})" if kind is DateTime else ""))
                raise RuntimeError(f"schema mismatch: table={table} column={column} expected_type={expected_label} actual_type={actual_type} expected_nullable={nullable} actual_nullable={actual_nullable} condition=type")
    for table in HELPER_TABLES:
        pk = inspector.get_pk_constraint(table).get("constrained_columns") or []
        if pk != ["id"]:
            raise RuntimeError(f"schema mismatch: table={table} column=id expected_type=Integer actual_type=<unknown> expected_nullable=False actual_nullable=<unknown> condition=primary_key")
        id_column = next((c for c in inspector.get_columns(table) if c["name"] == "id"), None)
        if id_column is None or not _type_matches(id_column["type"], Integer, None, None) or id_column.get("nullable") is not False:
            raise RuntimeError(f"schema mismatch: table={table} column=id expected_type=Integer actual_type={id_column.get('type') if id_column else '<missing>'} expected_nullable=False actual_nullable={id_column.get('nullable') if id_column else '<missing>'} condition=primary_key_column")
        default = id_column.get("default")
        identity = id_column.get("identity")
        if not identity and not (isinstance(default, str) and "nextval(" in default.lower()):
            raise RuntimeError(f"schema mismatch: table={table} column=id expected_type=Integer actual_type={id_column['type']} expected_nullable=False actual_nullable=False condition=missing_sequence_or_identity")
    for table, column in (("windows_helper_credentials", "token_prefix"), ("windows_helper_submissions", "collection_id")):
        uniques = inspector.get_unique_constraints(table)
        if not any(u.get("column_names") == [column] for u in uniques):
            raise RuntimeError(f"missing unique constraint for {table}.{column}")
    foreign_keys = {
        (table, fk["constrained_columns"][0], fk["referred_table"], fk["referred_columns"][0], (fk.get("options") or {}).get("ondelete", "").upper())
        for table in HELPER_TABLES for fk in inspector.get_foreign_keys(table)
        if fk.get("constrained_columns") and fk.get("referred_columns")
    }
    required_foreign_keys = {
        ("windows_helper_credentials", "device_id", "devices", "id", "CASCADE"),
        ("windows_helper_credentials", "site_id", "sites", "id", "CASCADE"),
        ("windows_helper_submissions", "device_id", "devices", "id", "CASCADE"),
    }
    if not required_foreign_keys <= foreign_keys:
        raise RuntimeError("required helper foreign keys are missing")
    indexes = {i["name"] for table in HELPER_TABLES for i in inspector.get_indexes(table)}
    required = {
        "ix_windows_helper_credentials_device_active": ("windows_helper_credentials", ["device_id", "is_active"], False),
        "ix_windows_helper_credentials_site_id": ("windows_helper_credentials", ["site_id"], False),
        "ix_windows_helper_credentials_expires_at": ("windows_helper_credentials", ["expires_at"], False),
        "ix_windows_helper_submissions_device_id": ("windows_helper_submissions", ["device_id"], False),
        "ix_windows_helper_submission_expiry": ("windows_helper_submissions", ["expires_at"], False),
    }
    for name, (table, columns, unique) in required.items():
        found = next((item for item in inspector.get_indexes(table) if item.get("name") == name), None)
        options = (found or {}).get("dialect_options") or {}
        if found is None or found.get("column_names") != columns or bool(found.get("unique")) != unique or options.get("postgresql_where") is not None:
            raise RuntimeError(f"incompatible or missing index: {name}")

def inspect_0075(engine: Engine) -> dict[str, Any]:
    """Read-only validation; does not create tables or record migration."""
    with engine.connect() as connection:
        _validate_parents(connection)
        applied = _migration_applied(connection)
        _validate_existing_or_absent(connection, applied=applied)
        if applied:
            _validate_created_schema(connection)
        return {"migration_id": MIGRATION_ID, "database": connection.engine.url.database, "applied": applied, "helper_tables_present": sorted(set(HELPER_TABLES) & _table_names(connection)), "ready": not applied}

def apply_0075(engine: Engine) -> None:
    """Apply 0075 atomically under a transaction-scoped advisory lock."""
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": LOCK_KEY})
        _validate_parents(connection)
        applied = _migration_applied(connection)
        _validate_existing_or_absent(connection, applied=applied)
        if applied:
            _validate_created_schema(connection)
            raise RuntimeError(f"{MIGRATION_ID} is already applied")
        _create_tables(connection)
        _validate_created_schema(connection)
        connection.execute(text("INSERT INTO schema_migrations (migration_id, description, applied_at) VALUES (:id, :description, :applied_at)"), {"id": MIGRATION_ID, "description": DESCRIPTION, "applied_at": datetime.now()})

def _engine_from_settings():
    from backend.config.settings import get_settings
    return create_engine(get_settings().database_url, pool_pre_ping=True)

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare/apply only Windows helper migration 0075")
    parser.add_argument("--apply", action="store_true", help="apply migration; without this flag the command is read-only")
    parser.add_argument("--confirm-database", metavar="NAME", help="required with --apply; exact database name confirmation")
    args = parser.parse_args(argv)
    engine = _engine_from_settings()
    target = engine.url.database
    if args.apply:
        if args.confirm_database != target:
            raise SystemExit("refusing apply: --confirm-database must exactly match the configured database name")
        apply_0075(engine)
        print(f"Applied {MIGRATION_ID} to database {target}")
    else:
        print(inspect_0075(engine))
        print("Dry-run only; no schema or migration changes were made.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
