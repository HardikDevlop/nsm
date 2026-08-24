"""Run EXPLAIN ANALYZE for common NMS query patterns.

Usage:
    cd /home/agnigate/Desktop/NMS/hardik
    python3 -m backend.query_audit
    python3 -m backend.query_audit overview
    python3 -m backend.query_audit device_metrics
"""

from __future__ import annotations

import sys
from collections.abc import Iterable

from sqlalchemy import text

from backend.database.session import engine


QUERY_PROFILES: dict[str, tuple[str, str]] = {
    "overview": (
        "Dashboard overview alerts query",
        """
        SELECT id, device_id, severity, title, status, created_at
        FROM alerts
        WHERE deleted_at IS NULL AND status IN ('open', 'acknowledged')
        ORDER BY created_at DESC
        LIMIT 50
        """,
    ),
    "device_metrics": (
        "Latest device metrics for dashboard/server pages",
        """
        SELECT id, device_id, cpu_usage, memory_usage, latency, bandwidth_usage, created_at
        FROM device_metrics
        ORDER BY created_at DESC
        LIMIT 200
        """,
    ),
    "device_metrics_by_device": (
        "Per-device metrics history",
        """
        SELECT id, device_id, cpu_usage, memory_usage, latency, bandwidth_usage, created_at
        FROM device_metrics
        WHERE device_id = 1
        ORDER BY created_at DESC
        LIMIT 200
        """,
    ),
    "events": (
        "Recent events feed",
        """
        SELECT id, device_id, event_type, description, timestamp
        FROM events
        WHERE deleted_at IS NULL
        ORDER BY timestamp DESC
        LIMIT 50
        """,
    ),
    "interfaces_by_device": (
        "Interface list for one device",
        """
        SELECT id, device_id, interface_name, status, traffic_in, traffic_out, last_updated
        FROM interfaces
        WHERE device_id = 1
        ORDER BY last_updated DESC
        LIMIT 100
        """,
    ),
    "polling_history": (
        "Recent SNMP polling history",
        """
        SELECT id, device_id, collector, status, created_at
        FROM polling_history
        WHERE device_id = 1
        ORDER BY created_at DESC
        LIMIT 200
        """,
    ),
    "snmp_devices": (
        "SNMP device list page with credential existence filter",
        """
        SELECT d.id, d.hostname, d.ip_address, d.status, d.last_seen
        FROM devices AS d
        WHERE d.deleted_at IS NULL
          AND EXISTS (
              SELECT 1
              FROM device_credentials AS dc
              WHERE dc.device_id = d.id
          )
        ORDER BY d.id ASC
        LIMIT 50
        """,
    ),
    "snmp_device_details": (
        "SNMP device details primary record lookup",
        """
        SELECT d.id, d.hostname, d.ip_address, d.model, d.serial_number, d.status
        FROM devices AS d
        WHERE d.id = 1 AND d.deleted_at IS NULL
        LIMIT 1
        """,
    ),
    "snmp_topology_cache": (
        "SNMP topology capability cache lookup",
        """
        SELECT dc.device_id, dc.capability_detail
        FROM device_capabilities AS dc
        WHERE dc.device_id IN (1, 2, 3)
        """,
    ),
}


def _iter_profiles(selection: str | None) -> Iterable[tuple[str, tuple[str, str]]]:
    if selection:
        if selection not in QUERY_PROFILES:
            available = ", ".join(sorted(QUERY_PROFILES))
            raise SystemExit(f"Unknown profile '{selection}'. Available: {available}")
        return ((selection, QUERY_PROFILES[selection]),)
    return QUERY_PROFILES.items()


def main() -> int:
    selection = sys.argv[1] if len(sys.argv) > 1 else None
    for profile_name, (description, sql) in _iter_profiles(selection):
        print(f"\n=== {profile_name} ===")
        print(description)
        with engine.connect() as connection:
            rows = connection.execute(
                text(f"EXPLAIN (ANALYZE, BUFFERS, VERBOSE, FORMAT TEXT) {sql}")
            ).fetchall()
        for row in rows:
            print(row[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
