"""Isolated opt-in migration for Windows process collection lifecycle state."""
from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, create_engine, inspect, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.engine import Connection, Engine

MIGRATION_ID = "20261104_0077_windows_process_collection_lifecycle"
DESCRIPTION = "Create durable Windows process collection lifecycle state"
LOCK_KEY = "agnigate:nms:migration:" + MIGRATION_ID
TABLE = "windows_process_collections"
PARENTS = {"devices": "id", "sites": "id", "schema_migrations": "migration_id"}


def _tables(connection): return set(inspect(connection).get_table_names())


def _parents(connection):
    names = _tables(connection)
    missing = sorted(set(PARENTS) - names)
    if missing: raise RuntimeError(f"required parent tables are missing: {', '.join(missing)}")
    inspector = inspect(connection)
    for table, column in PARENTS.items():
        if inspector.get_pk_constraint(table).get("constrained_columns") != [column]:
            raise RuntimeError(f"{table}.{column} is not the expected primary key")


def _applied(connection):
    return connection.execute(text("SELECT 1 FROM schema_migrations WHERE migration_id = :id"), {"id": MIGRATION_ID}).first() is not None


def _create(connection):
    connection.execute(text(f"""
        CREATE TABLE {TABLE} (
            id SERIAL PRIMARY KEY,
            collection_id UUID NOT NULL,
            device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
            site_id INTEGER NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
            state VARCHAR(16) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL,
            started_at TIMESTAMPTZ,
            finalized_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL,
            CONSTRAINT uq_windows_process_collections_collection UNIQUE (collection_id),
            CONSTRAINT ck_windows_process_collections_state CHECK (state IN ('RESERVED','COLLECTING','FINALIZED','FAILED','SUPERSEDED','EXPIRED'))
        )
    """))
    connection.execute(text(f"CREATE INDEX ix_windows_process_collections_device_state ON {TABLE} (device_id, state)"))
    connection.execute(text(f"CREATE INDEX ix_windows_process_collections_expiry ON {TABLE} (expires_at)"))


def _validate(connection):
    inspector = inspect(connection)
    columns = {item["name"] for item in inspector.get_columns(TABLE)}
    expected = {"id", "collection_id", "device_id", "site_id", "state", "created_at", "started_at", "finalized_at", "expires_at", "updated_at"}
    if columns != expected: raise RuntimeError(f"schema mismatch for {TABLE}")
    if inspector.get_pk_constraint(TABLE).get("constrained_columns") != ["id"]: raise RuntimeError(f"schema mismatch: {TABLE} primary key")
    uniques = {tuple(item.get("column_names") or []) for item in inspector.get_unique_constraints(TABLE)}
    if ("collection_id",) not in uniques: raise RuntimeError(f"schema mismatch: {TABLE} collection uniqueness")
    fks = {(fk["constrained_columns"][0], fk["referred_table"], (fk.get("options") or {}).get("ondelete", "").upper()) for fk in inspector.get_foreign_keys(TABLE)}
    if {("device_id", "devices", "CASCADE"), ("site_id", "sites", "CASCADE")} - fks: raise RuntimeError(f"schema mismatch: {TABLE} foreign keys")
    indexes = {item.get("name") for item in inspector.get_indexes(TABLE)}
    if {"ix_windows_process_collections_device_state", "ix_windows_process_collections_expiry"} - indexes: raise RuntimeError(f"schema mismatch: {TABLE} indexes")


def inspect_0077(engine: Engine) -> dict[str, Any]:
    with engine.connect() as connection:
        _parents(connection); applied = _applied(connection)
        if applied: _validate(connection)
        return {"migration_id": MIGRATION_ID, "applied": applied, "table_present": TABLE in _tables(connection), "ready": not applied}


def apply_0077(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": LOCK_KEY})
        _parents(connection)
        if _applied(connection):
            _validate(connection)
            raise RuntimeError(f"{MIGRATION_ID} is already applied")
        if TABLE in _tables(connection): raise RuntimeError(f"partial or unexpected schema exists: {TABLE}")
        _create(connection); _validate(connection)
        connection.execute(text("INSERT INTO schema_migrations (migration_id, description, applied_at) VALUES (:id, :description, :at)"), {"id": MIGRATION_ID, "description": DESCRIPTION, "at": datetime.now()})


def _engine_from_settings():
    from backend.config.settings import get_settings
    return create_engine(get_settings().database_url, pool_pre_ping=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Apply only Windows lifecycle migration 0077")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-database")
    args = parser.parse_args(argv); engine = _engine_from_settings(); target = engine.url.database
    if args.apply:
        if args.confirm_database != target: raise SystemExit("refusing apply: exact database confirmation required")
        apply_0077(engine); print(f"Applied {MIGRATION_ID} to database {target}")
    else: print(inspect_0077(engine)); print("Dry-run only; no schema or migration changes were made.")
    return 0


if __name__ == "__main__": raise SystemExit(main())
