"""Manual topology persistence and live-vs-baseline reconciliation API."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.snmp_device_routes import get_snmp_topology
from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.models import User
from backend.models.manual_topology import ManualTopologyChange, ManualTopologySnapshot

router = APIRouter(prefix="/api/v1")


class ManualTopologySnapshotPayload(BaseModel):
    name: str = Field(default="Manual topology", max_length=160)
    payload: dict[str, Any] = Field(default_factory=dict)


class ManualTopologyResolvePayload(BaseModel):
    action: str = Field(pattern="^(accept_real_change|keep_manual)$")
    note: str | None = Field(default=None, max_length=500)


def _link_key(link: dict[str, Any]) -> tuple[tuple[str, str], tuple[str, str]]:
    left = (str(link.get("from") or link.get("source_node") or ""), str(link.get("fromPort") or link.get("source_port") or ""))
    right = (str(link.get("to") or link.get("target_node") or ""), str(link.get("toPort") or link.get("target_port") or ""))
    return tuple(sorted((left, right)))  # type: ignore[return-value]


def _device_maps(payload: dict[str, Any]) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    manual_to_backend: dict[str, str] = {}
    backend_to_manual: dict[str, str] = {}
    names: dict[str, str] = {}
    for device in payload.get("devices", []):
        manual_id = str(device.get("id") or "")
        backend_id = device.get("backendId")
        if manual_id and backend_id is not None:
            manual_to_backend[manual_id] = str(backend_id)
            backend_to_manual[str(backend_id)] = manual_id
        name = str(device.get("name") or "").strip().lower()
        if name and backend_id is not None:
            names[name] = str(backend_id)
    return manual_to_backend, backend_to_manual, names


def _observed_links(live: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    manual_to_backend, backend_to_manual, names = _device_maps(payload)
    result: list[dict[str, Any]] = []
    for raw in live.get("links", []) or []:
        source = str(raw.get("source_node") or raw.get("source_device_id") or "")
        target = str(raw.get("target_node") or raw.get("target_device_id") or "")
        source = names.get(source.lower(), source)
        target = names.get(target.lower(), target)
        source = backend_to_manual.get(source, source)
        target = backend_to_manual.get(target, target)
        if source not in backend_to_manual.values() or target not in backend_to_manual.values():
            continue
        source_port = str(raw.get("source_port") or raw.get("local_port") or raw.get("from_port") or "")
        target_port = str(raw.get("target_port") or raw.get("remote_port") or raw.get("to_port") or "")
        result.append({
            "from": source,
            "to": target,
            "fromPort": source_port,
            "toPort": target_port,
            "label": f"{source_port} -> {target_port}",
            "verified": bool(raw.get("verified", True)),
        })
    return result


def _change_read(change: ManualTopologyChange) -> dict[str, Any]:
    return {
        "id": change.id,
        "change_type": change.change_type,
        "signature": change.signature,
        "expected": change.expected_state,
        "observed": change.observed_state,
        "status": change.status,
        "detected_at": change.detected_at.isoformat() if change.detected_at else None,
        "resolved_at": change.resolved_at.isoformat() if change.resolved_at else None,
        "resolution_note": change.resolution_note,
    }


def _snapshot_read(snapshot: ManualTopologySnapshot, changes: list[ManualTopologyChange]) -> dict[str, Any]:
    return {
        "id": snapshot.id,
        "name": snapshot.name,
        "payload": snapshot.payload or {},
        "reconcile_status": snapshot.reconcile_status,
        "last_reconciled_at": snapshot.last_reconciled_at.isoformat() if snapshot.last_reconciled_at else None,
        "changes": [_change_read(change) for change in changes],
    }


@router.post("/manual-topology/snapshots")
def create_manual_topology_snapshot(
    request: ManualTopologySnapshotPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("topology:read")),
) -> dict[str, Any]:
    snapshot = ManualTopologySnapshot(name=request.name, payload=request.payload, created_by=current_user.id)
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return _snapshot_read(snapshot, [])


@router.put("/manual-topology/snapshots/{snapshot_id}")
def update_manual_topology_snapshot(
    snapshot_id: int,
    request: ManualTopologySnapshotPayload,
    db: Session = Depends(get_db),
    _: User = Depends(require_permission("topology:read")),
) -> dict[str, Any]:
    snapshot = db.get(ManualTopologySnapshot, snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Manual topology snapshot not found")
    snapshot.name = request.name
    snapshot.payload = request.payload
    db.commit()
    db.refresh(snapshot)
    changes = db.query(ManualTopologyChange).filter(ManualTopologyChange.snapshot_id == snapshot.id, ManualTopologyChange.status == "pending").all()
    return _snapshot_read(snapshot, changes)


@router.get("/manual-topology/snapshots/latest")
def get_latest_manual_topology_snapshot(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("topology:read")),
) -> dict[str, Any] | None:
    snapshot = db.query(ManualTopologySnapshot).filter(ManualTopologySnapshot.created_by == current_user.id).order_by(ManualTopologySnapshot.updated_at.desc()).first()
    if not snapshot:
        return None
    changes = db.query(ManualTopologyChange).filter(ManualTopologyChange.snapshot_id == snapshot.id, ManualTopologyChange.status == "pending").all()
    return _snapshot_read(snapshot, changes)


@router.post("/manual-topology/snapshots/{snapshot_id}/reconcile")
def reconcile_manual_topology(
    snapshot_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("topology:read")),
) -> dict[str, Any]:
    snapshot = db.get(ManualTopologySnapshot, snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Manual topology snapshot not found")
    try:
        live = get_snmp_topology(device_id=None, refresh=True, db=db, _=current_user)
    except Exception as error:
        snapshot.reconcile_status = "error"
        db.commit()
        raise HTTPException(status_code=502, detail=f"Live topology unavailable: {error}") from error

    payload = snapshot.payload or {}
    baseline_links = [link for link in payload.get("links", []) if link.get("fromPort") and link.get("toPort")]
    observed_links = _observed_links(live, payload)
    baseline_by_key = {_link_key(link): link for link in baseline_links}
    observed_by_key = {_link_key(link): link for link in observed_links}
    differences: list[tuple[str, str, dict[str, Any] | None, dict[str, Any] | None]] = []
    for key in baseline_by_key.keys() - observed_by_key.keys():
        differences.append(("CONNECTION_DISCONNECTED", repr(key), baseline_by_key[key], None))
    for key in observed_by_key.keys() - baseline_by_key.keys():
        differences.append(("CONNECTION_ADDED", repr(key), None, observed_by_key[key]))

    live_devices = {str(device.get("id")): device for device in live.get("devices", []) or []}
    for device in payload.get("devices", []):
        backend_id = device.get("backendId")
        if backend_id is None:
            continue
        observed_device = live_devices.get(str(backend_id))
        if not observed_device:
            continue
        observed_status = str(observed_device.get("status") or "unknown").lower()
        baseline_status = str(device.get("status") or "online").lower()
        observed_online = observed_status not in {"offline", "down", "unreachable", "unknown"}
        baseline_online = baseline_status not in {"offline", "down", "unreachable", "unknown"}
        if observed_online != baseline_online:
            change_type = "DEVICE_ONLINE" if observed_online else "DEVICE_OFFLINE"
            signature = f"device:{backend_id}:{observed_status}"
            differences.append((change_type, signature, {"status": baseline_status, "device_id": backend_id}, {"status": observed_status, "device_id": backend_id}))

    now = datetime.now().replace(microsecond=0)
    for change_type, signature, expected, observed in differences:
        existing = db.query(ManualTopologyChange).filter(
            ManualTopologyChange.snapshot_id == snapshot.id,
            ManualTopologyChange.change_type == change_type,
            ManualTopologyChange.signature == signature,
            ManualTopologyChange.status.in_(["pending", "accepted", "kept_manual"]),
        ).order_by(ManualTopologyChange.updated_at.desc()).first()
        if not existing:
            db.add(ManualTopologyChange(snapshot_id=snapshot.id, change_type=change_type, signature=signature, expected_state=expected, observed_state=observed))

    snapshot.last_reconciled_at = now
    snapshot.reconcile_status = "changes_found" if differences else "in_sync"
    db.commit()
    changes = db.query(ManualTopologyChange).filter(ManualTopologyChange.snapshot_id == snapshot.id, ManualTopologyChange.status == "pending").order_by(ManualTopologyChange.detected_at.desc()).all()
    return {**_snapshot_read(snapshot, changes), "live": {"links": observed_links, "devices": live.get("devices", [])}}


@router.post("/manual-topology/snapshots/{snapshot_id}/changes/{change_id}/resolve")
def resolve_manual_topology_change(
    snapshot_id: int,
    change_id: int,
    request: ManualTopologyResolvePayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("topology:read")),
) -> dict[str, Any]:
    snapshot = db.get(ManualTopologySnapshot, snapshot_id)
    change = db.query(ManualTopologyChange).filter(ManualTopologyChange.id == change_id, ManualTopologyChange.snapshot_id == snapshot_id).first()
    if not snapshot or not change:
        raise HTTPException(status_code=404, detail="Topology change not found")
    if request.action == "accept_real_change" and change.change_type.startswith("CONNECTION"):
        links = [link for link in (snapshot.payload or {}).get("links", []) if _link_key(link) != _link_key(change.expected_state or {})]
        if change.observed_state:
            links.append(change.observed_state)
        payload = dict(snapshot.payload or {})
        payload["links"] = links
        snapshot.payload = payload
        change.status = "accepted"
    elif request.action == "accept_real_change" and change.change_type.startswith("DEVICE_"):
        observed = change.observed_state or {}
        payload = dict(snapshot.payload or {})
        payload["devices"] = [
            {**device, "status": observed.get("status", device.get("status", "unknown"))}
            if str(device.get("backendId")) == str(observed.get("device_id")) else device
            for device in payload.get("devices", [])
        ]
        snapshot.payload = payload
        change.status = "accepted"
    else:
        change.status = "kept_manual"
    change.resolved_at = datetime.now()
    change.resolved_by = current_user.id
    change.resolution_note = request.note
    db.commit()
    pending = db.query(ManualTopologyChange).filter(ManualTopologyChange.snapshot_id == snapshot.id, ManualTopologyChange.status == "pending").all()
    return _snapshot_read(snapshot, pending)
