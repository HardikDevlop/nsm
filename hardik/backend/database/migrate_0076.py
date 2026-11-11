"""Isolated, opt-in migration for durable Windows helper challenges.

Importing this module is side-effect free. The command is read-only by default;
schema creation requires ``--apply`` and an exact database-name confirmation.
It is intentionally not registered with application startup migrations.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Integer, SmallInteger, String, create_engine, inspect, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.engine import Connection, Engine

MIGRATION_ID = "20261104_0076_windows_helper_challenges"
DESCRIPTION = "Create durable device-bound Windows helper challenge state"
LOCK_KEY = "agnigate:nms:migration:" + MIGRATION_ID
CHALLENGE_TABLE = "windows_helper_challenges"
REQUIRED_PARENTS = {"devices": "id", "sites": "id", "schema_migrations": "migration_id"}

EXPECTED = {
    "id": (Integer, None, False),
    "challenge_id": (UUID, None, False),
    "device_id": (Integer, None, False),
    "site_id": (Integer, None, False),
    "collection_id": (UUID, None, False),
    "purpose": (String, 64, False),
    "nonce_hash": (String, 64, False),
    "issued_at": (DateTime, True, False),
    "expires_at": (DateTime, True, False),
    "consumed_at": (DateTime, True, True),
    "cancelled_at": (DateTime, True, True),
}


def _type_matches(actual: Any, expected: type, length: int | None, timezone: bool | None) -> bool:
    if expected is String:
        return isinstance(actual, String) and actual.length == length
    if expected is Integer:
        return isinstance(actual, Integer)
    if expected is UUID:
        return isinstance(actual, UUID)
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
        reflected = next((item for item in inspector.get_columns(table) if item["name"] == column), None)
        actual_type = reflected["type"] if reflected is not None else None
        if table in {"devices", "sites"}:
            valid_type = isinstance(actual_type, Integer) and not isinstance(actual_type, (BigInteger, SmallInteger))
            expected_type = "INTEGER"
        else:
            valid_type = isinstance(actual_type, String) and actual_type.length == 255
            expected_type = "VARCHAR(255)"
        if not valid_type:
            raise RuntimeError(
                f"{table}.{column} has incompatible primary-key type: "
                f"expected {expected_type}, got {actual_type!s}"
            )


def _migration_applied(connection: Connection) -> bool:
    return connection.execute(
        text("SELECT 1 FROM schema_migrations WHERE migration_id = :id"),
        {"id": MIGRATION_ID},
    ).first() is not None


def _validate_existing_or_absent(connection: Connection, *, applied: bool) -> None:
    present = CHALLENGE_TABLE in _table_names(connection)
    if not applied and present:
        raise RuntimeError(f"partial or unexpected challenge schema exists: {CHALLENGE_TABLE}")
    if applied and not present:
        raise RuntimeError(f"{MIGRATION_ID} is recorded but {CHALLENGE_TABLE} is missing")


def _create_table(connection: Connection) -> None:
    connection.execute(text(f"""
        CREATE TABLE {CHALLENGE_TABLE} (
            id SERIAL PRIMARY KEY,
            challenge_id UUID NOT NULL,
            device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
            collection_id UUID NOT NULL,
            purpose VARCHAR(64) NOT NULL,
            nonce_hash VARCHAR(64) NOT NULL,
            issued_at TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            consumed_at TIMESTAMPTZ,
            cancelled_at TIMESTAMPTZ,
            CONSTRAINT uq_windows_helper_challenges_id UNIQUE (challenge_id),
            CONSTRAINT uq_windows_helper_challenges_device_collection UNIQUE (device_id, collection_id)
        )
    """))
    connection.execute(text(f"CREATE INDEX ix_windows_helper_challenges_device_expiry ON {CHALLENGE_TABLE} (device_id, expires_at)"))
    connection.execute(text(f"CREATE INDEX ix_windows_helper_challenges_collection ON {CHALLENGE_TABLE} (collection_id)"))


def _validate_created_schema(connection: Connection) -> None:
    inspector = inspect(connection)
    actual = {c["name"]: (c["type"], c["nullable"]) for c in inspector.get_columns(CHALLENGE_TABLE)}
    for column, (kind, length, nullable) in EXPECTED.items():
        if column not in actual:
            raise RuntimeError(f"schema mismatch: table={CHALLENGE_TABLE} column={column} condition=missing_column")
        actual_type, actual_nullable = actual[column]
        expected_timezone = length if kind is DateTime else None
        if actual_nullable != nullable or not _type_matches(actual_type, kind, length if kind is not DateTime else None, expected_timezone):
            raise RuntimeError(
                f"schema mismatch: table={CHALLENGE_TABLE} column={column} "
                f"expected_type={kind.__name__} actual_type={actual_type} "
                f"expected_nullable={nullable} actual_nullable={actual_nullable}"
            )
    pk = inspector.get_pk_constraint(CHALLENGE_TABLE).get("constrained_columns") or []
    if pk != ["id"]:
        raise RuntimeError(f"schema mismatch: table={CHALLENGE_TABLE} expected primary key id")
    uniques = {tuple(item.get("column_names") or []) for item in inspector.get_unique_constraints(CHALLENGE_TABLE)}
    required_uniques = {("challenge_id",), ("device_id", "collection_id")}
    if not required_uniques <= uniques:
        raise RuntimeError(f"schema mismatch: missing unique constraints on {CHALLENGE_TABLE}")
    foreign_keys = {
        (fk["constrained_columns"][0], fk["referred_table"], fk["referred_columns"][0], (fk.get("options") or {}).get("ondelete", "").upper())
        for fk in inspector.get_foreign_keys(CHALLENGE_TABLE)
        if fk.get("constrained_columns") and fk.get("referred_columns")
    }
    required_fks = {
        ("device_id", "devices", "id", "CASCADE"),
        ("site_id", "sites", "id", "CASCADE"),
    }
    if not required_fks <= foreign_keys:
        raise RuntimeError(f"schema mismatch: missing foreign keys on {CHALLENGE_TABLE}")
    indexes = {item.get("name") for item in inspector.get_indexes(CHALLENGE_TABLE)}
    required_indexes = {"ix_windows_helper_challenges_device_expiry", "ix_windows_helper_challenges_collection"}
    if not required_indexes <= indexes:
        raise RuntimeError(f"schema mismatch: missing indexes on {CHALLENGE_TABLE}")


def inspect_0076(engine: Engine) -> dict[str, Any]:
    """Read-only validation; does not create tables or record migration."""
    with engine.connect() as connection:
        _validate_parents(connection)
        applied = _migration_applied(connection)
        _validate_existing_or_absent(connection, applied=applied)
        if applied:
            _validate_created_schema(connection)
        return {
            "migration_id": MIGRATION_ID,
            "database": connection.engine.url.database,
            "applied": applied,
            "challenge_table_present": CHALLENGE_TABLE in _table_names(connection),
            "ready": not applied,
        }


def apply_0076(engine: Engine) -> None:
    """Apply 0076 atomically under a transaction-scoped advisory lock."""
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": LOCK_KEY})
        _validate_parents(connection)
        applied = _migration_applied(connection)
        _validate_existing_or_absent(connection, applied=applied)
        if applied:
            _validate_created_schema(connection)
            raise RuntimeError(f"{MIGRATION_ID} is already applied")
        _create_table(connection)
        _validate_created_schema(connection)
        connection.execute(
            text("INSERT INTO schema_migrations (migration_id, description, applied_at) VALUES (:id, :description, :applied_at)"),
            {"id": MIGRATION_ID, "description": DESCRIPTION, "applied_at": datetime.now()},
        )


def _engine_from_settings():
    from backend.config.settings import get_settings
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare/apply only Windows helper challenge migration 0076")
    parser.add_argument("--apply", action="store_true", help="apply migration; without this flag the command is read-only")
    parser.add_argument("--confirm-database", metavar="NAME", help="required with --apply; exact database name confirmation")
    args = parser.parse_args(argv)
    engine = _engine_from_settings()
    target = engine.url.database
    if args.apply:
        if args.confirm_database != target:
            raise SystemExit("refusing apply: --confirm-database must exactly match the configured database name")
        apply_0076(engine)
        print(f"Applied {MIGRATION_ID} to database {target}")
    else:
        print(inspect_0076(engine))
        print("Dry-run only; no schema or migration changes were made.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
