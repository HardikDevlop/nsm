import csv
import logging
from datetime import datetime
from io import StringIO

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.models import AvailabilityReport, Device, User
from backend.services.availability import calculate_availability, normalize_time, outage_views

router = APIRouter(prefix="/api/v1/availability", tags=["Availability"])
logger = logging.getLogger(__name__)


class AvailabilityPayload(BaseModel):
    entity_type: str = Field(pattern="^(device|interface|site|business_service)$")
    entity_id: int = Field(gt=0)
    start: datetime
    end: datetime
    sla_target: float = Field(default=99.0, ge=0, le=100)


def view(report: AvailabilityReport, db: Session | None = None, include_outages: bool = False) -> dict:
    result = {"id": report.id, "entity_type": report.entity_type, "entity_id": report.entity_id, "window_start": report.window_start, "window_end": report.window_end, "total_seconds": report.total_seconds, "requested_duration_seconds": report.total_seconds, "monitored_duration_seconds": report.monitored_duration_seconds, "uptime_seconds": report.uptime_seconds, "downtime_seconds": report.downtime_seconds, "unknown_seconds": report.unknown_seconds, "planned_downtime_seconds": report.planned_downtime_seconds, "unplanned_downtime_seconds": report.unplanned_downtime_seconds, "coverage_percent": report.coverage_percent, "availability_percent": report.availability_percent, "outage_count": report.outage_count, "last_outage": None, "current_outage": None, "mttr_seconds": report.mttr_seconds, "mtbf_seconds": report.mtbf_seconds, "sla_target_percent": report.sla_target_percent, "achieved_percent": report.availability_percent, "sla_breached": report.sla_breached, "downtime_reasons": report.downtime_reasons, "generated_by": report.generated_by, "generated_at": report.generated_at}
    if report.entity_type == "device" and db is not None:
        device = db.query(Device).filter(Device.id == report.entity_id).first()
        if device: result.update({"device_name": device.hostname, "ip_address": device.ip_address, "current_status": device.status})
    if db is not None and (include_outages or report.outage_count):
        outages = outage_views(db, report); result["outages"] = outages; result["current_outage"] = next((row for row in reversed(outages) if row["ongoing"]), None); result["last_outage"] = outages[-1] if outages else None
    return result


@router.post("/reports", status_code=201)
def generate(payload: AvailabilityPayload, db: Session = Depends(get_db), user: User = Depends(require_permission("availability:read"))):
    try:
        report = calculate_availability(db, payload.entity_type, payload.entity_id, payload.start, payload.end, user.id, payload.sla_target)
    except (ValueError, LookupError) as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    except IntegrityError as exc:
        db.rollback()
        constraint = str(getattr(exc, "orig", exc))
        logger.exception("Availability report persistence conflict for %s/%s: %s", payload.entity_type, payload.entity_id, constraint)
        # A concurrent request may have won the logical-window insert. Re-run
        # the same reconciliation against that committed row instead of
        # turning an idempotent retry into a user-visible conflict.
        if "uq_availability_report_window" in constraint or "duplicate key" in constraint.lower():
            try:
                report = calculate_availability(db, payload.entity_type, payload.entity_id, payload.start, payload.end, user.id, payload.sla_target)
                db.commit(); db.refresh(report)
                return view(report, db, True)
            except Exception:
                db.rollback()
                logger.exception("Availability report idempotent retry failed for %s/%s", payload.entity_type, payload.entity_id)
        raise HTTPException(409, "Availability report could not be persisted") from None
    except Exception:
        db.rollback()
        logger.exception("Availability report generation failed for %s/%s", payload.entity_type, payload.entity_id)
        raise HTTPException(500, "Unable to generate availability report") from None
    try:
        db.commit(); db.refresh(report)
    except IntegrityError:
        db.rollback()
        logger.exception("Availability report commit conflict for %s/%s", payload.entity_type, payload.entity_id)
        raise HTTPException(409, "Availability report could not be persisted") from None
    except Exception:
        db.rollback()
        logger.exception("Availability report commit failed for %s/%s", payload.entity_type, payload.entity_id)
        raise HTTPException(500, "Unable to generate availability report") from None
    return view(report, db, True)


@router.get("/reports")
def history(entity_type: str | None = None, entity_id: int | None = None, skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), _: User = Depends(require_permission("availability:read"))):
    query = db.query(AvailabilityReport)
    if entity_type: query = query.filter_by(entity_type=entity_type)
    if entity_id: query = query.filter_by(entity_id=entity_id)
    rows = query.order_by(AvailabilityReport.generated_at.desc()).offset(skip).limit(limit).all()
    return {"items": [view(row, db) for row in rows], "skip": skip, "limit": limit}


@router.get("/reports/export.csv")
def export_csv(entity_type: str | None = None, entity_id: int | None = None, db: Session = Depends(get_db), _: User = Depends(require_permission("availability:read"))):
    query = db.query(AvailabilityReport)
    if entity_type: query = query.filter_by(entity_type=entity_type)
    if entity_id: query = query.filter_by(entity_id=entity_id)
    output = StringIO(); writer = csv.writer(output)
    writer.writerow(["entity_type", "entity_id", "window_start", "window_end", "availability_percent", "coverage_percent", "uptime_seconds", "downtime_seconds", "unknown_seconds", "planned_downtime_seconds", "unplanned_downtime_seconds", "outage_count", "sla_target_percent", "sla_breached"])
    for row in query.order_by(AvailabilityReport.generated_at.desc()).all():
        writer.writerow([row.entity_type, row.entity_id, row.window_start, row.window_end, row.availability_percent, row.coverage_percent, row.uptime_seconds, row.downtime_seconds, row.unknown_seconds, row.planned_downtime_seconds, row.unplanned_downtime_seconds, row.outage_count, row.sla_target_percent, row.sla_breached])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=availability-report.csv"})


@router.get("/reports/{report_id}")
def detail(report_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("availability:read"))):
    report = db.query(AvailabilityReport).filter(AvailabilityReport.id == report_id).first()
    if not report: raise HTTPException(404, "Availability report not found")
    return view(report, db, True)
