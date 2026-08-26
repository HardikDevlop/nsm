"""HTTP API for Linux Server Monitoring foundation resources only."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.models import User
from backend.linux_monitoring import service
from backend.linux_monitoring.models import LinuxSecurityEvent, LinuxServer, LinuxServerCredential, LinuxServerMetricSample
from backend.linux_monitoring.schemas import (
    LinuxServerAddRequest,
    LinuxServerCreate,
    LinuxServerCredentialCreate,
    LinuxServerCredentialRead,
    LinuxServerCredentialUpdate,
    LinuxServerMonitoringConfigRead,
    LinuxServerMonitoringConfigUpdate,
    LinuxServerDetailsRead,
    LinuxServerDetectedData,
    LinuxServerDetectionResponse,
    LinuxServerMetricCollectionResponse,
    LinuxServerMetricRead,
    LinuxServerCurrentMetricRead,
    LinuxServerMetricsCollectRequest,
    LinuxSecurityCollectRequest,
    LinuxSecurityCollectResponse,
    LinuxSecurityEventRead,
    LinuxServerRead,
    LinuxServerUpdate,
    LinuxServerSSHValidateRequest,
    LinuxServerSNMPValidateRequest,
    LinuxMonitoringStartRequest,
    LinuxMonitoringStatusRead,
    LinuxRetentionStatusRead,
)
from backend.linux_monitoring.scheduler import LinuxMonitoringScheduler

router = APIRouter(prefix="/api/v1/linux-servers", tags=["Linux Server Monitoring"])


def _scheduler(request: Request) -> LinuxMonitoringScheduler:
    scheduler = getattr(request.app.state, "linux_monitoring_scheduler", None)
    if scheduler is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Linux monitoring scheduler is unavailable")
    return scheduler


@router.get("/monitoring/status", response_model=list[LinuxMonitoringStatusRead])
def list_linux_monitoring_status(request: Request, _: User = Depends(require_permission("linux_servers:read"))):
    return _scheduler(request).statuses()


@router.get("/retention/status", response_model=LinuxRetentionStatusRead)
def get_linux_retention_status(request: Request, _: User = Depends(require_permission("linux_servers:read"))):
    return _scheduler(request).retention_status()


@router.get("", response_model=list[LinuxServerRead])
def list_linux_servers(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("linux_servers:read")),
):
    return db.query(LinuxServer).filter(LinuxServer.deleted_at.is_(None)).order_by(LinuxServer.id).offset(skip).limit(min(limit, 500)).all()


def _detection_response(payload: LinuxServerAddRequest) -> LinuxServerDetectionResponse:
    data, warnings, error = service.detect_server(payload)
    if error:
        return LinuxServerDetectionResponse(
            success=False,
            status=error.code,
            message=error.message,
            warnings=warnings,
        )
    detected = LinuxServerDetectedData.model_validate(data)
    valid = detected.ssh_valid and detected.snmp_valid
    return LinuxServerDetectionResponse(
        success=valid,
        status="validated" if valid else "validation_failed",
        message="SSH and SNMPv3 connectivity validated" if valid else "SSH and SNMPv3 validation must both pass before adding the server",
        data=detected,
        warnings=warnings,
        ssh_valid=detected.ssh_valid,
        snmp_valid=detected.snmp_valid,
        ssh_error=detected.ssh_error,
        snmp_error=detected.snmp_error,
    )


@router.post("/detect", response_model=LinuxServerDetectionResponse)
def detect_linux_server(payload: LinuxServerAddRequest, _: User = Depends(require_permission("linux_servers:read"))):
    return _detection_response(payload)


@router.post("/detect/ssh", response_model=LinuxServerDetectionResponse)
def validate_linux_server_ssh(payload: LinuxServerSSHValidateRequest, _: User = Depends(require_permission("linux_servers:read"))):
    data, error = service.validate_ssh(payload)
    if error:
        return LinuxServerDetectionResponse(success=False, status=error.code, message=error.message, ssh_error=error.message)
    detected = LinuxServerDetectedData.model_validate({**data, "ssh_valid": True, "snmp_valid": False})
    return LinuxServerDetectionResponse(success=True, status="validated", message="SSH connectivity validated", data=detected, ssh_valid=True)


@router.post("/detect/snmp", response_model=LinuxServerDetectionResponse)
def validate_linux_server_snmp(payload: LinuxServerSNMPValidateRequest, _: User = Depends(require_permission("linux_servers:read"))):
    valid, error = service.validate_snmp(payload)
    if error:
        return LinuxServerDetectionResponse(success=False, status=error.code, message=error.message, snmp_error=error.message)
    if not valid:
        message = "SNMPv3 did not respond with the supplied credentials"
        return LinuxServerDetectionResponse(success=False, status="validation_failed", message=message, snmp_error=message)
    return LinuxServerDetectionResponse(success=True, status="validated", message="SNMPv3 connectivity validated", snmp_valid=True)


@router.post("", response_model=LinuxServerDetailsRead, status_code=status.HTTP_201_CREATED)
def create_linux_server(
    payload: LinuxServerAddRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("linux_servers:create")),
):
    result = _detection_response(payload)
    if not result.success or result.data is None:
        error_status = {
            "timeout": status.HTTP_504_GATEWAY_TIMEOUT,
            "authentication_failed": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "invalid_address": status.HTTP_422_UNPROCESSABLE_ENTITY,
            "validation_failed": status.HTTP_422_UNPROCESSABLE_ENTITY,
        }.get(result.status, status.HTTP_502_BAD_GATEWAY)
        raise HTTPException(status_code=error_status, detail=result.message)
    return service.save_detected_server(db, payload, result.data.model_dump(), current_user.id)


@router.get("/{server_id}", response_model=LinuxServerDetailsRead)
def get_linux_server(server_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("linux_servers:read"))):
    return service.get_server_details(db, server_id)


@router.get("/{server_id}/monitoring/status", response_model=LinuxMonitoringStatusRead)
def get_linux_monitoring_status(server_id: int, request: Request, _: User = Depends(require_permission("linux_servers:read"))):
    return _scheduler(request).status(server_id)


@router.post("/{server_id}/monitoring/start", response_model=LinuxMonitoringStatusRead)
async def start_linux_monitoring(
    server_id: int,
    payload: LinuxMonitoringStartRequest,
    request: Request,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("linux_servers:update")),
):
    service.get_server(db, server_id)
    existing = db.query(service.LinuxServerSNMPCredential).filter_by(linux_server_id=server_id).first()
    if payload.username:
        service.save_monitoring_credential(db, server_id, payload)
    elif existing is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="SNMPv3 credentials are required on first start")
    return await _scheduler(request).start_server(server_id)


@router.post("/{server_id}/monitoring/stop", response_model=LinuxMonitoringStatusRead)
async def stop_linux_monitoring(server_id: int, request: Request, _: User = Depends(require_permission("linux_servers:update"))):
    return await _scheduler(request).stop_server(server_id)


@router.get("/{server_id}/security/events", response_model=list[LinuxSecurityEventRead])
def list_linux_security_events(
    server_id: int,
    skip: int = 0,
    limit: int = 100,
    since: datetime | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("linux_servers:read")),
):
    service.get_server(db, server_id)
    query = db.query(LinuxSecurityEvent).filter(LinuxSecurityEvent.linux_server_id == server_id)
    retention_cutoff = datetime.utcnow() - timedelta(hours=24)
    query = query.filter(LinuxSecurityEvent.event_timestamp >= retention_cutoff)
    if since is not None:
        query = query.filter(LinuxSecurityEvent.event_timestamp >= max(since.replace(tzinfo=None), retention_cutoff))
    return query.order_by(LinuxSecurityEvent.event_timestamp.desc()).offset(skip).limit(min(limit, 5000)).all()


@router.post("/{server_id}/security/collect", response_model=LinuxSecurityCollectResponse)
def collect_linux_security_events(
    server_id: int,
    payload: LinuxSecurityCollectRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("linux_servers:update")),
):
    events, duplicates, logs_available, warnings, error = service.collect_security(db, server_id, payload)
    if error:
        return LinuxSecurityCollectResponse(
            success=False,
            status=error.code,
            message=error.message,
            logs_available=False,
            collected_events=0,
            duplicate_events=0,
            warnings=warnings,
            events=[],
        )
    status_value = "collected" if events else "logs_unavailable" if not logs_available else "no_security_events"
    message = (
        "Security events collected from Linux firewall/security logs"
        if events else "No explicit security events found in the available Linux logs"
        if logs_available else "No readable Linux security logs were available"
    )
    return LinuxSecurityCollectResponse(
        success=True,
        status=status_value,
        message=message,
        logs_available=logs_available,
        collected_events=len(events),
        duplicate_events=duplicates,
        warnings=warnings,
        events=[LinuxSecurityEventRead.model_validate(event) for event in events],
    )


@router.get("/{server_id}/metrics/latest", response_model=LinuxServerCurrentMetricRead)
def get_latest_linux_metrics(server_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("linux_servers:read"))):
    return service.get_current_metrics(db, server_id)


@router.get("/{server_id}/metrics/history", response_model=list[LinuxServerMetricRead])
def get_linux_metric_history(
    server_id: int,
    since: datetime | None = None,
    limit: int = 5000,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("linux_servers:read")),
):
    service.get_server(db, server_id)
    cutoff = datetime.utcnow() - timedelta(hours=24)
    requested = since.replace(tzinfo=None) if since else cutoff
    query = db.query(LinuxServerMetricSample).filter(
        LinuxServerMetricSample.linux_server_id == server_id,
        LinuxServerMetricSample.collected_at >= max(requested, cutoff),
    )
    return query.order_by(LinuxServerMetricSample.collected_at.desc()).limit(min(limit, 5000)).all()


@router.post("/{server_id}/metrics/collect", response_model=LinuxServerMetricCollectionResponse)
def collect_linux_server_metrics(
    server_id: int,
    payload: LinuxServerMetricsCollectRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("linux_servers:update")),
):
    sample, error = service.collect_metrics(db, server_id, payload)
    if sample is None:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Linux metric collection failed")
    if error:
        return LinuxServerMetricCollectionResponse(
            success=False,
            status=error.code,
            message=error.message,
            data=LinuxServerMetricRead.model_validate(sample),
        )
    return LinuxServerMetricCollectionResponse(
        success=True,
        status="collected",
        message="Linux metrics collected from SNMPv3 and saved",
        data=LinuxServerMetricRead.model_validate(sample),
    )


@router.patch("/{server_id}", response_model=LinuxServerRead)
def update_linux_server(
    server_id: int,
    payload: LinuxServerUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("linux_servers:update")),
):
    return service.update_server(db, server_id, payload)


@router.delete("/{server_id}")
async def delete_linux_server(server_id: int, request: Request, db: Session = Depends(get_db), _: User = Depends(require_permission("linux_servers:delete"))):
    # Stop the in-process polling task before deleting its database row.
    service.get_server(db, server_id)
    scheduler = getattr(request.app.state, "linux_monitoring_scheduler", None)
    if scheduler is not None:
        await scheduler.stop_server(server_id)
    return service.delete_server(db, server_id)


@router.get("/{server_id}/config", response_model=LinuxServerMonitoringConfigRead)
def get_linux_server_config(server_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("linux_servers:read"))):
    return service.get_config(db, server_id)


@router.put("/{server_id}/config", response_model=LinuxServerMonitoringConfigRead)
def update_linux_server_config(
    server_id: int,
    payload: LinuxServerMonitoringConfigUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("linux_servers:update")),
):
    return service.upsert_config(db, server_id, payload)


@router.get("/{server_id}/credentials", response_model=list[LinuxServerCredentialRead])
def list_linux_server_credentials(server_id: int, db: Session = Depends(get_db), _: User = Depends(require_permission("linux_servers:read"))):
    service.get_server(db, server_id)
    return db.query(LinuxServerCredential).filter(LinuxServerCredential.linux_server_id == server_id).order_by(LinuxServerCredential.id).all()


@router.post("/{server_id}/credentials", response_model=LinuxServerCredentialRead, status_code=status.HTTP_201_CREATED)
def create_linux_server_credential(
    server_id: int,
    payload: LinuxServerCredentialCreate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("linux_servers:update")),
):
    return service.add_credential(db, server_id, payload)


@router.patch("/{server_id}/credentials/{credential_id}", response_model=LinuxServerCredentialRead)
def update_linux_server_credential(
    server_id: int,
    credential_id: int,
    payload: LinuxServerCredentialUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("linux_servers:update")),
):
    return service.update_credential(db, server_id, credential_id, payload)
