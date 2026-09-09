"""Safely reset NMS operational data without touching RBAC.

This utility intentionally uses DELETE, never DROP/TRUNCATE, because the
database contains shared foreign keys and user-owned RBAC data. It is dry-run
by default. Execute only after reviewing the target list:

    PYTHONPATH=. python -m backend.database.reset_operational_data --execute
"""

from __future__ import annotations

import argparse
from collections import defaultdict, deque
from dataclasses import dataclass

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from backend.database.session import engine


RBAC_TABLES = frozenset({"users", "roles", "permissions", "role_permissions"})
AUDIT_TABLES = frozenset({"audit_logs"})

# Rows in these tables are telemetry, discovery state, device configuration,
# or operational workflow state. The list is deliberately explicit for root
# domain tables; device-linked association tables are discovered below.
EXPLICIT_OPERATIONAL_TABLES = frozenset({
    "devices", "device_credentials", "interfaces", "monitoring_jobs",
    "device_metrics", "device_status_history", "alerts", "events",
    "notifications", "reports", "thresholds", "snmp_traps", "alarms",
    "device_inventory", "snmp_credentials", "device_performance",
    "cpu_statistics", "memory_statistics", "storage_statistics",
    "environment_statistics", "power_statistics", "poe_statistics",
    "vlan_information", "lldp_neighbors", "routing_table", "system_health",
    "polling_history", "interface_statistics", "oid_cache",
    "device_interfaces", "device_capabilities", "device_identity",
    "monitoring_configs", "latest_cpu", "latest_memory", "latest_storage",
    "latest_interface", "latest_environment", "manual_topology_snapshots",
    "manual_topology_changes", "linux_servers", "linux_server_credentials",
    "linux_server_snmp_credentials", "linux_server_monitoring_configs",
    "linux_server_metric_samples", "linux_server_current_metrics",
    "linux_server_interfaces", "linux_server_disks", "linux_security_events",
    "flow_records", "sflow_counter_samples", "apm_metrics", "apm_metric_samples",
    "apm_transactions", "apm_dependencies", "availability_outages",
    "availability_reports", "virtual_objects", "qos_samples",
    "bgp_observations", "syslog_records", "syslog_correlation_rules",
    "rca_incidents", "rca_evidence", "incidents", "incident_alerts",
    "incident_comments", "incident_attachments", "incident_history",
    "incident_sla_timers", "incident_sla_history", "problems",
    "problem_incidents", "problem_history", "change_requests", "change_cis",
    "change_incidents", "change_problems", "change_history",
    "device_configuration_versions", "configuration_comparisons",
    "configuration_compliance_violations",
})


@dataclass(frozen=True)
class SchemaSnapshot:
    tables: tuple[str, ...]
    columns: tuple[tuple[str, tuple[str, ...]], ...]


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _schema_snapshot(inspector) -> SchemaSnapshot:
    tables = tuple(sorted(inspector.get_table_names()))
    columns = tuple((table, tuple(column["name"] for column in inspector.get_columns(table))) for table in tables)
    return SchemaSnapshot(tables=tables, columns=columns)


def _rbac_snapshot(connection, inspector) -> dict[str, tuple[tuple[object, ...], ...]]:
    snapshot = {}
    for table in sorted(RBAC_TABLES):
        if table not in inspector.get_table_names():
            raise RuntimeError(f"Required RBAC table is missing: {table}")
        columns = [column["name"] for column in inspector.get_columns(table)]
        order = ", ".join(_quote(column) for column in columns)
        rows = connection.execute(text(f"SELECT {order} FROM {_quote(table)} ORDER BY 1")).all()
        snapshot[table] = tuple(tuple(row) for row in rows)
    return snapshot


def _target_tables(inspector) -> set[str]:
    existing = set(inspector.get_table_names())
    targets = {table for table in EXPLICIT_OPERATIONAL_TABLES if table in existing}

    # Remove device-owned links too, but never infer a protected table.
    for table in existing - RBAC_TABLES - AUDIT_TABLES:
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "device_id" in columns and table not in {"sites", "organizations"}:
            targets.add(table)

    forbidden = targets & (RBAC_TABLES | AUDIT_TABLES)
    if forbidden:
        raise RuntimeError(f"Refusing unsafe reset target(s): {sorted(forbidden)}")
    return targets


def _delete_order(inspector, targets: set[str]) -> list[str]:
    children: dict[str, set[str]] = defaultdict(set)
    indegree = {table: 0 for table in targets}
    for table in targets:
        for fk in inspector.get_foreign_keys(table):
            parent = fk.get("referred_table")
            if parent in targets and parent != table:
                # A table can have multiple FK columns pointing to the same
                # parent. The graph edge is unique even when the constraints
                # are not, otherwise the topological sort reports a false
                # cycle and refuses a safe child-first delete.
                if parent not in children[table]:
                    children[table].add(parent)
                    indegree[parent] += 1

    queue = deque(sorted(table for table, degree in indegree.items() if degree == 0))
    order = []
    while queue:
        table = queue.popleft()
        order.append(table)
        for parent in sorted(children[table]):
            indegree[parent] -= 1
            if indegree[parent] == 0:
                queue.append(parent)
    if len(order) != len(targets):
        cycle = sorted(table for table, degree in indegree.items() if degree)
        raise RuntimeError(f"Cannot safely order deletes because of FK cycle(s): {cycle}")
    return order


def reset_operational_data(db_engine: Engine, execute: bool = False) -> dict[str, int]:
    inspector = inspect(db_engine)
    before_schema = _schema_snapshot(inspector)
    targets = _target_tables(inspector)
    order = _delete_order(inspector, targets)
    counts: dict[str, int] = {}

    with db_engine.begin() as connection:
        before_rbac = _rbac_snapshot(connection, inspector)
        for table in order:
            counts[table] = int(connection.execute(text(f"SELECT count(*) FROM {_quote(table)}")).scalar_one())
        if not execute:
            return counts

        for table in order:
            connection.execute(text(f"DELETE FROM {_quote(table)}"))

        after_rbac = _rbac_snapshot(connection, inspector)
        after_schema = _schema_snapshot(inspect(connection))
        if after_rbac != before_rbac:
            raise RuntimeError("RBAC verification failed; transaction rolled back")
        if after_schema != before_schema:
            raise RuntimeError("Schema verification failed; transaction rolled back")
        remaining = {
            table: int(connection.execute(text(f"SELECT count(*) FROM {_quote(table)}")).scalar_one())
            for table in order
        }
        non_empty = {table: count for table, count in remaining.items() if count}
        if non_empty:
            raise RuntimeError(f"Operational reset verification failed: {non_empty}")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", help="commit the guarded DELETE transaction")
    args = parser.parse_args()
    counts = reset_operational_data(engine, execute=args.execute)
    mode = "executed" if args.execute else "dry-run"
    print(f"Operational reset {mode}; {len(counts)} tables selected")
    for table, count in counts.items():
        print(f"{table}: {count}")


if __name__ == "__main__":
    main()
