"""Remote Access terminal WebSocket endpoint."""
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket
import logging
from sqlalchemy.orm import Session

from backend.auth.security import decode_access_token_claims
from backend.database.session import get_db
from backend.models import Device, RemoteAccessSession, User
from backend.schemas.remote_access import RemoteAccessSessionCreate, RemoteAccessSessionRead, RemoteAccessTestRequest, SSHHostKeyScanRequest, SSHHostKeyTrustRequest, SSHHostKeyRead
from backend.services.remote_access.session_manager import SessionManager
from backend.services.remote_access.test_connection import TestConnectionRequest, TestConnectionService
from backend.dependencies import get_current_user, get_user_permission_codes, require_permission
from backend.auth.authorization import can_access_site

from backend.services.remote_access.terminal_websocket import TerminalWebSocket
from backend.services.remote_access.host_keys import SSHHostKeyError, SSHHostKeyService

logger = logging.getLogger(__name__)

router = APIRouter()


def _manage_host_key_permission(user: User) -> None:
    if "remote_access:manage_credentials" not in get_user_permission_codes(user):
        raise HTTPException(status_code=403, detail="Missing permission: remote_access:manage_credentials")


def _host_key_response(item):
    return {"id": item.id, "device_id": item.device_id, "host": item.host, "port": item.port,
            "key_type": item.key_type, "fingerprint": item.fingerprint, "status": item.status}


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
def create_remote_session(payload: RemoteAccessSessionCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user), manager: SessionManager | None = Depends(manager_from_request)):
    if "remote_access:connect" not in get_user_permission_codes(current_user):
        raise HTTPException(status_code=403, detail="Missing permission: remote_access:connect")
    if payload.remember_credential and "remote_access:manage_credentials" not in get_user_permission_codes(current_user):
        raise HTTPException(status_code=403, detail="Missing permission: remote_access:manage_credentials")
    device = db.get(Device, payload.device_id)
    if device is None or not can_access_site(current_user, device.site_id):
        raise HTTPException(status_code=403, detail="Device access denied")
    if manager is None:
        raise HTTPException(status_code=503, detail="Remote Access session service unavailable")
    try:
        item = manager.create_session(user_id=current_user.id, **payload.model_dump())
        manager.db.commit()
        return item
    except Exception as exc:
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
    return (db.query(RemoteAccessSession)
            .filter(RemoteAccessSession.user_id == current_user.id)
            .order_by(RemoteAccessSession.started_at.desc())
            .limit(100).all())


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
def delete_remote_session(session_uuid: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user), manager: SessionManager | None = Depends(manager_from_request)):
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
        result = manager.disconnect_session(session_uuid, reason="API disconnect")
        manager.db.commit()
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
        if result.get("success") and result.get("credential_id") is not None:
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
    if managed is None or managed.record.user_id != user_id:
        await websocket.close(code=4403, reason="Session access denied")
        return
    device = db.get(Device, managed.record.device_id)
    if device is None or not can_access_site(user, device.site_id):
        await websocket.close(code=4403, reason="Device access denied")
        return
    selected_protocol = next((p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",") if p.strip().startswith("nms-bearer-")), None)
    await TerminalWebSocket(manager).serve(websocket, session_uuid, user_id=user_id, subprotocol=selected_protocol)
