from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.dependencies import require_permission

router = APIRouter(prefix="/api/v1/flows/analytics", tags=["Flow Analytics"])


def _where(device_id: int | None, site_id: int | None, start: datetime, end: datetime, protocol: str | None = None) -> tuple[str, dict[str, Any]]:
    clauses = ["f.flow_start >= :start", "f.flow_start < :end", "f.protocol IN ('sflow', 'ipfix')"]
    params: dict[str, Any] = {"start": start, "end": end}
    if device_id is not None:
        clauses.append("f.device_id = :device_id")
        params["device_id"] = device_id
    if site_id is not None:
        clauses.append("EXISTS (SELECT 1 FROM devices d WHERE d.id = f.device_id AND d.site_id = :site_id AND d.deleted_at IS NULL)")
        params["site_id"] = site_id
    if protocol is not None:
        if protocol not in {"sflow", "ipfix"}:
            raise ValueError("unsupported flow protocol")
        clauses.append("f.protocol = :protocol")
        params["protocol"] = protocol
    return " AND ".join(clauses), params


def _window(hours: int) -> tuple[datetime, datetime]:
    end = datetime.utcnow()
    return end - timedelta(hours=hours), end


def _rows(db: Session, dimension: str, where: str, params: dict[str, Any], limit: int, offset: int, *, protocol_filtered: bool):
    allowed = {
        "talkers": "COALESCE(f.src_ip, 'unknown')",
        "sources": "COALESCE(f.src_ip, 'unknown')",
        "destinations": "COALESCE(f.dst_ip, 'unknown')",
        "protocols": "COALESCE(f.ip_protocol::text, 'unknown')",
        "conversations": "CONCAT(COALESCE(f.src_ip, 'unknown'), ' -> ', COALESCE(f.dst_ip, 'unknown'))",
        "interfaces": "COALESCE(f.input_interface_id::text, f.output_interface_id::text, 'unknown')",
        "applications": "COALESCE(f.raw_fields ->> 'application', CONCAT('port:', COALESCE(f.dst_port::text, 'unknown')))" ,
    }
    expression = allowed[dimension]
    source_cte = _source_selection_cte(where, protocol_filtered=protocol_filtered)
    query = text(f"""
        {source_cte}
        SELECT {expression.replace('f.', 's.')} AS name,
               SUM(s.bytes)::bigint AS bytes, SUM(s.packets)::bigint AS packets,
               COUNT(*)::bigint AS flows,
               CASE WHEN COUNT(DISTINCT s.source) = 1 THEN MIN(s.source) ELSE 'unknown' END AS source,
               CASE WHEN COUNT(DISTINCT s.quality) = 1 THEN MIN(s.quality) ELSE 'unknown' END AS quality,
               CASE WHEN COUNT(DISTINCT s.sampled::text) = 1 THEN BOOL_OR(s.sampled) ELSE NULL END AS sampled,
               CASE WHEN COUNT(DISTINCT s.sampling_rate) = 1 THEN MIN(s.sampling_rate) ELSE NULL END AS sampling_rate
        FROM selected_flow_records s
        GROUP BY {expression.replace('f.', 's.')}
        ORDER BY bytes DESC, name
        LIMIT :limit OFFSET :offset
    """)
    return [dict(row) for row in db.execute(query, {**params, "limit": limit, "offset": offset}).mappings().all()]


def _source_selection_cte(where: str, *, protocol_filtered: bool) -> str:
    """Select one source for a flow identity while retaining raw records."""
    if protocol_filtered:
        return f"""
            WITH selected_flow_records AS (
                SELECT f.*, f.protocol AS source,
                       CASE
                         WHEN f.protocol = 'sflow' AND f.raw_fields ->> 'quality' = 'packet_sample' THEN 'estimated'
                         WHEN f.protocol = 'sflow' AND f.raw_fields ->> 'quality' = 'counter_sample' THEN 'counter'
                         WHEN f.protocol = 'ipfix' AND (f.raw_fields ->> 'quality' IN ('accounted', 'unsampled')
                              OR f.raw_fields -> 'ipfix' ->> 'sampled' = 'false') THEN 'accounted'
                         WHEN f.protocol = 'ipfix' AND (f.raw_fields ->> 'quality' = 'sampled'
                              OR f.raw_fields -> 'ipfix' ->> 'sampled' = 'true') THEN 'estimated'
                         ELSE 'unknown'
                       END AS quality,
                       CASE
                         WHEN f.protocol = 'sflow' AND f.raw_fields ->> 'quality' = 'packet_sample' THEN TRUE
                         WHEN f.protocol = 'ipfix' AND (f.raw_fields ->> 'quality' = 'sampled'
                              OR f.raw_fields -> 'ipfix' ->> 'sampled' = 'true') THEN TRUE
                         WHEN f.protocol = 'ipfix' AND (f.raw_fields ->> 'quality' IN ('accounted', 'unsampled')
                              OR f.raw_fields -> 'ipfix' ->> 'sampled' = 'false') THEN FALSE
                         ELSE NULL
                       END AS sampled,
                       CASE
                         WHEN f.protocol = 'sflow' AND f.raw_fields -> 'sflow' ->> 'sampling_rate' ~ '^[0-9]+$' THEN (f.raw_fields -> 'sflow' ->> 'sampling_rate')::bigint
                         WHEN f.protocol = 'ipfix' AND f.raw_fields -> 'ipfix' ->> 'sampling_rate' ~ '^[0-9]+$' THEN (f.raw_fields -> 'ipfix' ->> 'sampling_rate')::bigint
                         ELSE NULL
                       END AS sampling_rate
                FROM flow_records f
                WHERE {where}
            )
        """
    return f"""
        WITH classified_flow_records AS (
            SELECT f.*, f.protocol AS source,
                   CASE
                     WHEN f.protocol = 'sflow' AND f.raw_fields ->> 'quality' = 'packet_sample' THEN 'estimated'
                     WHEN f.protocol = 'sflow' AND f.raw_fields ->> 'quality' = 'counter_sample' THEN 'counter'
                     WHEN f.protocol = 'ipfix' AND (f.raw_fields ->> 'quality' IN ('accounted', 'unsampled')
                          OR f.raw_fields -> 'ipfix' ->> 'sampled' = 'false') THEN 'accounted'
                     WHEN f.protocol = 'ipfix' AND (f.raw_fields ->> 'quality' = 'sampled'
                          OR f.raw_fields -> 'ipfix' ->> 'sampled' = 'true') THEN 'estimated'
                     ELSE 'unknown'
                   END AS quality,
                   CASE
                     WHEN f.protocol = 'sflow' AND f.raw_fields ->> 'quality' = 'packet_sample' THEN TRUE
                     WHEN f.protocol = 'ipfix' AND (f.raw_fields ->> 'quality' = 'sampled'
                          OR f.raw_fields -> 'ipfix' ->> 'sampled' = 'true') THEN TRUE
                     WHEN f.protocol = 'ipfix' AND (f.raw_fields ->> 'quality' IN ('accounted', 'unsampled')
                          OR f.raw_fields -> 'ipfix' ->> 'sampled' = 'false') THEN FALSE
                     ELSE NULL
                   END AS sampled,
                   CASE
                     WHEN f.protocol = 'sflow' AND f.raw_fields -> 'sflow' ->> 'sampling_rate' ~ '^[0-9]+$' THEN (f.raw_fields -> 'sflow' ->> 'sampling_rate')::bigint
                     WHEN f.protocol = 'ipfix' AND f.raw_fields -> 'ipfix' ->> 'sampling_rate' ~ '^[0-9]+$' THEN (f.raw_fields -> 'ipfix' ->> 'sampling_rate')::bigint
                     ELSE NULL
                   END AS sampling_rate
            FROM flow_records f
            WHERE {where}
        ), ranked_flow_records AS (
            SELECT c.*, ROW_NUMBER() OVER (
                PARTITION BY COALESCE(c.device_id::text, c.exporter_ip),
                    date_trunc('minute', COALESCE(c.flow_start, c.received_at)),
                    c.src_ip, c.dst_ip, c.src_port, c.dst_port, c.ip_protocol,
                    c.input_interface_id, c.output_interface_id
                ORDER BY CASE
                    WHEN c.source = 'ipfix' AND c.quality = 'accounted' THEN 1
                    WHEN c.source = 'ipfix' AND c.quality = 'estimated' THEN 2
                    WHEN c.source = 'sflow' AND c.quality = 'estimated' THEN 3
                    WHEN c.source = 'sflow' AND c.quality = 'counter' THEN 4
                    ELSE 5
                END, c.id
            ) AS source_rank
            FROM classified_flow_records c
        ), selected_flow_records AS (
            SELECT * FROM ranked_flow_records WHERE source_rank = 1
        )
    """


def _analytics(dimension: str, hours: int, device_id: int | None, site_id: int | None, protocol: str | None, limit: int, page: int, db: Session) -> dict[str, Any]:
    start, end = _window(hours)
    where, params = _where(device_id, site_id, start, end, protocol)
    offset = (page - 1) * limit
    return {"items": _rows(db, dimension, where, params, limit, offset, protocol_filtered=protocol is not None), "page": page, "page_size": limit,
            "filters": {"hours": hours, "device_id": device_id, "site_id": site_id, "protocol": protocol}, "from": start.isoformat(), "to": end.isoformat()}


def _endpoint(dimension: str):
    def handler(hours: int = Query(24, ge=1, le=720), device_id: int | None = None, site_id: int | None = None,
                protocol: str | None = Query(None, pattern="^(sflow|ipfix)$"),
                page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                db: Session = Depends(get_db), _: Any = Depends(require_permission("flows:read"))):
        return _analytics(dimension, hours, device_id, site_id, protocol, page_size, page, db)
    return handler


for _name in ("talkers", "sources", "destinations", "applications", "protocols", "conversations", "interfaces"):
    router.add_api_route(f"/{_name}", _endpoint(_name), methods=["GET"], name=f"flow_{_name}")


@router.get("/records")
def flow_records(
    hours: int = Query(24, ge=1, le=720), device_id: int | None = None, site_id: int | None = None,
    protocol: str | None = Query(None, pattern="^(sflow|ipfix)$"),
    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db), _: Any = Depends(require_permission("flows:read")),
) -> dict[str, Any]:
    start, end = _window(hours)
    where, params = _where(device_id, site_id, start, end, protocol)
    rows = db.execute(text(f"""
        SELECT f.id, f.device_id, d.hostname AS device_name, f.exporter_ip,
               f.input_interface_id AS input_ifindex,
               f.raw_fields -> 'correlation' ->> 'input_interface_name' AS input_interface_name,
               f.output_interface_id AS output_ifindex,
               f.raw_fields -> 'correlation' ->> 'output_interface_name' AS output_interface_name,
               f.protocol, f.source_version, f.flow_start, f.flow_end,
               f.src_ip, f.dst_ip, f.src_port, f.dst_port, f.ip_protocol,
               f.bytes, f.packets
        FROM flow_records f
        LEFT JOIN devices d ON d.id = f.device_id
        WHERE {where}
        ORDER BY f.flow_start DESC, f.id DESC
        LIMIT :limit OFFSET :offset
    """), {**params, "limit": page_size, "offset": (page - 1) * page_size}).mappings().all()
    return {"items": [dict(row) for row in rows], "page": page, "page_size": page_size,
            "from": start.isoformat(), "to": end.isoformat()}


@router.get("/trends")
def flow_trends(hours: int = Query(24, ge=1, le=720), device_id: int | None = None, site_id: int | None = None,
                protocol: str | None = Query(None, pattern="^(sflow|ipfix)$"),
                bucket: str = Query("hour", pattern="^(hour|day)$"), db: Session = Depends(get_db),
                _: Any = Depends(require_permission("flows:read"))):
    start, end = _window(hours)
    where, params = _where(device_id, site_id, start, end, protocol)
    source_cte = _source_selection_cte(where, protocol_filtered="protocol" in params)
    rows = db.execute(text(f"""
        {source_cte}
        SELECT date_trunc(:bucket, s.flow_start) AS timestamp,
               SUM(s.bytes)::bigint AS bytes, SUM(s.packets)::bigint AS packets,
               COUNT(*)::bigint AS flows
        FROM selected_flow_records s
        GROUP BY 1 ORDER BY 1
    """), {**params, "bucket": bucket}).mappings().all()
    return {"items": [dict(row) for row in rows], "bucket": bucket, "from": start.isoformat(), "to": end.isoformat()}
