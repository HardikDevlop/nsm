from datetime import timedelta, datetime
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from backend.auth.authorization import can_access_site
from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.models import Device
from backend.services.audit import record_audit_event
from .helper_security import issue_token, matches_token, utc_now
from .models import WindowsHelperChallenge, WindowsHelperCredential, WindowsHelperSubmission, WindowsProcessCollection
from .helper_challenge import ChallengeError, consume_challenge, materialize_challenge
from backend.config.settings import get_settings

router = APIRouter(prefix="/windows/helper", tags=["Windows Helper"])
bearer = HTTPBearer(auto_error=False)

class CredentialCreate(BaseModel):
    device_id: int = Field(gt=0)
    expires_in_days: int = Field(default=30, ge=1, le=365)

class HelperEvidence(BaseModel):
    schema_version: int = Field(ge=1, le=1)
    collection_id: UUID
    collected_at: str
    session_id: int = Field(ge=0, le=0x7fffffff)
    visible_process_ids: list[int] = Field(default_factory=list, max_length=4096)
    process_creation_times: dict[str, str] = Field(default_factory=dict, max_length=4096)
    challenge: str | None = Field(default=None, min_length=1, max_length=4096)

def _auth(db: Session, credentials: HTTPAuthorizationCredentials | None):
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid helper credentials")
    token = credentials.credentials
    row = db.query(WindowsHelperCredential).filter(WindowsHelperCredential.token_prefix == token[:12], WindowsHelperCredential.is_active.is_(True)).with_for_update().first()
    now = utc_now()
    if row is None or row.revoked_at is not None or row.expires_at.replace(tzinfo=now.tzinfo) <= now or not matches_token(token, row.token_hash):
        raise HTTPException(status_code=401, detail="Invalid helper credentials")
    return row

@router.post("/credentials", status_code=201)
def issue_helper_credential(body: CredentialCreate, db: Session = Depends(get_db), user=Depends(require_permission("windows_helper:manage"))):
    device = db.get(Device, body.device_id)
    if device is None or not can_access_site(user, device.site_id): raise HTTPException(status_code=404, detail="Device not found")
    token, prefix, digest = issue_token()
    row = WindowsHelperCredential(device_id=device.id, site_id=device.site_id, token_prefix=prefix, token_hash=digest, expires_at=utc_now().replace(tzinfo=None) + timedelta(days=body.expires_in_days))
    db.add(row); db.commit(); db.refresh(row)
    record_audit_event(db, actor=user, action="ISSUE", resource_type="windows_helper_credential", resource_id=row.id, site_id=device.site_id)
    return {"id": row.id, "device_id": row.device_id, "site_id": row.site_id, "token_prefix": prefix, "expires_at": row.expires_at, "token": token}

@router.post("/credentials/{credential_id}/revoke")
def revoke_helper_credential(credential_id: int, db: Session = Depends(get_db), user=Depends(require_permission("windows_helper:manage"))):
    row = db.get(WindowsHelperCredential, credential_id)
    if row is None or not can_access_site(user, row.site_id): raise HTTPException(status_code=404, detail="Credential not found")
    row.is_active = False; row.revoked_at = utc_now().replace(tzinfo=None); db.commit()
    record_audit_event(db, actor=user, action="REVOKE", resource_type="windows_helper_credential", resource_id=row.id, site_id=row.site_id)
    return {"id": row.id, "revoked": True}

@router.post("/credentials/{credential_id}/rotate", status_code=201)
def rotate_helper_credential(credential_id: int, body: CredentialCreate | None = None, db: Session = Depends(get_db), user=Depends(require_permission("windows_helper:manage"))):
    old = db.get(WindowsHelperCredential, credential_id)
    if old is None or not can_access_site(user, old.site_id): raise HTTPException(status_code=404, detail="Credential not found")
    days = body.expires_in_days if body is not None else 30
    token, prefix, digest = issue_token()
    old.is_active = False; old.revoked_at = utc_now().replace(tzinfo=None)
    row = WindowsHelperCredential(device_id=old.device_id, site_id=old.site_id, token_prefix=prefix, token_hash=digest, expires_at=utc_now().replace(tzinfo=None) + timedelta(days=days))
    db.add(row); db.commit(); db.refresh(row)
    record_audit_event(db, actor=user, action="ROTATE", resource_type="windows_helper_credential", resource_id=row.id, site_id=row.site_id)
    return {"id": row.id, "device_id": row.device_id, "site_id": row.site_id, "token_prefix": prefix, "expires_at": row.expires_at, "token": token}

@router.get("/devices/{device_id}/challenge")
def get_helper_challenge(device_id: int, db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    auth = _auth(db, credentials)
    device = db.get(Device, device_id)
    if device is None or auth.device_id != device_id or auth.site_id != device.site_id:
        raise HTTPException(status_code=403, detail="Invalid helper credentials")
    if not get_settings().windows_helper_challenge_key_map:
        raise HTTPException(status_code=404, detail="No active helper challenge")
    row = (db.query(WindowsHelperChallenge)
           .filter(WindowsHelperChallenge.device_id == device_id,
                   WindowsHelperChallenge.site_id == device.site_id,
                   WindowsHelperChallenge.consumed_at.is_(None),
                   WindowsHelperChallenge.cancelled_at.is_(None),
                   WindowsHelperChallenge.expires_at > utc_now())
           .order_by(WindowsHelperChallenge.issued_at.desc()).first())
    if row is None:
        raise HTTPException(status_code=404, detail="No active helper challenge")
    try:
        issued = materialize_challenge(db, row.challenge_id)
    except ChallengeError:
        raise HTTPException(status_code=404, detail="No active helper challenge") from None
    return {"challenge": issued.token, "device_id": issued.device_id, "site_id": issued.site_id,
            "collection_id": str(issued.collection_id), "expires_at": issued.expires_at}

@router.post("/devices/{device_id}/evidence", status_code=202)
def submit_helper_evidence(device_id: int, body: HelperEvidence, db: Session = Depends(get_db), credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    auth = _auth(db, credentials)
    device = db.get(Device, device_id)
    if device is None or auth.device_id != device_id or auth.site_id != device.site_id: raise HTTPException(status_code=403, detail="Invalid helper credentials")
    from .application_helper import validate_helper_payload
    payload = body.model_dump(mode="json")
    try: validate_helper_payload(payload)
    except ValueError as exc: raise HTTPException(status_code=422, detail=str(exc))
    try:
        challenge_enabled = bool(get_settings().windows_helper_challenge_key_map)
        if challenge_enabled and not body.challenge:
            raise HTTPException(status_code=401, detail="Signed helper challenge required")
        if challenge_enabled:
            active_collection = (db.query(WindowsProcessCollection)
                                 .filter(WindowsProcessCollection.device_id == device_id,
                                         WindowsProcessCollection.site_id == device.site_id,
                                         WindowsProcessCollection.collection_id == body.collection_id)
                                 .with_for_update().first())
            if active_collection is None or active_collection.state != "COLLECTING":
                db.rollback()
                raise HTTPException(status_code=409, detail="Collection is not accepting helper evidence")
            try:
                consume_challenge(db, body.challenge, device_id=device_id, site_id=device.site_id,
                                  collection_id=body.collection_id)
            except ChallengeError:
                db.rollback()
                raise HTTPException(status_code=401, detail="Invalid helper challenge") from None
        expired_ids = [item.id for item in db.query(WindowsHelperSubmission.id).filter(WindowsHelperSubmission.expires_at <= utc_now().replace(tzinfo=None)).order_by(WindowsHelperSubmission.id).limit(1000).all()]
        if expired_ids:
            db.query(WindowsHelperSubmission).filter(WindowsHelperSubmission.id.in_(expired_ids)).delete(synchronize_session=False)
        collected_at = datetime.fromisoformat(body.collected_at.replace("Z", "+00:00"))
        db.add(WindowsHelperSubmission(collection_id=body.collection_id, device_id=device_id, session_id=body.session_id, collected_at=collected_at, evidence=payload, expires_at=utc_now().replace(tzinfo=None) + timedelta(seconds=60)))
        auth.last_used_at = utc_now().replace(tzinfo=None); db.commit()
    except IntegrityError:
        db.rollback(); raise HTTPException(status_code=409, detail="Duplicate collection")
    return {"accepted": True, "collection_id": str(body.collection_id)}
