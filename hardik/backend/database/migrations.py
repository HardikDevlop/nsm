from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from backend.database.session import Base


def _now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)


@dataclass(frozen=True)
class Migration:
    migration_id: str
    description: str


PERFORMANCE_INDEXES: dict[str, tuple[str, tuple[str, ...]]] = {
    "ix_devices_deleted_status": ("devices", ('"deleted_at"', '"status"')),
    "ix_devices_deleted_site": ("devices", ('"deleted_at"', '"site_id"')),
    "ix_device_credentials_device_id": ("device_credentials", ('"device_id"',)),
    "ix_interfaces_device_status": ("interfaces", ('"device_id"', '"status"')),
    "ix_interfaces_device_updated": ("interfaces", ('"device_id"', '"last_updated"')),
    "ix_monitoring_jobs_device_status": ("monitoring_jobs", ('"device_id"', '"status"')),
    "ix_device_metrics_device_created_at": ("device_metrics", ('"device_id"', '"created_at"')),
    "ix_alerts_deleted_status_created_at": ("alerts", ('"deleted_at"', '"status"', '"created_at"')),
    "ix_alerts_device_status_created_at": ("alerts", ('"device_id"', '"status"', '"created_at"')),
    "ix_events_deleted_timestamp": ("events", ('"deleted_at"', '"timestamp"')),
    "ix_events_device_timestamp": ("events", ('"device_id"', '"timestamp"')),
    "ix_audit_logs_user_timestamp": ("audit_logs", ('"user_id"', '"timestamp"')),
    "ix_device_status_history_device_timestamp": ("device_status_history", ('"device_id"', '"timestamp"')),
    "ix_polling_history_device_created_at": ("polling_history", ('"device_id"', '"created_at"')),
    "ix_polling_history_device_status_created_at": ("polling_history", ('"device_id"', '"status"', '"created_at"')),
    "ix_interface_statistics_device_created_at": ("interface_statistics", ('"device_id"', '"created_at"')),
    "ix_interface_statistics_interface_created_at": ("interface_statistics", ('"interface_id"', '"created_at"')),
    "ix_latest_interface_device_oper_status": ("latest_interface", ('"device_id"', '"oper_status"')),
}

DEVICE_CREDENTIAL_COLUMNS: dict[str, str] = {
    "snmp_version": "VARCHAR(20)",
    "community_string": "TEXT",
    "username": "VARCHAR(120)",
    "password": "TEXT",
    "auth_protocol": "VARCHAR(20)",
    "auth_password": "TEXT",
    "privacy_protocol": "VARCHAR(20)",
    "privacy_password": "TEXT",
    "security_level": "VARCHAR(30)",
    "ssh_port": "INTEGER",
    "api_token": "TEXT",
}

MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        migration_id="20260821_0001_device_credentials_columns",
        description="Ensure device_credentials contains all SNMP/auth fields",
    ),
    Migration(
        migration_id="20260821_0002_performance_indexes",
        description="Create composite indexes for hot dashboard and monitoring queries",
    ),
    Migration(
        migration_id="20260821_0003_device_types_metadata",
        description="Ensure device_types contains description and created_at metadata",
    ),
    Migration(
        migration_id="20260821_0004_device_topology_metadata",
        description="Store manually corrected topology fields on devices",
    ),
    Migration(
        migration_id="20260825_0005_linux_server_monitoring_foundation",
        description="Create isolated Linux Server Monitoring foundation tables",
    ),
    Migration(
        migration_id="20260825_0006_linux_server_inventory",
        description="Add isolated Linux server detected interface and disk inventory tables",
    ),
    Migration(
        migration_id="20260825_0007_linux_server_metric_columns",
        description="Add isolated Linux metric rate and utilization columns",
    ),
    Migration(
        migration_id="20260825_0008_linux_security_events",
        description="Create isolated Linux firewall and security event table",
    ),
    Migration(
        migration_id="20260825_0009_linux_monitoring_scheduler",
        description="Add isolated Linux scheduler credentials and durable monitoring state",
    ),
    Migration(
        migration_id="20260825_0010_linux_metric_retention",
        description="Add isolated current metrics table and indexed 24-hour history cleanup indexes",
    ),
)


def _ensure_migration_table(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    migration_id VARCHAR(120) PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at TIMESTAMP NOT NULL
                )
                """
            )
        )


def _applied_migrations(engine: Engine) -> set[str]:
    _ensure_migration_table(engine)
    with engine.begin() as connection:
        rows = connection.execute(text("SELECT migration_id FROM schema_migrations")).fetchall()
    return {row[0] for row in rows}


def _record_migration(engine: Engine, migration: Migration) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO schema_migrations (migration_id, description, applied_at)
                VALUES (:migration_id, :description, :applied_at)
                ON CONFLICT (migration_id) DO NOTHING
                """
            ),
            {
                "migration_id": migration.migration_id,
                "description": migration.description,
                "applied_at": _now(),
            },
        )


def _ensure_device_credential_columns(engine: Engine) -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "device_credentials" not in inspector.get_table_names():
            return
        present = {column["name"] for column in inspector.get_columns("device_credentials")}
        for name, sql_type in DEVICE_CREDENTIAL_COLUMNS.items():
            if name not in present:
                connection.execute(text(f'ALTER TABLE device_credentials ADD COLUMN "{name}" {sql_type}'))


def _ensure_performance_indexes(engine: Engine) -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        present_tables = set(inspector.get_table_names())
        present_indexes = {
            table: {index["name"] for index in inspector.get_indexes(table)}
            for table in present_tables
        }
        for index_name, (table_name, columns) in PERFORMANCE_INDEXES.items():
            if table_name not in present_tables:
                continue
            if index_name in present_indexes.get(table_name, set()):
                continue
            column_sql = ", ".join(columns)
            connection.execute(
                text(f'CREATE INDEX IF NOT EXISTS "{index_name}" ON "{table_name}" ({column_sql})')
            )


def _ensure_device_type_columns(engine: Engine) -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "device_types" not in inspector.get_table_names():
            return
        present = {column["name"] for column in inspector.get_columns("device_types")}
        if "description" not in present:
            connection.execute(text('ALTER TABLE device_types ADD COLUMN "description" TEXT'))
        if "created_at" not in present:
            connection.execute(text('ALTER TABLE device_types ADD COLUMN "created_at" TIMESTAMP'))
            connection.execute(
                text('UPDATE device_types SET "created_at" = :now WHERE "created_at" IS NULL'),
                {"now": _now()},
            )
            connection.execute(text('ALTER TABLE device_types ALTER COLUMN "created_at" SET NOT NULL'))


def _ensure_device_topology_metadata(engine: Engine) -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "devices" not in inspector.get_table_names():
            return
        present = {column["name"] for column in inspector.get_columns("devices")}
        if "topology_metadata" not in present:
            connection.execute(text('ALTER TABLE devices ADD COLUMN "topology_metadata" JSON'))


def _ensure_linux_server_monitoring_tables(engine: Engine) -> None:
    from backend.linux_monitoring.models import LINUX_MONITORING_TABLES

    # Table-level checkfirst is not enough for PostgreSQL when an existing
    # table's indexes were created by an earlier run. Create only missing
    # tables so startup never issues duplicate CREATE INDEX statements.
    present_tables = set(inspect(engine).get_table_names())
    for table in LINUX_MONITORING_TABLES:
        if table.name not in present_tables:
            table.create(bind=engine)


def _ensure_linux_metric_columns(engine: Engine) -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "linux_server_metric_samples" not in inspector.get_table_names():
            return
        present = {column["name"] for column in inspector.get_columns("linux_server_metric_samples")}
        columns = {
            "swap_percent": "DOUBLE PRECISION",
            "disk_io_read_bytes_per_sec": "DOUBLE PRECISION",
            "disk_io_write_bytes_per_sec": "DOUBLE PRECISION",
            "load_5m": "DOUBLE PRECISION",
            "load_15m": "DOUBLE PRECISION",
            "uptime_seconds": "DOUBLE PRECISION",
            "network_rx_bytes_per_sec": "DOUBLE PRECISION",
            "network_tx_bytes_per_sec": "DOUBLE PRECISION",
            "packets_per_sec": "DOUBLE PRECISION",
            "interface_errors": "DOUBLE PRECISION",
            "interface_drops": "DOUBLE PRECISION",
        }
        for name, sql_type in columns.items():
            if name not in present:
                connection.execute(text(f'ALTER TABLE linux_server_metric_samples ADD COLUMN "{name}" {sql_type}'))


def _ensure_linux_scheduler_columns(engine: Engine) -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "linux_server_monitoring_configs" not in inspector.get_table_names():
            return
        present = {column["name"] for column in inspector.get_columns("linux_server_monitoring_configs")}
        columns = {
            "monitoring_status": "VARCHAR(20) NOT NULL DEFAULT 'stopped'",
            "last_run_at": "TIMESTAMP",
            "last_success_at": "TIMESTAMP",
            "last_started_at": "TIMESTAMP",
            "last_stopped_at": "TIMESTAMP",
            "last_error": "TEXT",
        }
        for name, sql_type in columns.items():
            if name not in present:
                connection.execute(text(f'ALTER TABLE linux_server_monitoring_configs ADD COLUMN "{name}" {sql_type}'))
        connection.execute(text('ALTER TABLE linux_server_monitoring_configs ALTER COLUMN "interval_seconds" SET DEFAULT 300'))
        connection.execute(text('UPDATE linux_server_monitoring_configs SET "interval_seconds" = 300'))


def _ensure_linux_metric_retention(engine: Engine) -> None:
    _ensure_linux_server_monitoring_tables(engine)
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE INDEX IF NOT EXISTS "ix_linux_server_metric_samples_retention_collected" '
            'ON "linux_server_metric_samples" ("collected_at", "id")'
        ))
        connection.execute(text(
            'CREATE INDEX IF NOT EXISTS "ix_linux_security_events_retention_timestamp" '
            'ON "linux_security_events" ("event_timestamp", "id")'
        ))


def run_migrations(engine: Engine) -> list[str]:
    """Run idempotent application-managed migrations and return applied ids."""
    applied = _applied_migrations(engine)
    newly_applied: list[str] = []

    for migration in MIGRATIONS:
        if migration.migration_id in applied:
            continue
        if migration.migration_id == "20260821_0001_device_credentials_columns":
            _ensure_device_credential_columns(engine)
        elif migration.migration_id == "20260821_0002_performance_indexes":
            _ensure_performance_indexes(engine)
        elif migration.migration_id == "20260821_0003_device_types_metadata":
            _ensure_device_type_columns(engine)
        elif migration.migration_id == "20260821_0004_device_topology_metadata":
            _ensure_device_topology_metadata(engine)
        elif migration.migration_id == "20260825_0005_linux_server_monitoring_foundation":
            _ensure_linux_server_monitoring_tables(engine)
        elif migration.migration_id == "20260825_0006_linux_server_inventory":
            _ensure_linux_server_monitoring_tables(engine)
        elif migration.migration_id == "20260825_0007_linux_server_metric_columns":
            _ensure_linux_server_monitoring_tables(engine)
            _ensure_linux_metric_columns(engine)
        elif migration.migration_id == "20260825_0008_linux_security_events":
            _ensure_linux_server_monitoring_tables(engine)
        elif migration.migration_id == "20260825_0009_linux_monitoring_scheduler":
            _ensure_linux_server_monitoring_tables(engine)
            _ensure_linux_scheduler_columns(engine)
        elif migration.migration_id == "20260825_0010_linux_metric_retention":
            _ensure_linux_metric_retention(engine)
        else:
            raise ValueError(f"Unknown migration id: {migration.migration_id}")
        _record_migration(engine, migration)
        newly_applied.append(migration.migration_id)
        applied.add(migration.migration_id)

    return newly_applied


def get_migration_status(engine: Engine) -> dict[str, object]:
    """Return applied migration ids and counts for diagnostics/admin use."""
    applied = sorted(_applied_migrations(engine))
    return {
        "applied_count": len(applied),
        "applied_ids": applied,
        "known_count": len(MIGRATIONS),
    }
