from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.dependencies import require_permission

router = APIRouter(prefix="/api/v1/flows/analytics", tags=["Flow Analytics"])


def _where(device_id: int | None, site_id: int | None, start: datetime, end: datetime) -> tuple[str, dict[str, Any]]:
    clauses = ["f.flow_start >= :start", "f.flow_start < :end"]
    params: dict[str, Any] = {"start": start, "end": end}
    if device_id is not None:
        clauses.append("f.device_id = :device_id")
        params["device_id"] = device_id
    if site_id is not None:
        clauses.append("EXISTS (SELECT 1 FROM devices d WHERE d.id = f.device_id AND d.site_id = :site_id AND d.deleted_at IS NULL)")
        params["site_id"] = site_id
    return " AND ".join(clauses), params


def _window(hours: int) -> tuple[datetime, datetime]:
    end = datetime.utcnow()
    return end - timedelta(hours=hours), end


def _rows(db: Session, dimension: str, where: str, params: dict[str, Any], limit: int, offset: int):
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
    query = text(f"""
        SELECT {expression} AS name, SUM(f.bytes)::bigint AS bytes,
               SUM(f.packets)::bigint AS packets, COUNT(*)::bigint AS flows
        FROM flow_records f
        WHERE {where}
        GROUP BY {expression}
        ORDER BY bytes DESC, name
        LIMIT :limit OFFSET :offset
    """)
    return [dict(row) for row in db.execute(query, {**params, "limit": limit, "offset": offset}).mappings().all()]


def _analytics(dimension: str, hours: int, device_id: int | None, site_id: int | None, limit: int, page: int, db: Session) -> dict[str, Any]:
    start, end = _window(hours)
    where, params = _where(device_id, site_id, start, end)
    offset = (page - 1) * limit
    return {"items": _rows(db, dimension, where, params, limit, offset), "page": page, "page_size": limit,
            "filters": {"hours": hours, "device_id": device_id, "site_id": site_id}, "from": start.isoformat(), "to": end.isoformat()}


def _endpoint(dimension: str):
    def handler(hours: int = Query(24, ge=1, le=720), device_id: int | None = None, site_id: int | None = None,
                page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                db: Session = Depends(get_db), _: Any = Depends(require_permission("flows:read"))):
        return _analytics(dimension, hours, device_id, site_id, page_size, page, db)
    return handler


for _name in ("talkers", "sources", "destinations", "applications", "protocols", "conversations", "interfaces"):
    router.add_api_route(f"/{_name}", _endpoint(_name), methods=["GET"], name=f"flow_{_name}")


@router.get("/trends")
def flow_trends(hours: int = Query(24, ge=1, le=720), device_id: int | None = None, site_id: int | None = None,
                bucket: str = Query("hour", pattern="^(hour|day)$"), db: Session = Depends(get_db),
                _: Any = Depends(require_permission("flows:read"))):
    start, end = _window(hours)
    where, params = _where(device_id, site_id, start, end)
    rows = db.execute(text(f"""
        SELECT date_trunc(:bucket, f.flow_start) AS timestamp,
               SUM(f.bytes)::bigint AS bytes, SUM(f.packets)::bigint AS packets,
               COUNT(*)::bigint AS flows
        FROM flow_records f WHERE {where}
        GROUP BY 1 ORDER BY 1
    """), {**params, "bucket": bucket}).mappings().all()
    return {"items": [dict(row) for row in rows], "bucket": bucket, "from": start.isoformat(), "to": end.isoformat()}
