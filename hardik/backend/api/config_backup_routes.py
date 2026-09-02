from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.config_backups.service import compare_configurations, record_configuration
from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.models import DeviceConfigurationVersion, User
from backend.utils.crypto import decrypt_secret

router = APIRouter(prefix="/api/v1/config-backups", tags=["Configuration Backup"])


class ConfigurationCapturePayload(BaseModel):
    device_id: int = Field(gt=0)
    source: str = Field(min_length=1, max_length=40)
    content: str = Field(min_length=1, max_length=5_000_000)
    is_startup: bool = False


class ConfigurationComparePayload(BaseModel):
    device_id: int = Field(gt=0)
    from_version: int = Field(gt=0)
    to_version: int = Field(gt=0)


def _comparison_view(item: Any) -> dict[str, Any]:
    return {"id": item.id, "device_id": item.device_id, "from_version": item.from_version, "to_version": item.to_version, "added_lines": item.added_lines, "removed_lines": item.removed_lines, "changed_lines": item.changed_lines, "initiated_by": item.initiated_by, "created_at": item.created_at}


def _view(item: DeviceConfigurationVersion, include_content: bool = False) -> dict[str, Any]:
    value = {"id": item.id, "device_id": item.device_id, "version": item.version, "source": item.source, "checksum": item.checksum, "is_startup": item.is_startup, "captured_at": item.captured_at, "captured_by": item.captured_by, "unchanged": False}
    if include_content: value["content"] = decrypt_secret(item.encrypted_content)
    return value


@router.post("/capture", status_code=201)
def capture_configuration(payload: ConfigurationCapturePayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("config_backups:execute"))):
    try:
        item, created = record_configuration(db, payload.device_id, payload.content, payload.source, current_user.id, payload.is_startup)
    except LookupError as exc: raise HTTPException(404, str(exc))
    except ValueError as exc: raise HTTPException(422, str(exc))
    db.commit()
    db.refresh(item)
    result = _view(item, include_content=False); result["unchanged"] = not created
    return result


@router.get("/devices/{device_id}")
def list_device_configurations(device_id: int, include_content: bool = Query(False), skip: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db), _: User = Depends(require_permission("config_backups:read"))):
    rows = db.query(DeviceConfigurationVersion).filter_by(device_id=device_id).order_by(DeviceConfigurationVersion.version.desc()).offset(skip).limit(limit).all()
    return {"items": [_view(row, include_content) for row in rows], "skip": skip, "limit": limit}


@router.get("/devices/{device_id}/versions/{version}")
def get_device_configuration(device_id: int, version: int, db: Session = Depends(get_db), _: User = Depends(require_permission("config_backups:read"))):
    item = db.query(DeviceConfigurationVersion).filter_by(device_id=device_id, version=version).first()
    if item is None: raise HTTPException(404, "Configuration version not found")
    return _view(item, include_content=True)


@router.post("/compare")
def compare_configuration_versions(payload: ConfigurationComparePayload, db: Session = Depends(get_db), current_user: User = Depends(require_permission("config_backups:read"))):
    try:
        item = compare_configurations(db, payload.device_id, payload.from_version, payload.to_version, current_user.id)
    except LookupError as exc: raise HTTPException(404, str(exc))
    except ValueError as exc: raise HTTPException(422, str(exc))
    db.commit(); db.refresh(item)
    return _comparison_view(item)


@router.get("/devices/{device_id}/compare/baseline-current")
def compare_baseline_current(device_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_permission("config_backups:read"))):
    rows = db.query(DeviceConfigurationVersion).filter_by(device_id=device_id).order_by(DeviceConfigurationVersion.version.asc()).all()
    if len(rows) < 2: raise HTTPException(404, "At least two configuration versions are required")
    item = compare_configurations(db, device_id, rows[0].version, rows[-1].version, current_user.id)
    db.commit(); db.refresh(item)
    return _comparison_view(item)
