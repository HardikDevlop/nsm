from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.models import ConfigurationCompliancePolicy, ConfigurationComplianceViolation, User
from backend.config_backups.compliance import evaluate_policy

router = APIRouter(prefix="/api/v1/config-compliance", tags=["Configuration Compliance"])
class PolicyPayload(BaseModel):
    name: str = Field(min_length=1, max_length=160); description: str | None = None; rules: dict; enabled: bool = True
class EvaluationPayload(BaseModel):
    policy_id: int = Field(gt=0); device_id: int = Field(gt=0)
def view_policy(p): return {"id": p.id, "name": p.name, "description": p.description, "rules": p.rules, "enabled": p.enabled, "created_by": p.created_by, "created_at": p.created_at}
def view_violation(v): return {"id": v.id, "policy_id": v.policy_id, "device_id": v.device_id, "version": v.version, "severity": v.severity, "status": v.status, "evidence": v.evidence, "recommendation": v.recommendation, "detected_at": v.detected_at, "resolved_at": v.resolved_at, "resolved_by": v.resolved_by}
@router.get("/policies")
def list_policies(db: Session = Depends(get_db), _: User = Depends(require_permission("config_compliance:read"))): return {"items": [view_policy(p) for p in db.query(ConfigurationCompliancePolicy).order_by(ConfigurationCompliancePolicy.name).all()]}
@router.post("/policies", status_code=201)
def create_policy(payload: PolicyPayload, db: Session = Depends(get_db), user: User = Depends(require_permission("config_compliance:manage"))):
    item = ConfigurationCompliancePolicy(**payload.model_dump(), created_by=user.id, created_at=datetime.utcnow()); db.add(item); db.commit(); db.refresh(item); return view_policy(item)
@router.post("/evaluate")
def run_evaluation(payload: EvaluationPayload, db: Session = Depends(get_db), user: User = Depends(require_permission("config_compliance:execute"))):
    try: item = evaluate_policy(db, payload.policy_id, payload.device_id, user.id)
    except LookupError as exc: raise HTTPException(404, str(exc))
    db.commit(); return {"compliant": item is None, "violation": view_violation(item) if item else None}
@router.get("/violations")
def list_violations(status: str | None = Query(None), db: Session = Depends(get_db), _: User = Depends(require_permission("config_compliance:read"))):
    q = db.query(ConfigurationComplianceViolation)
    if status: q = q.filter_by(status=status)
    return {"items": [view_violation(v) for v in q.order_by(ConfigurationComplianceViolation.detected_at.desc()).all()]}
