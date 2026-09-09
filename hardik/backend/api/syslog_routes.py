import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.models import SyslogRecord, SyslogCorrelationRule, User
from backend.syslog import cleanup_syslog

router = APIRouter(prefix="/api/v1/syslog", tags=["Syslog"])


@router.get("/records")
def records(start: datetime | None = None, end: datetime | None = None, after: datetime | None = None, device_id: int | None = None, source_ip: str | None = None, hostname: str | None = None, severity: int | None = Query(None, ge=0, le=7), facility: int | None = Query(None, ge=0), application: str | None = None, pattern: str | None = None, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0), db: Session = Depends(get_db), _: User = Depends(require_permission("syslog:read"))):
    if start is None: start = after
    query = db.query(SyslogRecord)
    if start is not None: query = query.filter(SyslogRecord.event_timestamp >= start)
    if end is not None: query = query.filter(SyslogRecord.event_timestamp <= end)
    if device_id is not None: query = query.filter(SyslogRecord.device_id == device_id)
    if source_ip: query = query.filter(SyslogRecord.source_ip == source_ip)
    if hostname: query = query.filter(SyslogRecord.hostname == hostname)
    if severity is not None: query = query.filter(SyslogRecord.severity == severity)
    if facility is not None: query = query.filter(SyslogRecord.facility == facility)
    if application: query = query.filter(SyslogRecord.application == application)
    if pattern: query = query.filter(SyslogRecord.message.ilike(f"%{pattern}%"))
    total = query.count()
    rows = query.order_by(SyslogRecord.event_timestamp.desc().nullslast(), SyslogRecord.received_at.desc(), SyslogRecord.id.desc()).offset(offset).limit(limit).all()
    return {"items": rows, "total": total, "limit": limit, "offset": offset}


class RulePayload(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    pattern: str = Field(min_length=1, max_length=500)
    min_severity: int | None = Field(default=None, ge=0, le=7)
    alert_severity: str = "warning"
    cooldown_seconds: int = Field(default=300, ge=1)
    enabled: bool = True
    device_id: int | None = Field(default=None, gt=0)
    source_ip: str | None = None
    hostname: str | None = None
    facility: int | None = Field(default=None, ge=0)
    application: str | None = None

    @field_validator("pattern")
    @classmethod
    def valid_regex(cls, value: str) -> str:
        try: re.compile(value)
        except re.error as exc: raise ValueError(f"Invalid syslog rule regex: {exc}") from exc
        return value


def _rule(db: Session, rule_id: int) -> SyslogCorrelationRule:
    item = db.get(SyslogCorrelationRule, rule_id)
    if item is None: raise HTTPException(404, "Syslog rule not found")
    return item


@router.get("/rules")
def rules(db: Session = Depends(get_db), _: User = Depends(require_permission("syslog:read"))):
    return db.query(SyslogCorrelationRule).order_by(SyslogCorrelationRule.name).all()


@router.get("/rules/{rule_id}")
def rule_detail(rule_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("syslog:read"))):
    return _rule(db, rule_id)


@router.post("/rules", status_code=201)
def add_rule(payload: RulePayload, db: Session = Depends(get_db), user: User = Depends(require_permission("syslog:manage"))):
    item = SyslogCorrelationRule(**payload.model_dump(), created_by=user.id, created_at=datetime.utcnow()); db.add(item); db.commit(); db.refresh(item); return item


@router.patch("/rules/{rule_id}")
def update_rule(rule_id: int, payload: RulePayload, db: Session = Depends(get_db), _: User = Depends(require_permission("syslog:manage"))):
    item = _rule(db, rule_id)
    for field, value in payload.model_dump().items(): setattr(item, field, value)
    db.commit(); db.refresh(item); return item


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("syslog:manage"))):
    item = _rule(db, rule_id); db.delete(item); db.commit(); return {"deleted": True, "id": rule_id}


@router.post("/rules/{rule_id}/enable")
def enable_rule(rule_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("syslog:manage"))):
    item = _rule(db, rule_id); item.enabled = True; db.commit(); return item


@router.post("/rules/{rule_id}/disable")
def disable_rule(rule_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("syslog:manage"))):
    item = _rule(db, rule_id); item.enabled = False; db.commit(); return item


@router.post("/retention/cleanup")
def retention_cleanup(retention_days: int = Query(..., ge=0), batch_size: int = Query(1000, ge=1, le=10000), db: Session = Depends(get_db), _: User = Depends(require_permission("syslog:manage"))):
    return {"deleted": cleanup_syslog(db, retention_days, batch_size), "retention_days": retention_days}
