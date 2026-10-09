"""Remote Access terminal WebSocket endpoint."""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, WebSocket
import logging
import time
from sqlalchemy.orm import Session

from backend.auth.security import decode_access_token_claims
from backend.database.session import get_db
from backend.models import Alert, Device, RemoteAccessCredential, RemoteAccessSession, SSHHostKey, User, utc_now
from backend.database.session import SessionLocal
from backend.schemas.remote_access import (RemoteAccessCredentialCreate, RemoteAccessCredentialRead,
    RemoteAccessCredentialUpdate, RemoteAccessSessionCreate, RemoteAccessSessionRead, RemoteAccessTestRequest,
    SSHHostKeyScanRequest, SSHHostKeyTrustRequest, SSHHostKeyRead)
from backend.services.remote_access.session_manager import SessionManager
from backend.services.remote_access.test_connection import TestConnectionRequest, TestConnectionService
from backend.dependencies import get_current_user, get_user_permission_codes, require_permission
from backend.auth.authorization import can_access_site

from backend.services.remote_access.terminal_websocket import TerminalWebSocket
from backend.services.remote_access.host_keys import SSHHostKeyError, SSHHostKeyService
from backend.services.remote_access_credentials import RemoteAccessCredentialError, RemoteAccessCredentialService
from backend.services.audit import record_audit_event
from backend.services.alerting import _notify
from backend.services.alerting import deliver_notification_ids, prepare_notification_ids

logger = logging.getLogger(__name__)

router = APIRouter()


def _manage_host_key_permission(user: User) -> None:
    if "remote_access:manage_credentials" not in get_user_permission_codes(user):
        raise HTTPException(status_code=403, detail="Missing permission: remote_access:manage_credentials")


def _host_key_response(item):
    return {"id": item.id, "device_id": item.device_id, "host": item.host, "port": item.port,
            "key_type": item.key_type, "fingerprint": item.fingerprint, "status": item.status}


def _credential_response(item):
    return RemoteAccessCredentialRead.model_validate(item)


def _credential_permission(user: User) -> None:
    if "remote_access:manage_credentials" not in get_user_permission_codes(user):
        raise HTTPException(status_code=403, detail="Missing permission: remote_access:manage_credentials")


def _credential_device(db: Session, user: User, device_id: int) -> Device:
    device = db.get(Device, device_id)
    if device is None or not can_access_site(user, device.site_id):
        raise HTTPException(status_code=403, detail="Device access denied")
    return device


def _should_commit_test_result(result: dict) -> bool:
    """Commit only success or intentionally-created pending trust state."""
    return bool(result.get("success") or (
        result.get("error_code") == "HOST_KEY_UNKNOWN" and result.get("host_key_id")
    ))


def _record_remote_access_connected_alert(db: Session, session: RemoteAccessSession,
                                          deferred_ids: list[int]) -> bool:
    """Record a successful session after its durable session commit."""
    try:
        alert_started = time.perf_counter()
        device = db.get(Device, session.device_id)
        hostname = device.hostname if device is not None else str(session.device_id)
        protocol = session.protocol.upper()
        alert = Alert(
            device_id=session.device_id,
            severity="info",
            title=f"Remote Access Connected: {hostname} ({protocol})",
            description=(
                f"{protocol} remote access session connected to {hostname}. "
                f"User: {session.device_username}. Port: {session.port}."
            ),
            status="open",
            created_at=utc_now(),
        )
        db.add(alert)
        db.flush()
        notify_started = time.perf_counter()
        logger.info("[remote-access][post-create] stage=notify-before elapsed_ms=%.3f stage_ms=0.000 session_uuid=%s",
                    (notify_started - alert_started) * 1000, session.session_uuid)
        deferred_ids.extend(prepare_notification_ids(db, alert))
        logger.info("[remote-access] notification-enqueued session_uuid=%s alert_id=%s count=%s",
                    session.session_uuid, alert.id, len(deferred_ids))
        logger.info("[remote-access][post-create] stage=notify-after elapsed_ms=%.3f stage_ms=%.3f session_uuid=%s",
                    (time.perf_counter() - alert_started) * 1000,
                    (time.perf_counter() - notify_started) * 1000, session.session_uuid)
        db.commit()
        return True
    except Exception:
        db.rollback()
        deferred_ids.clear()
        logger.exception("Remote Access connect alert could not be recorded: session=%s", session.session_uuid)
        return False


def _deliver_remote_access_notifications(notification_ids: list[int], session_uuid: str) -> None:
    """Deliver committed notification rows using an independent DB session."""
    if not notification_ids:
        return
    logger.info("[remote-access] notification-background-start session_uuid=%s count=%s",
                session_uuid, len(notification_ids))
    try:
        with SessionLocal() as delivery_db:
            deliver_notification_ids(delivery_db, notification_ids)
            delivery_db.commit()
        logger.info("[remote-access] notification-background-end session_uuid=%s count=%s",
                    session_uuid, len(notification_ids))
    except Exception:
        logger.exception("[remote-access] notification-failed session_uuid=%s count=%s",
                         session_uuid, len(notification_ids), exc_info=False)


@router.get("/remote-access/credentials", response_model=list[RemoteAccessCredentialRead])
def list_remote_credentials(device_id: int | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _credential_permission(current_user)
    if device_id is not None:
        _credential_device(db, current_user, device_id)
    items = RemoteAccessCredentialService(db).list(device_id=device_id)
    return [_credential_response(item) for item in items if can_access_site(current_user, item.device.site_id)]


@router.get("/remote-access/credentials/{credential_id}", response_model=RemoteAccessCredentialRead)
def get_remote_credential(credential_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _credential_permission(current_user)
    item = RemoteAccessCredentialService(db).get_by_id(credential_id)
    if item is None or not can_access_site(current_user, item.device.site_id):
        raise HTTPException(status_code=404, detail="Credential does not exist")
    return _credential_response(item)


def _audit_credential(db, user, action, item, request: Request, *, old=None, new=None):
    record_audit_event(db, actor=user, action=action, resource_type="remote_access_credential",
                       resource_id=item.id, site_id=item.device.site_id,
                       request_method=request.method, request_path=request.url.path,
                       old_values=old, new_values=new,
                       metadata={"device_id": item.device_id, "protocol": item.protocol})


@router.post("/remote-access/credentials", response_model=RemoteAccessCredentialRead, status_code=201)
def create_remote_credential(payload: RemoteAccessCredentialCreate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _credential_permission(current_user)
    device = _credential_device(db, current_user, payload.device_id)
    result = TestConnectionService(db).test_connection(TestConnectionRequest(
        device_id=device.id, protocol=payload.protocol, port=payload.port,
        username=payload.username, secret=payload.secret, auth_type=payload.auth_type,
        remember_credential=False, mark_existing_failed=False))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)
    service = RemoteAccessCredentialService(db)
    try:
        item = service.create(device_id=device.id, protocol=payload.protocol, port=payload.port,
                              username=payload.username, auth_type=payload.auth_type, secret=payload.secret,
                              created_by=current_user.id)
        item = service.mark_verified(item.id)
        db.commit()
        _audit_credential(db, current_user, "REMOTE_ACCESS_CREDENTIAL_CREATED", item, request,
                          new={"device_id": item.device_id, "protocol": item.protocol, "username": item.username})
        return _credential_response(item)
    except RemoteAccessCredentialError as exc:
        db.rollback(); raise HTTPException(status_code=400, detail=exc.code) from exc


@router.patch("/remote-access/credentials/{credential_id}", response_model=RemoteAccessCredentialRead)
def update_remote_credential(credential_id: int, payload: RemoteAccessCredentialUpdate, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _credential_permission(current_user)
    service = RemoteAccessCredentialService(db)
    old = service.get_by_id(credential_id)
    if old is None or not can_access_site(current_user, old.device.site_id):
        raise HTTPException(status_code=404, detail="Credential does not exist")
    current_secret = service.resolve_connection_credential(old.id).secret
    result = TestConnectionService(db).test_connection(TestConnectionRequest(
        device_id=old.device_id, protocol=old.protocol, port=payload.port or old.port,
        username=payload.username or old.username,
        secret=payload.secret or current_secret, auth_type=payload.auth_type or old.auth_type,
        remember_credential=False, mark_existing_failed=False))
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)
    old_values = {"device_id": old.device_id, "protocol": old.protocol, "username": old.username, "port": old.port}
    item = service.update(credential_id, port=payload.port, username=payload.username,
                          auth_type=payload.auth_type, secret=payload.secret)
    item = service.mark_verified(item.id)
    db.commit()
    _audit_credential(db, current_user, "REMOTE_ACCESS_CREDENTIAL_UPDATED", item, request,
                      old=old_values, new={"device_id": item.device_id, "protocol": item.protocol, "username": item.username, "port": item.port})
    return _credential_response(item)


@router.delete("/remote-access/credentials/{credential_id}")
def delete_remote_credential(credential_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _credential_permission(current_user)
    service = RemoteAccessCredentialService(db)
    item = service.get_by_id(credential_id)
    if item is None or not can_access_site(current_user, item.device.site_id):
        raise HTTPException(status_code=404, detail="Credential does not exist")
    old = {"device_id": item.device_id, "protocol": item.protocol, "username": item.username, "port": item.port}
    service.delete(credential_id); db.commit()
    record_audit_event(db, actor=current_user, action="REMOTE_ACCESS_CREDENTIAL_DELETED",
                       resource_type="remote_access_credential", resource_id=credential_id,
                       site_id=item.device.site_id, request_method=request.method,
                       request_path=request.url.path, old_values=old,
                       metadata={"device_id": item.device_id, "protocol": item.protocol})
    return {"deleted": True, "credential_id": credential_id}


@router.post("/remote-access/host-keys/scan", response_model=SSHHostKeyRead)
def scan_ssh_host_key(payload: SSHHostKeyScanRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _manage_host_key_permission(current_user)
    device = db.get(Device, payload.device_id)
    if device is None or not can_access_site(current_user, device.site_id):
        raise HTTPException(status_code=403, detail="Device access denied")
    try:
        item = SSHHostKeyService(db).scan(payload.device_id, payload.port)
        db.commit()
        return _host_key_response(item)
    except SSHHostKeyError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=exc.code) from exc


@router.post("/remote-access/host-keys/{host_key_id}/trust", response_model=SSHHostKeyRead)
def trust_ssh_host_key(host_key_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _manage_host_key_permission(current_user)
    try:
        existing = db.get(SSHHostKey, host_key_id)
        if existing is None:
            raise SSHHostKeyError("HOST_KEY_NOT_FOUND", "Host key does not exist")
        device = db.get(Device, existing.device_id)
        if device is None or not can_access_site(current_user, device.site_id):
            raise HTTPException(status_code=403, detail="Device access denied")
        item = SSHHostKeyService(db).trust(host_key_id, current_user.id)
        db.commit()
        return _host_key_response(item)
    except SSHHostKeyError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=exc.code) from exc


@router.post("/remote-access/host-keys/{host_key_id}/revoke", response_model=SSHHostKeyRead)
def revoke_ssh_host_key(host_key_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _manage_host_key_permission(current_user)
    try:
        item = SSHHostKeyService(db).revoke(host_key_id)
        db.commit()
        return _host_key_response(item)
    except SSHHostKeyError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=exc.code) from exc


def manager_from_request(request: Request):
    return getattr(request.app.state, "remote_access_session_manager", None)


@router.post("/remote-access/sessions", response_model=RemoteAccessSessionRead)
def create_remote_session(payload: RemoteAccessSessionCreate, request: Request, background_tasks: BackgroundTasks,
                          db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
                          manager: SessionManager | None = Depends(manager_from_request)):
    if "remote_access:connect" not in get_user_permission_codes(current_user):
        raise HTTPException(status_code=403, detail="Missing permission: remote_access:connect")
    if payload.remember_credential and "remote_access:manage_credentials" not in get_user_permission_codes(current_user):
        raise HTTPException(status_code=403, detail="Missing permission: remote_access:manage_credentials")
    device = db.get(Device, payload.device_id)
    if device is None or not can_access_site(current_user, device.site_id):
        raise HTTPException(status_code=403, detail="Device access denied")
    if manager is None:
        raise HTTPException(status_code=503, detail="Remote Access session service unavailable")
    request_started = __import__("time").perf_counter()
    logger.info(
        "[remote-access] session-request device_id=%s protocol=%s port=%s username_present=%s "
        "secret_present=%s credential_id=%s remember_credential=%s",
        payload.device_id, payload.protocol, payload.port,
        bool(payload.username), bool(payload.secret), payload.credential_id,
        payload.remember_credential,
    )
    item = None
    try:
        item = manager.create_session(
            user_id=current_user.id,
            source_ip=request.client.host if request.client else None,
            **payload.model_dump(exclude={"source_ip"}),
        )
        commit_started = time.perf_counter()
        logger.info("[remote-access][post-create] stage=before-commit elapsed_ms=%.3f stage_ms=0.000 session_uuid=%s",
                    (commit_started - request_started) * 1000, item.session_uuid)
        manager.db.commit()
        logger.info("[remote-access][post-create] stage=after-commit elapsed_ms=%.3f stage_ms=%.3f session_uuid=%s",
                    (time.perf_counter() - request_started) * 1000,
                    (time.perf_counter() - commit_started) * 1000, item.session_uuid)
        # Use the same long-lived DB session that persisted the remote session.
        # This avoids a second request session hiding/losing the connect alert
        # while the session itself is already committed.
        alert_started = time.perf_counter()
        notification_ids: list[int] = []
        logger.info("[remote-access][post-create] stage=before-connected-alert elapsed_ms=%.3f stage_ms=0.000 session_uuid=%s",
                    (alert_started - request_started) * 1000, item.session_uuid)
        alert_persisted = _record_remote_access_connected_alert(manager.db, item, notification_ids)
        logger.info("[remote-access] connected-alert-persisted session_uuid=%s persisted=%s",
                    item.session_uuid, alert_persisted)
        if alert_persisted and notification_ids:
            logger.info("[remote-access] notification-enqueued session_uuid=%s count=%s",
                        item.session_uuid, len(notification_ids))
            background_tasks.add_task(
                _deliver_remote_access_notifications,
                list(notification_ids),
                item.session_uuid,
            )
        logger.info("[remote-access][post-create] stage=after-connected-alert elapsed_ms=%.3f stage_ms=%.3f session_uuid=%s",
                    (time.perf_counter() - request_started) * 1000,
                    (time.perf_counter() - alert_started) * 1000, item.session_uuid)
        logger.info("[remote-access][post-create] stage=before-return elapsed_ms=%.3f stage_ms=0.000 session_uuid=%s",
                    (time.perf_counter() - request_started) * 1000, item.session_uuid)
        return item
    except Exception as exc:
        safe_exception = str(exc).replace("\n", " ").replace("\r", " ")[:512]
        for sensitive in (payload.username, payload.secret):
            if sensitive:
                safe_exception = safe_exception.replace(sensitive, "[REDACTED]")
        logger.exception(
            "[remote-access][session-create-failed] stage=session-response elapsed_ms=%.3f "
            "exception_type=%s exception_message=%s",
            (__import__("time").perf_counter() - request_started) * 1000,
            type(exc).__name__,
            safe_exception,
            exc_info=False,
        )
        if item is not None and manager is not None:
            try:
                manager.disconnect_session(item.session_uuid, reason="Session creation failed")
            except Exception:
                logger.exception("[remote-access] session cleanup failed session_uuid=%s", item.session_uuid, exc_info=False)
        db.rollback()
        code = getattr(exc, "code", "SESSION_CREATE_FAILED")
        if manager is not None:
            try:
                if code == "DEVICE_ALREADY_CONNECTED" or not manager.db.is_active:
                    manager.db.rollback()
                else:
                    manager.db.commit()
            except Exception:
                manager.db.rollback()
        logger.warning("Remote Access session creation failed: code=%s exception_type=%s", code, type(exc).__name__)
        if code == "DEVICE_ALREADY_CONNECTED":
            protocol = getattr(exc, "protocol", "")
            raise HTTPException(
                status_code=409,
                detail=f"DEVICE_ALREADY_CONNECTED:{protocol}",
            ) from exc
        raise HTTPException(status_code=400, detail=code) from exc


@router.get("/remote-access/sessions", response_model=list[RemoteAccessSessionRead])
def list_remote_sessions(db: Session = Depends(get_db), current_user: User = Depends(get_current_user), manager: SessionManager | None = Depends(manager_from_request)):
    if "remote_access:view_sessions" not in get_user_permission_codes(current_user):
        raise HTTPException(status_code=403, detail="Missing permission: remote_access:view_sessions")
    if manager is None:
        raise HTTPException(status_code=503, detail="Remote Access session service unavailable")
    return manager.list_active_sessions(user_id=current_user.id)


@router.get("/remote-access/sessions/history", response_model=list[RemoteAccessSessionRead])
def list_remote_session_history(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if "remote_access:view_sessions" not in get_user_permission_codes(current_user):
        raise HTTPException(status_code=403, detail="Missing permission: remote_access:view_sessions")
    items = (db.query(RemoteAccessSession)
            .filter(RemoteAccessSession.user_id == current_user.id)
            .order_by(RemoteAccessSession.started_at.desc())
            .limit(100).all())
    for item in items:
        item.user_name = current_user.name or current_user.email
    return items


@router.get("/remote-access/sessions/{session_uuid}", response_model=RemoteAccessSessionRead)
def get_remote_session(session_uuid: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user), manager: SessionManager | None = Depends(manager_from_request)):
    if "remote_access:view_sessions" not in get_user_permission_codes(current_user):
        raise HTTPException(status_code=403, detail="Missing permission: remote_access:view_sessions")
    item = manager.get_session(session_uuid) if manager else None
    record = item.record if item is not None else db.query(RemoteAccessSession).filter_by(session_uuid=session_uuid).first()
    if record is None or record.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session does not exist")
    return record


@router.delete("/remote-access/sessions/{session_uuid}", response_model=RemoteAccessSessionRead)
def delete_remote_session(session_uuid: str, background_tasks: BackgroundTasks,
                          db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
                          manager: SessionManager | None = Depends(manager_from_request)):
    if "remote_access:disconnect" not in get_user_permission_codes(current_user):
        raise HTTPException(status_code=403, detail="Missing permission: remote_access:disconnect")
    item = manager.get_session(session_uuid) if manager else None
    record = item.record if item is not None else db.query(RemoteAccessSession).filter_by(session_uuid=session_uuid).first()
    if record is None or record.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Session does not exist")
    # WS cleanup can win the race and remove the in-memory adapter before the
    # REST DELETE arrives. Preserve the durable history and make that request
    # idempotent instead of returning a misleading 404.
    if manager is not None and item is not None:
        notification_ids: list[int] = []
        result = manager.disconnect_session(session_uuid, reason="API disconnect",
                                             notification_ids=notification_ids)
        manager.db.commit()
        if notification_ids:
            background_tasks.add_task(
                _deliver_remote_access_notifications,
                list(notification_ids),
                session_uuid,
            )
    else:
        result = record
    db.commit()
    return result


@router.post("/remote-access/test")
def test_remote_access(payload: RemoteAccessTestRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if "remote_access:test" not in get_user_permission_codes(current_user):
        raise HTTPException(status_code=403, detail="Missing permission: remote_access:test")
    device = db.get(Device, payload.device_id)
    if device is None or not can_access_site(current_user, device.site_id):
        raise HTTPException(status_code=403, detail="Device access denied")
    if payload.remember_credential and "remote_access:manage_credentials" not in get_user_permission_codes(current_user):
        raise HTTPException(status_code=403, detail="Missing permission: remote_access:manage_credentials")
    try:
        result = TestConnectionService(db).test_connection(TestConnectionRequest(**payload.model_dump()))
        # HOST_KEY_UNKNOWN intentionally reports success=false, but the test
        # has deliberately created durable pending trust state that the user
        # must review. Commit only that explicit durable-state outcome; other
        # failed tests must not commit incidental database changes.
        should_commit = _should_commit_test_result(result)
        if should_commit:
            db.commit()
        logger.info(
            "Remote Access test response: success=%s credential_persisted=%s credential_id=%s device_id=%s protocol=%s verified=%s port=%s",
            result.get("success"), result.get("credential_id") is not None,
            result.get("credential_id"), payload.device_id, payload.protocol,
            result.get("credential_id") is not None, result.get("port"),
        )
        return result
    except Exception:
        db.rollback()
        raise


@router.websocket("/remote-access/sessions/{session_uuid}/terminal")
async def remote_access_terminal(websocket: WebSocket, session_uuid: str, db: Session = Depends(get_db)):
    """Authenticate the bearer token, then attach to an existing session."""
    authorization = websocket.headers.get("authorization", "")
    if not authorization:
        for protocol in websocket.headers.get("sec-websocket-protocol", "").split(","):
            protocol = protocol.strip()
            if protocol.startswith("nms-bearer-"):
                authorization = f"Bearer {protocol.removeprefix('nms-bearer-')}"
                break
    token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    claims = decode_access_token_claims(token) if token else None
    subject = (claims or {}).get("sub")
    user = db.query(User).filter(User.email == subject, User.status == "active").first() if subject else None
    user_id = user.id if user is not None else None
    if user is not None and "remote_access:connect" not in get_user_permission_codes(user):
        await websocket.close(code=4403, reason="Permission denied")
        return
    manager = getattr(websocket.app.state, "remote_access_session_manager", None)
    if user_id is None or manager is None:
        await websocket.close(code=4401, reason="Authentication required")
        return
    managed = manager.get_session(session_uuid)
    if managed is None:
        await websocket.close(code=4404, reason="Session is no longer active")
        return
    if managed.record.user_id != user_id:
        await websocket.close(code=4403, reason="Session access denied")
        return
    device = db.get(Device, managed.record.device_id)
    if device is None or not can_access_site(user, device.site_id):
        await websocket.close(code=4403, reason="Device access denied")
        return
    selected_protocol = next((p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",") if p.strip().startswith("nms-bearer-")), None)
    await TerminalWebSocket(manager).serve(websocket, session_uuid, user_id=user_id, subprotocol=selected_protocol)
