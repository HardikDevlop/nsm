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
    "snmp_port": "INTEGER",
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
    Migration(
        migration_id="20260829_0011_flow_records",
        description="Create additive normalized NetFlow and IPFIX records table",
    ),
    Migration(
        migration_id="20260829_0012_apm_metrics",
        description="Create additive APM application, service, transaction and metric tables",
    ),
    Migration(
        migration_id="20260829_0013_apm_dependencies",
        description="Create additive APM dependency observations and indexes",
    ),
    Migration(
        migration_id="20260829_0014_cmdb_foundation",
        description="Create additive CMDB types, configuration items, relationships and history",
    ),
    Migration(
        migration_id="20260829_0015_rca",
        description="Create additive RCA incidents and auditable alert/topology evidence",
    ),
    Migration(
        migration_id="20260829_0016_incident_management",
        description="Create persisted incident management records linked to alerts and RCA",
    ),
    Migration(
        migration_id="20260829_0017_incident_sla",
        description="Create incident SLA policies, timers, breach escalation and history",
    ),
    Migration(
        migration_id="20260829_0018_problem_management",
        description="Create problems, recurring incident links and immutable problem history",
    ),
    Migration(
        migration_id="20260829_0019_change_management",
        description="Create change requests, approvals, maintenance windows and dependency links",
    ),
    Migration(
        migration_id="20260829_0020_knowledge_base",
        description="Create searchable knowledge articles, versions and typed NMS links",
    ),
    Migration(
        migration_id="20260829_0021_device_configuration_versions",
        description="Create encrypted device configuration versions with checksum deduplication",
    ),
    Migration(
        migration_id="20260829_0022_configuration_comparisons",
        description="Store audited configuration version comparisons and categorized line diffs",
    ),
    Migration(
        migration_id="20260829_0023_configuration_compliance",
        description="Create persisted configuration compliance policies and violation history",
    ),
    Migration(migration_id="20260829_0024_availability_reports", description="Store planned and unplanned availability reports"),
    Migration(migration_id="20260829_0025_virtualization_objects", description="Store normalized provider-independent virtualization inventory"),
    Migration(migration_id="20260829_0026_qos_samples", description="Store QoS class and queue history"),
    Migration(migration_id="20260829_0027_bgp_observations", description="Store BGP neighbor and route history"),
    Migration(migration_id="20260829_0028_syslog_records", description="Store normalized asynchronous Syslog records"),
    Migration(migration_id="20260829_0029_syslog_correlation", description="Add Syslog correlation links and alert rules"),
    Migration(migration_id="20260831_0030_cmdb_reconciliation", description="Add CMDB source reconciliation metadata and relationship ownership"),
    Migration(migration_id="20260831_0031_availability_intervals", description="Add accurate availability intervals, metrics, SLA persistence, and idempotent reports"),
    Migration(migration_id="20260831_0032_availability_nullable_reconciliation", description="Align availability report nullability for unevaluable reports"),
    Migration(migration_id="20260831_0033_incident_automation", description="Add Incident correlation, lifecycle, acknowledgement, recovery, and history"),
    Migration(migration_id="20260901_0034_problem_priority", description="Add Problem priority with a safe default"),
    Migration(migration_id="20260901_0035_problem_timezone", description="Align legacy Problem timestamps with application timezone"),
    Migration(migration_id="20260902_0036_snmp_port", description="Persist configurable SNMP transport port"),
    Migration(migration_id="20260902_0037_sflow_counters", description="Persist sFlow generic interface counter samples"),
    Migration(migration_id="20260902_0038_ipfix_nullable_timestamps", description="Allow IPFIX records to preserve absent flow timestamps"),
    Migration(migration_id="20260902_0039_alert_interface_identity", description="Persist the SNMP interface identity on interface alerts"),
    Migration(migration_id="20260902_0040_change_core_workflow", description="Add Change priority, ownership, approval and execution fields"),
    Migration(migration_id="20260902_0041_change_problem_links", description="Add persisted Change to Problem relationships"),
    Migration(migration_id="20260902_0042_knowledge_core_workflow", description="Add Knowledge article metadata, lifecycle and audit history"),
    Migration(migration_id="20260902_0043_knowledge_relationships_usefulness", description="Add Knowledge change, CI, related article and feedback relationships"),
    Migration(migration_id="20260902_0044_syslog_backend_readiness", description="Complete Syslog receiver, parsing, filtering, rules and retention fields"),
    Migration(migration_id="20260910_0045_snmp_scalability_indexes", description="Add composite indexes for SNMP history and active-alert hot queries"),
    Migration(migration_id="20260917_0046_icmp_health_evidence", description="Add durable realtime ICMP attempt and result evidence"),
    Migration(migration_id="20260922_0047_audit_outcome", description="Track audit event outcome for authentication and security events"),
)


def _ensure_snmp_scalability_indexes(engine: Engine) -> None:
    statements = (
        'CREATE INDEX IF NOT EXISTS "ix_cpu_statistics_device_time" ON cpu_statistics (device_id, created_at DESC, id DESC)',
        'CREATE INDEX IF NOT EXISTS "ix_memory_statistics_device_time" ON memory_statistics (device_id, created_at DESC, id DESC)',
        'CREATE INDEX IF NOT EXISTS "ix_storage_statistics_device_time" ON storage_statistics (device_id, created_at DESC, id DESC)',
        'CREATE INDEX IF NOT EXISTS "ix_environment_statistics_device_time" ON environment_statistics (device_id, created_at DESC, id DESC)',
        'CREATE INDEX IF NOT EXISTS "ix_interface_statistics_device_interface_time" ON interface_statistics (device_id, interface_id, created_at DESC, id DESC)',
        'CREATE INDEX IF NOT EXISTS "ix_polling_history_device_collector_time" ON polling_history (device_id, collector, created_at DESC, id DESC)',
        'CREATE INDEX IF NOT EXISTS "ix_polling_history_device_id_desc" ON polling_history (device_id, id DESC)',
        "CREATE INDEX IF NOT EXISTS \"ix_alerts_active_device_title_status\" ON alerts (device_id, title, status) WHERE deleted_at IS NULL",
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


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


def _ensure_flow_records(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS flow_records (
                id BIGSERIAL PRIMARY KEY,
                device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL,
                exporter_ip VARCHAR(64) NOT NULL,
                protocol VARCHAR(20) NOT NULL,
                observation_domain VARCHAR(120),
                source_version VARCHAR(20),
                flow_start TIMESTAMP NOT NULL,
                flow_end TIMESTAMP NOT NULL,
                received_at TIMESTAMP NOT NULL,
                src_ip VARCHAR(64),
                dst_ip VARCHAR(64),
                src_port INTEGER,
                dst_port INTEGER,
                ip_protocol INTEGER,
                bytes BIGINT NOT NULL DEFAULT 0,
                packets BIGINT NOT NULL DEFAULT 0,
                input_interface_id INTEGER,
                output_interface_id INTEGER,
                raw_fields JSON NOT NULL DEFAULT '{}',
                record_hash VARCHAR(64) NOT NULL UNIQUE
            )
        """))
        connection.execute(text(
            'ALTER TABLE flow_records ADD COLUMN IF NOT EXISTS device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL'
        ))
        connection.execute(text(
            'CREATE INDEX IF NOT EXISTS "ix_flow_records_device_time" '
            'ON flow_records (device_id, flow_start DESC)'
        ))
        connection.execute(text(
            'CREATE INDEX IF NOT EXISTS "ix_flow_records_exporter_received" '
            'ON flow_records (exporter_ip, received_at DESC)'
        ))
        connection.execute(text(
            'CREATE INDEX IF NOT EXISTS "ix_flow_records_time_protocol" '
            'ON flow_records (flow_start, protocol)'
        ))
        connection.execute(text(
            'CREATE INDEX IF NOT EXISTS "ix_flow_records_src_time" '
            'ON flow_records (src_ip, flow_start DESC)'
        ))
        connection.execute(text(
            'CREATE INDEX IF NOT EXISTS "ix_flow_records_dst_time" '
            'ON flow_records (dst_ip, flow_start DESC)'
        ))


def _ensure_sflow_counters(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS sflow_counter_samples (
                id BIGSERIAL PRIMARY KEY,
                device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL,
                exporter_ip VARCHAR(64) NOT NULL,
                agent_address VARCHAR(64) NOT NULL,
                sub_agent_id INTEGER NOT NULL,
                sequence_number BIGINT NOT NULL,
                if_index INTEGER NOT NULL,
                interface_name VARCHAR(160),
                if_type INTEGER NOT NULL,
                if_speed BIGINT NOT NULL,
                if_direction INTEGER NOT NULL,
                if_status INTEGER NOT NULL,
                if_in_octets BIGINT NOT NULL,
                if_in_ucast_pkts BIGINT NOT NULL,
                if_in_multicast_pkts BIGINT NOT NULL,
                if_in_broadcast_pkts BIGINT NOT NULL,
                if_in_discards BIGINT NOT NULL,
                if_in_errors BIGINT NOT NULL,
                if_out_octets BIGINT NOT NULL,
                if_out_ucast_pkts BIGINT NOT NULL,
                if_out_multicast_pkts BIGINT NOT NULL,
                if_out_broadcast_pkts BIGINT NOT NULL,
                if_out_discards BIGINT NOT NULL,
                if_out_errors BIGINT NOT NULL,
                observed_at TIMESTAMP NOT NULL,
                raw_fields JSON NOT NULL DEFAULT '{}',
                record_hash VARCHAR(64) NOT NULL UNIQUE
            )
        """))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_sflow_counter_device_time" ON sflow_counter_samples (device_id, observed_at DESC)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_sflow_counter_exporter_time" ON sflow_counter_samples (exporter_ip, observed_at DESC)'))


def _ensure_apm_metrics(engine: Engine) -> None:
    # Tables are registered in Base.metadata and created before migrations;
    # this migration adds only the query/retention indexes idempotently.
    with engine.begin() as connection:
        connection.execute(text(
            'CREATE INDEX IF NOT EXISTS "ix_apm_metrics_service_time" '
            'ON apm_metric_samples (service_id, observed_at DESC)'
        ))
        connection.execute(text(
            'CREATE INDEX IF NOT EXISTS "ix_apm_metrics_application_time" '
            'ON apm_metric_samples (application_id, observed_at DESC)'
        ))
        connection.execute(text(
            'CREATE INDEX IF NOT EXISTS "ix_apm_metrics_retention" '
            'ON apm_metric_samples (observed_at, id)'
        ))


def _ensure_apm_dependencies(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS apm_dependencies (
                id SERIAL PRIMARY KEY,
                source_service_id INTEGER NOT NULL REFERENCES apm_services(id) ON DELETE CASCADE,
                target_service_id INTEGER REFERENCES apm_services(id) ON DELETE SET NULL,
                target_name VARCHAR(240) NOT NULL,
                dependency_type VARCHAR(60),
                device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL,
                site_id INTEGER REFERENCES sites(id) ON DELETE SET NULL,
                observed_at TIMESTAMP NOT NULL,
                call_count INTEGER NOT NULL DEFAULT 0,
                error_count INTEGER NOT NULL DEFAULT 0,
                response_time_ms DOUBLE PRECISION NOT NULL DEFAULT 0
            )
        """))
        connection.execute(text(
            'CREATE INDEX IF NOT EXISTS "ix_apm_dependencies_source_time" '
            'ON apm_dependencies (source_service_id, observed_at DESC)'
        ))
        connection.execute(text(
            'CREATE INDEX IF NOT EXISTS "ix_apm_dependencies_site_time" '
            'ON apm_dependencies (site_id, observed_at DESC)'
        ))


def _ensure_cmdb_foundation(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS cmdb_ci_types (
                id SERIAL PRIMARY KEY,
                name VARCHAR(120) NOT NULL UNIQUE,
                category VARCHAR(80) NOT NULL DEFAULT 'custom',
                description TEXT,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                deleted_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS cmdb_configuration_items (
                id SERIAL PRIMARY KEY,
                ci_type_id INTEGER NOT NULL REFERENCES cmdb_ci_types(id) ON DELETE RESTRICT,
                name VARCHAR(180) NOT NULL,
                external_key VARCHAR(180),
                lifecycle_state VARCHAR(40) NOT NULL DEFAULT 'planned',
                owner_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                organization_id INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
                device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL,
                interface_id INTEGER REFERENCES interfaces(id) ON DELETE SET NULL,
                site_id INTEGER REFERENCES sites(id) ON DELETE SET NULL,
                application_id INTEGER REFERENCES apm_applications(id) ON DELETE SET NULL,
                environment VARCHAR(80),
                attributes JSON NOT NULL DEFAULT '{}',
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                deleted_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS cmdb_ci_relationships (
                id SERIAL PRIMARY KEY,
                source_ci_id INTEGER NOT NULL REFERENCES cmdb_configuration_items(id) ON DELETE CASCADE,
                target_ci_id INTEGER NOT NULL REFERENCES cmdb_configuration_items(id) ON DELETE CASCADE,
                relationship_type VARCHAR(80) NOT NULL,
                created_at TIMESTAMP NOT NULL,
                deleted_at TIMESTAMP,
                CONSTRAINT uq_cmdb_ci_relationship UNIQUE (source_ci_id, target_ci_id, relationship_type)
            );
            CREATE TABLE IF NOT EXISTS cmdb_ci_history (
                id SERIAL PRIMARY KEY,
                ci_id INTEGER NOT NULL REFERENCES cmdb_configuration_items(id) ON DELETE CASCADE,
                changed_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                action VARCHAR(40) NOT NULL,
                field_name VARCHAR(120),
                old_value TEXT,
                new_value TEXT,
                changed_at TIMESTAMP NOT NULL
            );
        """))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_cmdb_ci_type_lifecycle" ON cmdb_configuration_items (ci_type_id, lifecycle_state)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_cmdb_ci_links_device" ON cmdb_configuration_items (device_id)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_cmdb_ci_links_site" ON cmdb_configuration_items (site_id)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_cmdb_ci_links_application" ON cmdb_configuration_items (application_id)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_cmdb_ci_history_ci_time" ON cmdb_ci_history (ci_id, changed_at DESC)'))


def _ensure_cmdb_reconciliation(engine: Engine) -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if "cmdb_configuration_items" in tables:
            present = {column["name"] for column in inspector.get_columns("cmdb_configuration_items")}
            additions = {
                "first_discovered": "TIMESTAMP",
                "last_seen": "TIMESTAMP",
                "last_synchronized": "TIMESTAMP",
                "sync_source": "VARCHAR(40)",
            }
            for name, sql_type in additions.items():
                if name not in present:
                    default = " DEFAULT 'manual'" if name == "sync_source" else ""
                    connection.execute(text(f'ALTER TABLE cmdb_configuration_items ADD COLUMN "{name}" {sql_type}{default}'))
            connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_cmdb_ci_sync_source" ON cmdb_configuration_items (sync_source, last_synchronized)'))
        if "cmdb_ci_relationships" in tables:
            present = {column["name"] for column in inspector.get_columns("cmdb_ci_relationships")}
            additions = {"managed_by": "VARCHAR(40) DEFAULT 'manual'", "source_key": "VARCHAR(240)"}
            for name, sql_type in additions.items():
                if name not in present:
                    connection.execute(text(f'ALTER TABLE cmdb_ci_relationships ADD COLUMN "{name}" {sql_type}'))
            connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_cmdb_relationship_source" ON cmdb_ci_relationships (managed_by, source_key)'))


def _ensure_rca_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS rca_incidents (
                id SERIAL PRIMARY KEY,
                correlation_key VARCHAR(128) NOT NULL UNIQUE,
                root_kind VARCHAR(30) NOT NULL,
                root_label VARCHAR(180) NOT NULL,
                root_device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL,
                root_interface_id INTEGER REFERENCES interfaces(id) ON DELETE SET NULL,
                root_ci_id INTEGER REFERENCES cmdb_configuration_items(id) ON DELETE SET NULL,
                confidence DOUBLE PRECISION NOT NULL,
                impact_summary TEXT NOT NULL,
                window_start TIMESTAMP NOT NULL,
                window_end TIMESTAMP NOT NULL,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            );
            CREATE TABLE IF NOT EXISTS rca_evidence (
                id SERIAL PRIMARY KEY,
                incident_id INTEGER NOT NULL REFERENCES rca_incidents(id) ON DELETE CASCADE,
                evidence_type VARCHAR(40) NOT NULL,
                alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL,
                event_id INTEGER REFERENCES events(id) ON DELETE SET NULL,
                relationship_id INTEGER REFERENCES cmdb_ci_relationships(id) ON DELETE SET NULL,
                score DOUBLE PRECISION NOT NULL DEFAULT 0,
                reason TEXT NOT NULL,
                payload JSON,
                created_at TIMESTAMP NOT NULL,
                CONSTRAINT uq_rca_evidence_item UNIQUE (incident_id, evidence_type, alert_id, relationship_id)
            );
        """))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_rca_incidents_window" ON rca_incidents (window_start, window_end)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_rca_evidence_incident" ON rca_evidence (incident_id)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_rca_evidence_alert" ON rca_evidence (alert_id)'))


def _ensure_incident_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS incidents (
                id SERIAL PRIMARY KEY,
                title VARCHAR(180) NOT NULL,
                description TEXT,
                category VARCHAR(60) NOT NULL,
                priority VARCHAR(30) NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'open',
                assigned_to INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                rca_incident_id INTEGER REFERENCES rca_incidents(id) ON DELETE SET NULL,
                closed_at TIMESTAMP,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL
            );
            CREATE TABLE IF NOT EXISTS incident_alerts (
                id SERIAL PRIMARY KEY,
                incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
                alert_id INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
                linked_at TIMESTAMP NOT NULL,
                CONSTRAINT uq_incident_alert UNIQUE (incident_id, alert_id)
            );
            CREATE TABLE IF NOT EXISTS incident_comments (
                id SERIAL PRIMARY KEY,
                incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
                author_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                body TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL
            );
            CREATE TABLE IF NOT EXISTS incident_attachments (
                id SERIAL PRIMARY KEY,
                incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
                uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                file_name VARCHAR(255) NOT NULL,
                content_type VARCHAR(120),
                size_bytes INTEGER NOT NULL DEFAULT 0,
                storage_key VARCHAR(500) NOT NULL,
                created_at TIMESTAMP NOT NULL
            );
        """))
        for name, table, columns in (
            ("ix_incidents_status_priority", "incidents", "status, priority"),
            ("ix_incidents_assigned_status", "incidents", "assigned_to, status"),
            ("ix_incident_alerts_alert", "incident_alerts", "alert_id"),
            ("ix_incident_comments_incident", "incident_comments", "incident_id, created_at"),
        ):
            connection.execute(text(f'CREATE INDEX IF NOT EXISTS "{name}" ON {table} ({columns})'))


def _ensure_incident_sla_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "incidents" in inspector.get_table_names() and "service_id" not in {c["name"] for c in inspector.get_columns("incidents")}:
            connection.execute(text('ALTER TABLE incidents ADD COLUMN service_id INTEGER REFERENCES apm_services(id) ON DELETE SET NULL'))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS incident_sla_configs (
                id SERIAL PRIMARY KEY,
                priority VARCHAR(30) NOT NULL,
                service_id INTEGER REFERENCES apm_services(id) ON DELETE CASCADE,
                response_target_minutes INTEGER NOT NULL,
                resolution_target_minutes INTEGER NOT NULL,
                pause_states JSON NOT NULL DEFAULT '["pending"]',
                escalation_after_minutes INTEGER,
                escalation_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                CONSTRAINT uq_incident_sla_policy UNIQUE (priority, service_id)
            );
            CREATE TABLE IF NOT EXISTS incident_sla_timers (
                id SERIAL PRIMARY KEY,
                incident_id INTEGER NOT NULL UNIQUE REFERENCES incidents(id) ON DELETE CASCADE,
                config_id INTEGER NOT NULL REFERENCES incident_sla_configs(id) ON DELETE RESTRICT,
                started_at TIMESTAMP NOT NULL,
                response_deadline TIMESTAMP NOT NULL,
                resolution_deadline TIMESTAMP NOT NULL,
                first_responded_at TIMESTAMP,
                resolved_at TIMESTAMP,
                paused_at TIMESTAMP,
                paused_seconds INTEGER NOT NULL DEFAULT 0,
                response_breached BOOLEAN NOT NULL DEFAULT FALSE,
                resolution_breached BOOLEAN NOT NULL DEFAULT FALSE,
                escalation_sent BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at TIMESTAMP NOT NULL
            );
            CREATE TABLE IF NOT EXISTS incident_sla_history (
                id SERIAL PRIMARY KEY,
                incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
                timer_id INTEGER REFERENCES incident_sla_timers(id) ON DELETE SET NULL,
                action VARCHAR(50) NOT NULL,
                details TEXT,
                created_at TIMESTAMP NOT NULL
            );
        """))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_incident_sla_config_lookup" ON incident_sla_configs (priority, service_id, enabled)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_incident_sla_history_incident" ON incident_sla_history (incident_id, created_at)'))


def _ensure_problem_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "incidents" in inspector.get_table_names() and "service_id" not in {c["name"] for c in inspector.get_columns("incidents")}:
            connection.execute(text('ALTER TABLE incidents ADD COLUMN service_id INTEGER REFERENCES apm_services(id) ON DELETE SET NULL'))
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS problems (
                id SERIAL PRIMARY KEY,
                number VARCHAR(40) NOT NULL UNIQUE,
                title VARCHAR(180) NOT NULL,
                description TEXT,
                category VARCHAR(60) NOT NULL,
                status VARCHAR(30) NOT NULL DEFAULT 'open',
                root_cause TEXT,
                workaround TEXT,
                known_error TEXT,
                permanent_fix TEXT,
                owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                closed_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS problem_incidents (
                id SERIAL PRIMARY KEY,
                problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
                incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
                linked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                linked_at TIMESTAMP NOT NULL,
                CONSTRAINT uq_problem_incident UNIQUE (problem_id, incident_id)
            );
            CREATE TABLE IF NOT EXISTS problem_history (
                id SERIAL PRIMARY KEY,
                problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
                changed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                action VARCHAR(60) NOT NULL,
                field_name VARCHAR(80),
                old_value TEXT,
                new_value TEXT,
                created_at TIMESTAMP NOT NULL
            );
        """))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_problem_incidents_incident" ON problem_incidents (incident_id)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_problem_history_problem" ON problem_history (problem_id, created_at)'))


def _ensure_change_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS change_requests (
                id SERIAL PRIMARY KEY,
                number VARCHAR(40) NOT NULL UNIQUE,
                title VARCHAR(180) NOT NULL,
                description TEXT,
                category VARCHAR(50) NOT NULL,
                risk VARCHAR(30) NOT NULL,
                impact VARCHAR(30) NOT NULL,
                priority VARCHAR(2) NOT NULL DEFAULT 'p3',
                status VARCHAR(30) NOT NULL DEFAULT 'draft',
                requested_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                approved_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                approved_at TIMESTAMP,
                approval_comment TEXT,
                approval_required BOOLEAN NOT NULL DEFAULT FALSE,
                rejected_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                rejected_at TIMESTAMP,
                rejection_comment TEXT,
                maintenance_start TIMESTAMP,
                maintenance_end TIMESTAMP,
                implementation_plan TEXT,
                rollback_plan TEXT,
                implementation_result TEXT,
                implementation_failure_reason TEXT,
                rollback_result TEXT,
                rollback_status VARCHAR(30),
                closure_note TEXT,
                created_at TIMESTAMP NOT NULL,
                updated_at TIMESTAMP NOT NULL,
                closed_at TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS change_cis (
                id SERIAL PRIMARY KEY,
                change_id INTEGER NOT NULL REFERENCES change_requests(id) ON DELETE CASCADE,
                ci_id INTEGER NOT NULL REFERENCES cmdb_configuration_items(id) ON DELETE CASCADE,
                linked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                linked_at TIMESTAMP NOT NULL,
                CONSTRAINT uq_change_ci UNIQUE (change_id, ci_id)
            );
            CREATE TABLE IF NOT EXISTS change_incidents (
                id SERIAL PRIMARY KEY,
                change_id INTEGER NOT NULL REFERENCES change_requests(id) ON DELETE CASCADE,
                incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
                linked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                linked_at TIMESTAMP NOT NULL,
                CONSTRAINT uq_change_incident UNIQUE (change_id, incident_id)
            );
            CREATE TABLE IF NOT EXISTS change_problems (
                id SERIAL PRIMARY KEY,
                change_id INTEGER NOT NULL REFERENCES change_requests(id) ON DELETE CASCADE,
                problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
                linked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                linked_at TIMESTAMP NOT NULL,
                CONSTRAINT uq_change_problem UNIQUE (change_id, problem_id)
            );
            CREATE TABLE IF NOT EXISTS change_history (
                id SERIAL PRIMARY KEY,
                change_id INTEGER NOT NULL REFERENCES change_requests(id) ON DELETE CASCADE,
                changed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                action VARCHAR(60) NOT NULL,
                field_name VARCHAR(80),
                old_value TEXT,
                new_value TEXT,
                metadata_json JSON,
                created_at TIMESTAMP NOT NULL
            );
        """))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_change_status_window" ON change_requests (status, maintenance_start, maintenance_end)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_change_history_change" ON change_history (change_id, created_at)'))


def _ensure_knowledge_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS knowledge_articles (
                id SERIAL PRIMARY KEY, number VARCHAR(40) NOT NULL UNIQUE, title VARCHAR(220) NOT NULL,
                summary TEXT, article_type VARCHAR(30) NOT NULL, category VARCHAR(80), tags JSON NOT NULL DEFAULT '[]',
                status VARCHAR(30) NOT NULL DEFAULT 'draft', current_version INTEGER NOT NULL DEFAULT 1,
                created_by INTEGER REFERENCES users(id) ON DELETE SET NULL, updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL, published_at TIMESTAMP,
                view_count INTEGER NOT NULL DEFAULT 0, helpful_count INTEGER NOT NULL DEFAULT 0, not_helpful_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge_article_versions (
                id SERIAL PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES knowledge_articles(id) ON DELETE CASCADE,
                version INTEGER NOT NULL, body TEXT NOT NULL, changed_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMP NOT NULL, CONSTRAINT uq_knowledge_article_version UNIQUE(article_id, version)
            );
            CREATE TABLE IF NOT EXISTS knowledge_incident_links (
                id SERIAL PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES knowledge_articles(id) ON DELETE CASCADE,
                incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE, linked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                linked_at TIMESTAMP NOT NULL, CONSTRAINT uq_knowledge_incident UNIQUE(article_id, incident_id)
            );
            CREATE TABLE IF NOT EXISTS knowledge_problem_links (
                id SERIAL PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES knowledge_articles(id) ON DELETE CASCADE,
                problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE, linked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                linked_at TIMESTAMP NOT NULL, CONSTRAINT uq_knowledge_problem UNIQUE(article_id, problem_id)
            );
            CREATE TABLE IF NOT EXISTS knowledge_device_links (
                id SERIAL PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES knowledge_articles(id) ON DELETE CASCADE,
                device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE, linked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                linked_at TIMESTAMP NOT NULL, CONSTRAINT uq_knowledge_device UNIQUE(article_id, device_id)
            );
            CREATE TABLE IF NOT EXISTS knowledge_service_links (
                id SERIAL PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES knowledge_articles(id) ON DELETE CASCADE,
                service_id INTEGER NOT NULL REFERENCES apm_services(id) ON DELETE CASCADE, linked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                linked_at TIMESTAMP NOT NULL, CONSTRAINT uq_knowledge_service UNIQUE(article_id, service_id)
            );
            CREATE TABLE IF NOT EXISTS knowledge_article_history (
                id SERIAL PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES knowledge_articles(id) ON DELETE CASCADE,
                action VARCHAR(60) NOT NULL, actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                metadata_json JSON, created_at TIMESTAMP NOT NULL
            );
            CREATE TABLE IF NOT EXISTS knowledge_change_links (
                id SERIAL PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES knowledge_articles(id) ON DELETE CASCADE,
                change_id INTEGER NOT NULL REFERENCES change_requests(id) ON DELETE CASCADE, linked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                linked_at TIMESTAMP NOT NULL, CONSTRAINT uq_knowledge_change UNIQUE(article_id, change_id)
            );
            CREATE TABLE IF NOT EXISTS knowledge_ci_links (
                id SERIAL PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES knowledge_articles(id) ON DELETE CASCADE,
                ci_id INTEGER NOT NULL REFERENCES cmdb_configuration_items(id) ON DELETE CASCADE, linked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                linked_at TIMESTAMP NOT NULL, CONSTRAINT uq_knowledge_ci UNIQUE(article_id, ci_id)
            );
            CREATE TABLE IF NOT EXISTS knowledge_related_links (
                id SERIAL PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES knowledge_articles(id) ON DELETE CASCADE,
                related_article_id INTEGER NOT NULL REFERENCES knowledge_articles(id) ON DELETE CASCADE, linked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                linked_at TIMESTAMP NOT NULL, CONSTRAINT uq_knowledge_related UNIQUE(article_id, related_article_id),
                CONSTRAINT chk_knowledge_related_not_self CHECK(article_id <> related_article_id)
            );
            CREATE TABLE IF NOT EXISTS knowledge_feedback (
                id SERIAL PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES knowledge_articles(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, helpful BOOLEAN NOT NULL,
                created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL, CONSTRAINT uq_knowledge_feedback_user UNIQUE(article_id, user_id)
            );
        """))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_knowledge_search" ON knowledge_articles (status, article_type, title)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_knowledge_version_article" ON knowledge_article_versions (article_id, version DESC)'))


def _ensure_configuration_version_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS device_configuration_versions (
                id SERIAL PRIMARY KEY,
                device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
                version INTEGER NOT NULL,
                source VARCHAR(40) NOT NULL,
                checksum VARCHAR(64) NOT NULL,
                encrypted_content TEXT NOT NULL,
                is_startup BOOLEAN NOT NULL DEFAULT FALSE,
                captured_at TIMESTAMP NOT NULL,
                captured_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                CONSTRAINT uq_device_config_version UNIQUE (device_id, version)
            );
        """))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_device_config_checksum" ON device_configuration_versions (device_id, checksum)'))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_device_config_capture_time" ON device_configuration_versions (device_id, captured_at DESC)'))


def _ensure_configuration_comparison_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE IF NOT EXISTS configuration_comparisons (
                id SERIAL PRIMARY KEY,
                device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
                from_version INTEGER NOT NULL,
                to_version INTEGER NOT NULL,
                added_lines JSON NOT NULL DEFAULT '[]',
                removed_lines JSON NOT NULL DEFAULT '[]',
                changed_lines JSON NOT NULL DEFAULT '[]',
                initiated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                created_at TIMESTAMP NOT NULL
            );
        """))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_config_comparison_device_time" ON configuration_comparisons (device_id, created_at DESC)'))

def _ensure_configuration_compliance_tables(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(text("""CREATE TABLE IF NOT EXISTS configuration_compliance_policies (id INTEGER PRIMARY KEY, name VARCHAR(160) UNIQUE NOT NULL, description TEXT, rules JSON NOT NULL DEFAULT '{}', enabled BOOLEAN NOT NULL DEFAULT TRUE, created_by INTEGER REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMP NOT NULL)"""))
        connection.execute(text("""CREATE TABLE IF NOT EXISTS configuration_compliance_violations (id INTEGER PRIMARY KEY, policy_id INTEGER NOT NULL REFERENCES configuration_compliance_policies(id) ON DELETE CASCADE, device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE, version INTEGER NOT NULL, severity VARCHAR(20) NOT NULL, status VARCHAR(20) NOT NULL DEFAULT 'open', evidence JSON NOT NULL DEFAULT '{}', recommendation TEXT, detected_at TIMESTAMP NOT NULL, resolved_at TIMESTAMP, resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL, CONSTRAINT uq_config_compliance_violation UNIQUE(policy_id, device_id, version))"""))
        connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_config_compliance_violation_status" ON configuration_compliance_violations (status, detected_at DESC)'))


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
        elif migration.migration_id == "20260829_0011_flow_records":
            _ensure_flow_records(engine)
        elif migration.migration_id == "20260829_0012_apm_metrics":
            _ensure_apm_metrics(engine)
        elif migration.migration_id == "20260829_0013_apm_dependencies":
            _ensure_apm_dependencies(engine)
        elif migration.migration_id == "20260829_0014_cmdb_foundation":
            _ensure_cmdb_foundation(engine)
        elif migration.migration_id == "20260829_0015_rca":
            _ensure_rca_tables(engine)
        elif migration.migration_id == "20260829_0016_incident_management":
            _ensure_incident_tables(engine)
        elif migration.migration_id == "20260829_0017_incident_sla":
            _ensure_incident_sla_tables(engine)
        elif migration.migration_id == "20260829_0018_problem_management":
            _ensure_problem_tables(engine)
        elif migration.migration_id == "20260901_0034_problem_priority":
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE problems ADD COLUMN IF NOT EXISTS priority VARCHAR(2) NOT NULL DEFAULT 'p3'"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_problems_priority ON problems (priority)"))
        elif migration.migration_id == "20260901_0035_problem_timezone":
            with engine.begin() as connection:
                connection.execute(text("UPDATE problems SET created_at = created_at + INTERVAL '5 hours 30 minutes', updated_at = updated_at + INTERVAL '5 hours 30 minutes', closed_at = closed_at + INTERVAL '5 hours 30 minutes' WHERE created_at IS NOT NULL"))
                connection.execute(text("UPDATE problem_incidents SET linked_at = linked_at + INTERVAL '5 hours 30 minutes' WHERE linked_at IS NOT NULL"))
                connection.execute(text("UPDATE problem_history SET created_at = created_at + INTERVAL '5 hours 30 minutes' WHERE created_at IS NOT NULL"))
        elif migration.migration_id == "20260902_0036_snmp_port":
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE device_credentials ADD COLUMN IF NOT EXISTS snmp_port INTEGER"))
        elif migration.migration_id == "20260902_0037_sflow_counters":
            _ensure_sflow_counters(engine)
        elif migration.migration_id == "20260902_0038_ipfix_nullable_timestamps":
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE flow_records ALTER COLUMN flow_start DROP NOT NULL"))
                connection.execute(text("ALTER TABLE flow_records ALTER COLUMN flow_end DROP NOT NULL"))
        elif migration.migration_id == "20260902_0039_alert_interface_identity":
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS interface_id INTEGER REFERENCES interfaces(id) ON DELETE SET NULL"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_alerts_interface_status ON alerts (interface_id, status)"))
        elif migration.migration_id == "20260902_0040_change_core_workflow":
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS priority VARCHAR(2) NOT NULL DEFAULT 'p3'"))
                connection.execute(text("ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL"))
                connection.execute(text("ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP"))
                connection.execute(text("ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS approval_required BOOLEAN NOT NULL DEFAULT FALSE"))
                connection.execute(text("ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS rejected_by INTEGER REFERENCES users(id) ON DELETE SET NULL"))
                connection.execute(text("ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS rejected_at TIMESTAMP"))
                connection.execute(text("ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS rejection_comment TEXT"))
                connection.execute(text("ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS implementation_result TEXT"))
                connection.execute(text("ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS implementation_failure_reason TEXT"))
                connection.execute(text("ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS rollback_result TEXT"))
                connection.execute(text("ALTER TABLE change_requests ADD COLUMN IF NOT EXISTS rollback_status VARCHAR(30)"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_change_owner_status ON change_requests (owner_id, status)"))
        elif migration.migration_id == "20260902_0041_change_problem_links":
            with engine.begin() as connection:
                connection.execute(text("""CREATE TABLE IF NOT EXISTS change_problems (
                    id SERIAL PRIMARY KEY,
                    change_id INTEGER NOT NULL REFERENCES change_requests(id) ON DELETE CASCADE,
                    problem_id INTEGER NOT NULL REFERENCES problems(id) ON DELETE CASCADE,
                    linked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    linked_at TIMESTAMP NOT NULL,
                    CONSTRAINT uq_change_problem UNIQUE (change_id, problem_id)
                )"""))
                connection.execute(text('CREATE INDEX IF NOT EXISTS ix_change_problem_change ON change_problems (change_id)'))
                connection.execute(text('CREATE INDEX IF NOT EXISTS ix_change_problem_problem ON change_problems (problem_id)'))
        elif migration.migration_id == "20260902_0042_knowledge_core_workflow":
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE knowledge_articles ADD COLUMN IF NOT EXISTS summary TEXT"))
                connection.execute(text("ALTER TABLE knowledge_articles ADD COLUMN IF NOT EXISTS category VARCHAR(80)"))
                connection.execute(text("ALTER TABLE knowledge_articles ADD COLUMN IF NOT EXISTS tags JSON NOT NULL DEFAULT '[]'"))
                connection.execute(text("ALTER TABLE knowledge_articles ADD COLUMN IF NOT EXISTS owner_id INTEGER REFERENCES users(id) ON DELETE SET NULL"))
                connection.execute(text("ALTER TABLE knowledge_articles ADD COLUMN IF NOT EXISTS published_at TIMESTAMP"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_knowledge_owner_status ON knowledge_articles (owner_id, status)"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_knowledge_category ON knowledge_articles (category)"))
                connection.execute(text("""CREATE TABLE IF NOT EXISTS knowledge_article_history (
                    id SERIAL PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES knowledge_articles(id) ON DELETE CASCADE,
                    action VARCHAR(60) NOT NULL, actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    metadata_json JSON, created_at TIMESTAMP NOT NULL
                )"""))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_knowledge_history_article_time ON knowledge_article_history (article_id, created_at)"))
        elif migration.migration_id == "20260902_0043_knowledge_relationships_usefulness":
            with engine.begin() as connection:
                for column in (
                    "view_count INTEGER NOT NULL DEFAULT 0",
                    "helpful_count INTEGER NOT NULL DEFAULT 0",
                    "not_helpful_count INTEGER NOT NULL DEFAULT 0",
                ):
                    connection.execute(text(f"ALTER TABLE knowledge_articles ADD COLUMN IF NOT EXISTS {column}"))
                connection.execute(text("""CREATE TABLE IF NOT EXISTS knowledge_change_links (
                    id SERIAL PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES knowledge_articles(id) ON DELETE CASCADE,
                    change_id INTEGER NOT NULL REFERENCES change_requests(id) ON DELETE CASCADE, linked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    linked_at TIMESTAMP NOT NULL, CONSTRAINT uq_knowledge_change UNIQUE(article_id, change_id)
                )"""))
                connection.execute(text("""CREATE TABLE IF NOT EXISTS knowledge_ci_links (
                    id SERIAL PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES knowledge_articles(id) ON DELETE CASCADE,
                    ci_id INTEGER NOT NULL REFERENCES cmdb_configuration_items(id) ON DELETE CASCADE, linked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    linked_at TIMESTAMP NOT NULL, CONSTRAINT uq_knowledge_ci UNIQUE(article_id, ci_id)
                )"""))
                connection.execute(text("""CREATE TABLE IF NOT EXISTS knowledge_related_links (
                    id SERIAL PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES knowledge_articles(id) ON DELETE CASCADE,
                    related_article_id INTEGER NOT NULL REFERENCES knowledge_articles(id) ON DELETE CASCADE, linked_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    linked_at TIMESTAMP NOT NULL, CONSTRAINT uq_knowledge_related UNIQUE(article_id, related_article_id),
                    CONSTRAINT chk_knowledge_related_not_self CHECK(article_id <> related_article_id)
                )"""))
                connection.execute(text("""CREATE TABLE IF NOT EXISTS knowledge_feedback (
                    id SERIAL PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES knowledge_articles(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, helpful BOOLEAN NOT NULL,
                    created_at TIMESTAMP NOT NULL, updated_at TIMESTAMP NOT NULL, CONSTRAINT uq_knowledge_feedback_user UNIQUE(article_id, user_id)
                )"""))
        elif migration.migration_id == "20260829_0019_change_management":
            _ensure_change_tables(engine)
        elif migration.migration_id == "20260829_0020_knowledge_base":
            _ensure_knowledge_tables(engine)
        elif migration.migration_id == "20260829_0021_device_configuration_versions":
            _ensure_configuration_version_tables(engine)
        elif migration.migration_id == "20260829_0022_configuration_comparisons":
            _ensure_configuration_comparison_tables(engine)
        elif migration.migration_id == "20260829_0023_configuration_compliance":
            _ensure_configuration_compliance_tables(engine)
        elif migration.migration_id == "20260829_0024_availability_reports":
            with engine.begin() as connection:
                connection.execute(text("""CREATE TABLE IF NOT EXISTS availability_reports (id SERIAL PRIMARY KEY, entity_type VARCHAR(30) NOT NULL, entity_id INTEGER NOT NULL, window_start TIMESTAMP NOT NULL, window_end TIMESTAMP NOT NULL, total_seconds INTEGER NOT NULL, planned_downtime_seconds INTEGER NOT NULL, unplanned_downtime_seconds INTEGER NOT NULL, availability_percent DOUBLE PRECISION NOT NULL, downtime_reasons JSON NOT NULL DEFAULT '{}', generated_by INTEGER REFERENCES users(id) ON DELETE SET NULL, generated_at TIMESTAMP NOT NULL)"""))
                connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_availability_entity_time" ON availability_reports (entity_type, entity_id, generated_at DESC)'))
        elif migration.migration_id == "20260831_0031_availability_intervals":
            with engine.begin() as connection:
                for column in (
                    "monitored_duration_seconds INTEGER NOT NULL DEFAULT 0",
                    "uptime_seconds INTEGER NOT NULL DEFAULT 0",
                    "downtime_seconds INTEGER NOT NULL DEFAULT 0",
                    "unknown_seconds INTEGER NOT NULL DEFAULT 0",
                    "coverage_percent DOUBLE PRECISION",
                    "outage_count INTEGER NOT NULL DEFAULT 0",
                    "mttr_seconds DOUBLE PRECISION",
                    "mtbf_seconds DOUBLE PRECISION",
                    "sla_target_percent DOUBLE PRECISION NOT NULL DEFAULT 99.0",
                    "sla_breached BOOLEAN",
                ):
                    connection.execute(text(f"ALTER TABLE availability_reports ADD COLUMN IF NOT EXISTS {column}"))
                connection.execute(text("ALTER TABLE availability_reports ALTER COLUMN availability_percent DROP NOT NULL"))
                connection.execute(text("""CREATE TABLE IF NOT EXISTS availability_outages (
                    id SERIAL PRIMARY KEY,
                    report_id INTEGER NOT NULL REFERENCES availability_reports(id) ON DELETE CASCADE,
                    entity_type VARCHAR(30) NOT NULL,
                    entity_id INTEGER NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    duration_seconds INTEGER NOT NULL,
                    ongoing BOOLEAN NOT NULL DEFAULT FALSE,
                    planned BOOLEAN NOT NULL DEFAULT FALSE,
                    reason VARCHAR(255)
                )"""))
                connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_availability_outage_entity_start" ON availability_outages (entity_type, entity_id, start_time)'))
                connection.execute(text('CREATE UNIQUE INDEX IF NOT EXISTS "uq_availability_report_window" ON availability_reports (entity_type, entity_id, window_start, window_end)'))
        elif migration.migration_id == "20260831_0032_availability_nullable_reconciliation":
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE availability_reports ALTER COLUMN availability_percent DROP NOT NULL"))
        elif migration.migration_id == "20260831_0033_incident_automation":
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE incidents ADD COLUMN IF NOT EXISTS correlation_key VARCHAR(240)"))
                connection.execute(text("ALTER TABLE incidents ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMP"))
                connection.execute(text("ALTER TABLE incidents ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMP"))
                connection.execute(text("ALTER TABLE incidents ADD COLUMN IF NOT EXISTS acknowledged_by INTEGER REFERENCES users(id) ON DELETE SET NULL"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_incidents_correlation_key ON incidents (correlation_key)"))
                connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_incidents_active_correlation_key ON incidents (correlation_key) WHERE correlation_key IS NOT NULL AND status IN ('open', 'investigating', 'pending')"))
                connection.execute(text("""CREATE TABLE IF NOT EXISTS incident_history (
                    id SERIAL PRIMARY KEY,
                    incident_id INTEGER NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
                    action VARCHAR(60) NOT NULL,
                    actor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
                    old_value TEXT,
                    new_value TEXT,
                    reason TEXT,
                    created_at TIMESTAMP NOT NULL
                )"""))
                connection.execute(text('CREATE INDEX IF NOT EXISTS "ix_incident_history_incident_time" ON incident_history (incident_id, created_at)'))
        elif migration.migration_id == "20260829_0025_virtualization_objects":
            with engine.begin() as connection:
                connection.execute(text("""CREATE TABLE IF NOT EXISTS virtualization_objects (id SERIAL PRIMARY KEY, provider VARCHAR(30) NOT NULL, object_type VARCHAR(30) NOT NULL, external_key VARCHAR(240) NOT NULL, name VARCHAR(240) NOT NULL, state VARCHAR(40) NOT NULL DEFAULT 'unknown', parent_external_key VARCHAR(240), attributes JSON NOT NULL DEFAULT '{}', cmdb_ci_id INTEGER REFERENCES cmdb_configuration_items(id) ON DELETE SET NULL, observed_at TIMESTAMP NOT NULL, CONSTRAINT uq_virtual_object_key UNIQUE(provider, external_key))"""))
        elif migration.migration_id == "20260829_0026_qos_samples":
            with engine.begin() as connection:
                connection.execute(text("""CREATE TABLE IF NOT EXISTS qos_samples (id SERIAL PRIMARY KEY, device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE, interface_id INTEGER REFERENCES interfaces(id) ON DELETE SET NULL, observed_at TIMESTAMP NOT NULL, tos INTEGER, dscp INTEGER, phb VARCHAR(40), traffic_class VARCHAR(80), queue_utilization DOUBLE PRECISION, queue_drops INTEGER NOT NULL DEFAULT 0, source VARCHAR(40) NOT NULL DEFAULT 'standard', raw_fields JSON NOT NULL DEFAULT '{}')"""))
        elif migration.migration_id == "20260829_0027_bgp_observations":
            with engine.begin() as connection:
                connection.execute(text("""CREATE TABLE IF NOT EXISTS bgp_observations (id SERIAL PRIMARY KEY, device_id INTEGER NOT NULL REFERENCES devices(id) ON DELETE CASCADE, neighbor VARCHAR(64) NOT NULL, state VARCHAR(40) NOT NULL, remote_as INTEGER, next_hop VARCHAR(64), prefixes INTEGER NOT NULL DEFAULT 0, as_path VARCHAR(1000), observed_at TIMESTAMP NOT NULL, raw_fields JSON NOT NULL DEFAULT '{}')"""))
        elif migration.migration_id == "20260829_0028_syslog_records":
            with engine.begin() as connection:
                connection.execute(text("""CREATE TABLE IF NOT EXISTS syslog_records (id SERIAL PRIMARY KEY, device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL, source_ip VARCHAR(64), facility INTEGER, severity INTEGER, hostname VARCHAR(255), application VARCHAR(48), process_id VARCHAR(128), message_id VARCHAR(32), structured_data TEXT, event_timestamp TIMESTAMP, message TEXT NOT NULL, raw_message TEXT NOT NULL, received_at TIMESTAMP NOT NULL, fingerprint VARCHAR(64))"""))
        elif migration.migration_id == "20260829_0029_syslog_correlation":
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE syslog_records ADD COLUMN IF NOT EXISTS interface_id INTEGER REFERENCES interfaces(id) ON DELETE SET NULL; ALTER TABLE syslog_records ADD COLUMN IF NOT EXISTS alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL; ALTER TABLE syslog_records ADD COLUMN IF NOT EXISTS incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL; CREATE TABLE IF NOT EXISTS syslog_correlation_rules (id SERIAL PRIMARY KEY, name VARCHAR(160) UNIQUE NOT NULL, pattern VARCHAR(500) NOT NULL, min_severity INTEGER, alert_severity VARCHAR(30) NOT NULL DEFAULT 'warning', cooldown_seconds INTEGER NOT NULL DEFAULT 300, enabled BOOLEAN NOT NULL DEFAULT TRUE, created_by INTEGER REFERENCES users(id) ON DELETE SET NULL, created_at TIMESTAMP NOT NULL)"))
        elif migration.migration_id == "20260902_0044_syslog_backend_readiness":
            with engine.begin() as connection:
                for column in (
                    "application VARCHAR(48)", "process_id VARCHAR(128)", "message_id VARCHAR(32)",
                    "structured_data TEXT", "fingerprint VARCHAR(64)",
                ):
                    connection.execute(text(f"ALTER TABLE syslog_records ADD COLUMN IF NOT EXISTS {column}"))
                connection.execute(text("ALTER TABLE syslog_records ALTER COLUMN event_timestamp DROP NOT NULL"))
                for column in ("device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL", "source_ip VARCHAR(64)", "hostname VARCHAR(255)", "facility INTEGER", "application VARCHAR(48)"):
                    connection.execute(text(f"ALTER TABLE syslog_correlation_rules ADD COLUMN IF NOT EXISTS {column}"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_syslog_fingerprint_received ON syslog_records (fingerprint, received_at)"))
                connection.execute(text("CREATE INDEX IF NOT EXISTS ix_syslog_hostname ON syslog_records (hostname)"))
        elif migration.migration_id == "20260910_0045_snmp_scalability_indexes":
            _ensure_snmp_scalability_indexes(engine)
        elif migration.migration_id == "20260917_0046_icmp_health_evidence":
            with engine.begin() as connection:
                connection.execute(text('ALTER TABLE devices ADD COLUMN IF NOT EXISTS "last_icmp_attempt_at" TIMESTAMP'))
                connection.execute(text('ALTER TABLE devices ADD COLUMN IF NOT EXISTS "last_icmp_status" VARCHAR(20)'))
        elif migration.migration_id == "20260922_0047_audit_outcome":
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS outcome VARCHAR(20) NOT NULL DEFAULT 'success'"))
        elif migration.migration_id == "20260831_0030_cmdb_reconciliation":
            _ensure_cmdb_reconciliation(engine)
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
