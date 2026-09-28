from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.apm.service import APMMetric, cleanup_metrics, ingest_metrics
from backend.database.session import get_db
from backend.dependencies import require_permission

router = APIRouter(prefix="/api/v1/apm", tags=["APM"])




class APMMetricPayload(BaseModel):
    application_id: int = Field(gt=0)
    service_id: int = Field(gt=0)
    transaction_id: int | None = Field(default=None, gt=0)
    device_id: int | None = Field(default=None, gt=0)
    site_id: int | None = Field(default=None, gt=0)
    observed_at: datetime
    response_time_ms: float = Field(ge=0)
    request_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    slow_transaction_count: int = Field(default=0, ge=0)
    availability_percent: float = Field(default=100, ge=0, le=100)


class APMMetricBatch(BaseModel):
    metrics: list[APMMetricPayload] = Field(min_length=1, max_length=500)


def _window(hours: int) -> tuple[datetime, datetime]:
    end = datetime.utcnow()
    return end - timedelta(hours=hours), end


def _filters(device_id: int | None, site_id: int | None, application_id: int | None, service_id: int | None,
             start: datetime, end: datetime) -> tuple[str, dict[str, Any]]:
    clauses = ["m.observed_at >= :start", "m.observed_at < :end"]
    params: dict[str, Any] = {"start": start, "end": end}
    for column, value in (("m.device_id", device_id), ("m.site_id", site_id),
                          ("m.application_id", application_id), ("m.service_id", service_id)):
        if value is not None:
            clauses.append(f"{column} = :{column[2:]}")
            params[column[2:]] = value
    return " AND ".join(clauses), params


@router.post("/metrics")
def ingest_metric_batch(payload: APMMetricBatch, db: Session = Depends(get_db), _: Any = Depends(require_permission("apm:ingest"))):
    now = datetime.utcnow()
    accepted = ingest_metrics(db, [APMMetric(**metric.model_dump()) for metric in payload.metrics], now)
    return {"accepted": accepted, "submitted": len(payload.metrics)}


@router.get("/applications")
def apm_applications(db: Session = Depends(get_db), _: Any = Depends(require_permission("apm:read"))):
    rows = db.execute(text("""
        SELECT id, name, environment FROM apm_applications
        WHERE deleted_at IS NULL AND enabled = TRUE ORDER BY name, environment
    """)).mappings().all()
    return [dict(row) for row in rows]


@router.get("/services")
def apm_services(application_id: int | None = None, db: Session = Depends(get_db),
                 _: Any = Depends(require_permission("apm:read"))):
    clauses = ["s.deleted_at IS NULL", "s.enabled = TRUE"]
    params: dict[str, Any] = {}
    if application_id is not None:
        clauses.append("s.application_id = :application_id")
        params["application_id"] = application_id
    rows = db.execute(text(f"""
        SELECT s.id, s.application_id, s.name, s.service_key, s.device_id, s.site_id,
               a.name AS application_name
        FROM apm_services s JOIN apm_applications a ON a.id = s.application_id
        WHERE {' AND '.join(clauses)} AND a.deleted_at IS NULL
        ORDER BY a.name, s.name
    """), params).mappings().all()
    return [dict(row) for row in rows]


@router.get("/overview")
def apm_overview(hours: int = Query(24, ge=1, le=720), device_id: int | None = None,
                 site_id: int | None = None, application_id: int | None = None,
                 service_id: int | None = None, page: int = Query(1, ge=1),
                 page_size: int = Query(50, ge=1, le=500), db: Session = Depends(get_db),
                 _: Any = Depends(require_permission("apm:read"))):
    start, end = _window(hours)
    where, params = _filters(device_id, site_id, application_id, service_id, start, end)
    params.update({"limit": page_size, "offset": (page - 1) * page_size})
    rows = db.execute(text(f"""
        SELECT m.application_id, m.service_id, a.name AS application_name,
               s.name AS service_name, SUM(m.request_count)::bigint AS request_count,
               SUM(m.error_count)::bigint AS error_count,
               ROUND((SUM(m.response_time_ms * m.request_count) /
                 NULLIF(SUM(m.request_count), 0))::numeric, 3) AS response_time_ms,
               SUM(m.slow_transaction_count)::bigint AS slow_transaction_count,
               ROUND(AVG(m.availability_percent)::numeric, 3) AS availability_percent
        FROM apm_metric_samples m
        JOIN apm_applications a ON a.id = m.application_id
        JOIN apm_services s ON s.id = m.service_id
        WHERE {where} AND a.deleted_at IS NULL AND s.deleted_at IS NULL
        GROUP BY m.application_id, m.service_id, a.name, s.name
        ORDER BY request_count DESC, m.service_id
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()
    items = [dict(row) for row in rows]
    for item in items:
        item["error_rate"] = (item["error_count"] / item["request_count"] * 100) if item["request_count"] else 0
    return {"items": items, "page": page, "page_size": page_size,
            "from": start.isoformat(), "to": end.isoformat(),
            "filters": {"hours": hours, "device_id": device_id, "site_id": site_id,
                        "application_id": application_id, "service_id": service_id}}


@router.get("/services/{service_id}/metrics")
def service_metrics(service_id: int, hours: int = Query(24, ge=1, le=720),
                    transaction_id: int | None = None, page: int = Query(1, ge=1),
                    page_size: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
                    _: Any = Depends(require_permission("apm:read"))):
    start, end = _window(hours)
    clauses = ["m.service_id = :service_id", "m.observed_at >= :start", "m.observed_at < :end"]
    params: dict[str, Any] = {"service_id": service_id, "start": start, "end": end,
                              "limit": page_size, "offset": (page - 1) * page_size}
    if transaction_id is not None:
        clauses.append("m.transaction_id = :transaction_id")
        params["transaction_id"] = transaction_id
    rows = db.execute(text(f"""
        SELECT observed_at, transaction_id, response_time_ms, request_count,
               error_count, slow_transaction_count, availability_percent
        FROM apm_metric_samples m WHERE {' AND '.join(clauses)}
        ORDER BY observed_at DESC LIMIT :limit OFFSET :offset
    """), params).mappings().all()
    return {"items": [dict(row) for row in rows], "page": page, "page_size": page_size,
            "from": start.isoformat(), "to": end.isoformat(), "service_id": service_id}


@router.get("/dependencies")
def apm_dependencies(hours: int = Query(24, ge=1, le=720), device_id: int | None = None,
                     site_id: int | None = None, service_id: int | None = None,
                     page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=500),
                     db: Session = Depends(get_db), _: Any = Depends(require_permission("apm:read"))):
    start, end = _window(hours)
    clauses = ["d.observed_at >= :start", "d.observed_at < :end"]
    params: dict[str, Any] = {"start": start, "end": end, "limit": page_size, "offset": (page - 1) * page_size}
    for column, value in (("d.device_id", device_id), ("d.site_id", site_id), ("d.source_service_id", service_id)):
        if value is not None:
            clauses.append(f"{column} = :{column[2:]}")
            params[column[2:]] = value
    rows = db.execute(text(f"""
        SELECT d.source_service_id, source.name AS source_service_name,
               d.target_service_id, d.target_name, d.dependency_type,
               SUM(d.call_count)::bigint AS call_count,
               SUM(d.error_count)::bigint AS error_count,
               ROUND((SUM(d.response_time_ms * d.call_count) /
                 NULLIF(SUM(d.call_count), 0))::numeric, 3) AS response_time_ms
        FROM apm_dependencies d JOIN apm_services source ON source.id = d.source_service_id
        WHERE {' AND '.join(clauses)}
        GROUP BY d.source_service_id, source.name, d.target_service_id,
                 d.target_name, d.dependency_type
        ORDER BY call_count DESC, d.target_name
        LIMIT :limit OFFSET :offset
    """), params).mappings().all()
    items = [dict(row) for row in rows]
    for item in items:
        item["error_rate"] = (item["error_count"] / item["call_count"] * 100) if item["call_count"] else 0
    return {"items": items, "page": page, "page_size": page_size,
            "from": start.isoformat(), "to": end.isoformat(),
            "filters": {"hours": hours, "device_id": device_id, "site_id": site_id, "service_id": service_id}}


@router.post("/retention/run")
def run_apm_retention(retention_days: int = Query(30, ge=1, le=3650), db: Session = Depends(get_db),
                      _: Any = Depends(require_permission("apm:manage"))):
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    deleted = cleanup_metrics(db, cutoff)
    return {"deleted": deleted, "retention_days": retention_days, "cutoff": cutoff.isoformat()}
