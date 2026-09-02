from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.models import Alert
from backend.models.rca import RCAIncident
from backend.rca.engine import correlate_alerts

router = APIRouter(prefix="/api/v1/rca", tags=["Root Cause Analysis"])


class AnalyzePayload(BaseModel):
    hours: int = Field(default=1, ge=1, le=720)
    alert_ids: list[int] | None = Field(default=None, max_length=500)


def _serialize(db: Session, incident: RCAIncident) -> dict[str, Any]:
    evidence = [{"id": e.id, "evidence_type": e.evidence_type, "alert_id": e.alert_id, "event_id": e.event_id, "relationship_id": e.relationship_id, "score": e.score, "reason": e.reason, "payload": e.payload} for e in incident.evidence]
    raw_ids = sorted({e["alert_id"] for e in evidence if e["alert_id"] is not None})
    alerts = db.query(Alert).filter(Alert.id.in_(raw_ids)).order_by(Alert.created_at.asc(), Alert.id.asc()).all() if raw_ids else []
    return {"id": incident.id, "root_kind": incident.root_kind, "root_label": incident.root_label, "root_device_id": incident.root_device_id, "root_interface_id": incident.root_interface_id, "root_ci_id": incident.root_ci_id, "confidence": incident.confidence, "impact_summary": incident.impact_summary, "window_start": incident.window_start, "window_end": incident.window_end, "created_at": incident.created_at, "updated_at": incident.updated_at, "evidence": evidence, "raw_alerts": [{"id": a.id, "device_id": a.device_id, "severity": a.severity, "title": a.title, "description": a.description, "status": a.status, "created_at": a.created_at} for a in alerts]}


@router.post("/analyze")
def analyze(payload: AnalyzePayload, db: Session = Depends(get_db), _: Any = Depends(require_permission("rca:execute"))):
    end = datetime.utcnow()
    incident = correlate_alerts(db, end - timedelta(hours=payload.hours), end, payload.alert_ids)
    return {"incident": _serialize(db, incident) if incident else None, "alerts_considered": len(payload.alert_ids or [])}


@router.get("/incidents")
def list_incidents(hours: int = Query(24, ge=1, le=720), skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db), _: Any = Depends(require_permission("rca:read"))):
    start = datetime.utcnow() - timedelta(hours=hours)
    incidents = db.query(RCAIncident).filter(RCAIncident.window_end >= start).order_by(RCAIncident.updated_at.desc()).offset(skip).limit(limit).all()
    return {"items": [_serialize(db, item) for item in incidents], "skip": skip, "limit": limit}


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: int, db: Session = Depends(get_db), _: Any = Depends(require_permission("rca:read"))):
    incident = db.query(RCAIncident).filter(RCAIncident.id == incident_id).first()
    if incident is None:
        raise HTTPException(status_code=404, detail="RCA incident not found")
    return _serialize(db, incident)
