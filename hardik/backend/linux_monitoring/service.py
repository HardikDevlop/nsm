"""Persistence service for Linux Server Monitoring configuration.

This service deliberately has no transport, polling, or scheduler behavior.
"""

import asyncio
from typing import Any
from pydantic import SecretStr

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload

from backend.linux_monitoring.detector import LinuxDetectionError, _snmp_get, _ssh_detect, detect_linux_server
from backend.linux_monitoring.metrics import LinuxMetricCollectionError, collect_linux_metrics
from backend.linux_monitoring.models import LinuxSecurityEvent, LinuxServer, LinuxServerCredential, LinuxServerCurrentMetric, LinuxServerDisk, LinuxServerInterface, LinuxServerMetricSample, LinuxServerMonitoringConfig, LinuxServerSNMPCredential, linux_now
from backend.linux_monitoring.schemas import LinuxSecurityCollectRequest, LinuxServerAddRequest, LinuxServerCredentialUpdate, LinuxServerCreate, LinuxServerMetricsCollectRequest, LinuxServerMonitoringConfigUpdate, LinuxServerUpdate
from backend.linux_monitoring.security import LinuxSecurityCollectionError, collect_security_logs
from backend.utils.crypto import decrypt_secret, encrypt_secret


def _commit(db: Session, item: Any) -> Any:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Linux server data violates a unique or foreign key constraint") from exc
    db.refresh(item)
    return item


def get_server(db: Session, server_id: int) -> LinuxServer:
    server = db.query(LinuxServer).filter(LinuxServer.id == server_id, LinuxServer.deleted_at.is_(None)).first()
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Linux server {server_id} not found")
    return server


def get_server_details(db: Session, server_id: int) -> LinuxServer:
    server = (
        db.query(LinuxServer)
        .options(
            selectinload(LinuxServer.interfaces),
            selectinload(LinuxServer.disks),
            selectinload(LinuxServer.monitoring_config),
        )
        .filter(LinuxServer.id == server_id, LinuxServer.deleted_at.is_(None))
        .first()
    )
    if server is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Linux server {server_id} not found")
    return server


def detect_server(payload: LinuxServerAddRequest | Any) -> tuple[dict[str, Any] | None, list[str], LinuxDetectionError | None]:
    try:
        data, warnings = detect_linux_server(payload)
        return data, warnings, None
    except LinuxDetectionError as exc:
        return None, [], exc


def validate_ssh(payload: LinuxServerAddRequest | Any) -> tuple[dict[str, Any] | None, LinuxDetectionError | None]:
    try:
        return _ssh_detect(payload), None
    except LinuxDetectionError as exc:
        return None, exc


def validate_snmp(payload: LinuxServerAddRequest | Any) -> tuple[bool, LinuxDetectionError | None]:
    try:
        return bool(asyncio.run(asyncio.wait_for(_snmp_get(payload), timeout=payload.timeout_seconds + 1))), None
    except (TimeoutError, asyncio.TimeoutError) as exc:
        return False, LinuxDetectionError("timeout", "SNMPv3 probe timed out")
    except Exception as exc:
        return False, LinuxDetectionError("unavailable", f"SNMPv3 probe was unavailable: {exc}")


def save_detected_server(db: Session, payload: LinuxServerAddRequest, data: dict[str, Any], user_id: int) -> LinuxServer:
    existing = db.query(LinuxServer).filter(LinuxServer.ip_address == data["ip_address"]).first()
    # Older versions used soft-delete. Remove that tombstone before creating
    # a replacement so the unique IP constraint cannot block re-addition.
    if existing and existing.deleted_at is not None:
        db.delete(existing)
        db.flush()
        existing = None
    if existing:
        server = existing
    else:
        server = LinuxServer(ip_address=data["ip_address"], created_by=user_id)
        db.add(server)

    server.site_id = payload.site_id
    server.display_name = payload.display_name
    server.hostname = data["hostname"]
    server.os_name = data.get("os_name")
    server.os_version = data.get("os_version")
    server.architecture = data.get("architecture")
    server.ssh_port = payload.ssh_port
    server.status = "active"
    server.enabled = True
    server.snmp_available = data.get("snmp_available")
    server.snmp_version = data.get("snmp_version")
    server.last_seen_at = linux_now()
    server.last_error = None
    db.flush()

    server.interfaces.clear()
    server.disks.clear()
    for item in data.get("interfaces", []):
        server.interfaces.append(LinuxServerInterface(**item))
    for item in data.get("disks", []):
        server.disks.append(LinuxServerDisk(**item))
    credential = server.credentials[0] if server.credentials else None
    if credential is None:
        server.credentials.append(LinuxServerCredential(
            auth_method=payload.auth_method,
            username=payload.username,
            secret_ref=None,
            enabled=True,
        ))
    else:
        credential.auth_method = payload.auth_method
        credential.username = payload.username
        credential.enabled = True

    # The detection credentials were already validated. Store only the
    # SNMPv3 secrets encrypted so monitoring can recover after a restart.
    if payload.snmp_version == "v3":
        snmp_credential = server.snmp_credential
        if snmp_credential is None:
            snmp_credential = LinuxServerSNMPCredential(linux_server_id=server.id)
            db.add(snmp_credential)
        snmp_credential.username = payload.snmp_username or ""
        snmp_credential.auth_protocol = payload.snmp_auth_protocol
        snmp_credential.encrypted_auth_password = encrypt_secret(
            payload.snmp_auth_password.get_secret_value() if payload.snmp_auth_password else None
        )
        snmp_credential.privacy_protocol = payload.snmp_privacy_protocol
        snmp_credential.encrypted_privacy_password = encrypt_secret(
            payload.snmp_privacy_password.get_secret_value() if payload.snmp_privacy_password else None
        )
        snmp_credential.security_level = payload.snmp_security_level
        snmp_credential.enabled = True
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Detected Linux server conflicts with an existing record") from exc
    return get_server_details(db, server.id)


def collect_metrics(db: Session, server_id: int, payload: LinuxServerMetricsCollectRequest) -> tuple[LinuxServerMetricSample | None, LinuxMetricCollectionError | None]:
    server = get_server(db, server_id)
    previous = db.query(LinuxServerMetricSample).filter(
        LinuxServerMetricSample.linux_server_id == server.id,
        LinuxServerMetricSample.collection_status == "success",
    ).order_by(LinuxServerMetricSample.collected_at.desc()).first()
    try:
        values = collect_linux_metrics(server.ip_address, payload, previous)
    except LinuxMetricCollectionError as exc:
        server.last_error = exc.message
        failed = LinuxServerMetricSample(
            linux_server_id=server.id,
            collection_status="error",
            details={"warnings": [exc.message]},
            error_message=exc.message,
        )
        db.add(failed)
        db.commit()
        db.refresh(failed)
        return failed, exc

    metric_fields = (
        "cpu_percent", "memory_percent", "swap_percent", "disk_percent",
        "load_1m", "load_5m", "load_15m", "uptime_seconds",
    )
    if not any(values.get(field) is not None for field in metric_fields):
        error = LinuxMetricCollectionError(
            "unavailable",
            "SNMPv3 authenticated, but no Linux metric OIDs are accessible; "
            "check the snmpd view includes .1.3.6.1.2.1.25 and .1.3.6.1.4.1.2021",
        )
        server.last_error = error.message
        failed = LinuxServerMetricSample(
            linux_server_id=server.id,
            collected_at=linux_now(),
            collection_status="error",
            details={"warnings": (values.get("details") or {}).get("warnings", [])},
            error_message=error.message,
        )
        db.add(failed)
        db.commit()
        db.refresh(failed)
        return failed, error

    sample = LinuxServerMetricSample(linux_server_id=server.id, collected_at=linux_now(), **values)
    server.status = "active"
    server.snmp_available = True
    server.snmp_version = "v3"
    server.last_seen_at = linux_now()
    # A successful SNMP sample may legitimately omit optional agent tables.
    # Keep those warnings in sample.details instead of marking the server down.
    server.last_error = None
    db.add(sample)
    current = db.query(LinuxServerCurrentMetric).filter_by(linux_server_id=server.id).first()
    if current is None:
        current = LinuxServerCurrentMetric(linux_server_id=server.id)
        db.add(current)
    for field in (
        "collected_at", "cpu_percent", "memory_percent", "swap_percent", "disk_percent",
        "disk_io_read_bytes_per_sec", "disk_io_write_bytes_per_sec", "load_1m", "load_5m",
        "load_15m", "uptime_seconds", "network_rx_bytes", "network_tx_bytes",
        "network_rx_bytes_per_sec", "network_tx_bytes_per_sec", "packets_per_sec",
        "interface_errors", "interface_drops", "process_count", "details",
    ):
        setattr(current, field, getattr(sample, field))
    db.commit()
    db.refresh(sample)
    return sample, None


def get_current_metrics(db: Session, server_id: int) -> LinuxServerCurrentMetric:
    get_server(db, server_id)
    current = db.query(LinuxServerCurrentMetric).filter_by(linux_server_id=server_id).first()
    if current is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No current Linux metrics have been collected yet")
    return current


def cleanup_expired_history(db: Session, cutoff: Any, batch_size: int = 1000) -> tuple[int, int]:
    """Delete only indexed historical rows in bounded batches; current rows are untouched."""
    deleted_metrics = 0
    deleted_security = 0
    while True:
        ids = [row[0] for row in db.query(LinuxServerMetricSample.id).filter(
            LinuxServerMetricSample.collected_at < cutoff
        ).order_by(LinuxServerMetricSample.collected_at, LinuxServerMetricSample.id).limit(batch_size).all()]
        if not ids:
            break
        db.query(LinuxServerMetricSample).filter(LinuxServerMetricSample.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        deleted_metrics += len(ids)
    while True:
        ids = [row[0] for row in db.query(LinuxSecurityEvent.id).filter(
            LinuxSecurityEvent.event_timestamp < cutoff
        ).order_by(LinuxSecurityEvent.event_timestamp, LinuxSecurityEvent.id).limit(batch_size).all()]
        if not ids:
            break
        db.query(LinuxSecurityEvent).filter(LinuxSecurityEvent.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        deleted_security += len(ids)
    return deleted_metrics, deleted_security


def collect_security(db: Session, server_id: int, payload: LinuxSecurityCollectRequest) -> tuple[list[LinuxSecurityEvent], int, bool, list[str], LinuxSecurityCollectionError | None]:
    server = get_server(db, server_id)
    try:
        raw_events, logs_available, warnings = collect_security_logs(server.ip_address, server.ssh_port, payload)
    except LinuxSecurityCollectionError as exc:
        return [], 0, False, [], exc

    if not raw_events:
        return [], 0, logs_available, warnings, None

    hashes = [item["event_hash"] for item in raw_events]
    existing_hashes = {
        value[0]
        for value in db.query(LinuxSecurityEvent.event_hash).filter(
            LinuxSecurityEvent.linux_server_id == server.id,
            LinuxSecurityEvent.event_hash.in_(hashes),
        ).all()
    }
    new_events = [
        LinuxSecurityEvent(linux_server_id=server.id, **item)
        for item in raw_events
        if item["event_hash"] not in existing_hashes
    ]
    if new_events:
        db.add_all(new_events)
        db.commit()
        for event in new_events:
            db.refresh(event)
    server.last_seen_at = linux_now()
    server.status = "active"
    db.commit()
    return new_events, len(raw_events) - len(new_events), logs_available, warnings, None


def create_server(db: Session, payload: LinuxServerCreate, user_id: int) -> LinuxServer:
    server = LinuxServer(**payload.model_dump(), created_by=user_id)
    db.add(server)
    return _commit(db, server)


def update_server(db: Session, server_id: int, payload: LinuxServerUpdate) -> LinuxServer:
    server = get_server(db, server_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(server, field, value)
    return _commit(db, server)


def delete_server(db: Session, server_id: int) -> dict[str, str]:
    server = get_server(db, server_id)
    # A deleted server must release its IP and all dependent records. This
    # also makes a later discovery create a fresh database record.
    db.delete(server)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Linux server data is still in use") from exc
    return {"detail": f"Linux server {server_id} deleted"}


def upsert_config(db: Session, server_id: int, payload: LinuxServerMonitoringConfigUpdate) -> LinuxServerMonitoringConfig:
    server = get_server(db, server_id)
    config = db.query(LinuxServerMonitoringConfig).filter(LinuxServerMonitoringConfig.linux_server_id == server.id).first()
    if config is None:
        config = LinuxServerMonitoringConfig(linux_server_id=server.id, **payload.model_dump())
        db.add(config)
    else:
        for field, value in payload.model_dump().items():
            setattr(config, field, value)
    return _commit(db, config)


def get_config(db: Session, server_id: int) -> LinuxServerMonitoringConfig:
    server = get_server(db, server_id)
    config = db.query(LinuxServerMonitoringConfig).filter(LinuxServerMonitoringConfig.linux_server_id == server.id).first()
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Linux server {server_id} monitoring config not found")
    return config


def save_monitoring_credential(db: Session, server_id: int, payload: Any) -> LinuxServerSNMPCredential:
    server = get_server(db, server_id)
    values = payload.model_dump()
    credential = db.query(LinuxServerSNMPCredential).filter_by(linux_server_id=server.id).first()
    if credential is None:
        credential = LinuxServerSNMPCredential(linux_server_id=server.id)
        db.add(credential)
    credential.username = values["username"]
    credential.auth_protocol = values.get("auth_protocol")
    credential.encrypted_auth_password = encrypt_secret(values["auth_password"].get_secret_value() if values.get("auth_password") else None)
    credential.privacy_protocol = values.get("privacy_protocol")
    credential.encrypted_privacy_password = encrypt_secret(values["privacy_password"].get_secret_value() if values.get("privacy_password") else None)
    credential.security_level = values.get("security_level")
    credential.enabled = True
    return _commit(db, credential)


def metrics_payload_from_credential(credential: LinuxServerSNMPCredential, timeout_seconds: float = 15.0) -> LinuxServerMetricsCollectRequest:
    return LinuxServerMetricsCollectRequest(
        username=credential.username,
        auth_protocol=credential.auth_protocol,
        auth_password=SecretStr(decrypt_secret(credential.encrypted_auth_password) or "") if credential.encrypted_auth_password else None,
        privacy_protocol=credential.privacy_protocol,
        privacy_password=SecretStr(decrypt_secret(credential.encrypted_privacy_password) or "") if credential.encrypted_privacy_password else None,
        security_level=credential.security_level,
        timeout_seconds=timeout_seconds,
    )


def add_credential(db: Session, server_id: int, payload: Any) -> LinuxServerCredential:
    server = get_server(db, server_id)
    credential = LinuxServerCredential(linux_server_id=server.id, **payload.model_dump())
    db.add(credential)
    return _commit(db, credential)


def update_credential(db: Session, server_id: int, credential_id: int, payload: LinuxServerCredentialUpdate) -> LinuxServerCredential:
    server = get_server(db, server_id)
    credential = db.query(LinuxServerCredential).filter(
        LinuxServerCredential.id == credential_id,
        LinuxServerCredential.linux_server_id == server.id,
    ).first()
    if credential is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Linux server credential not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(credential, field, value)
    return _commit(db, credential)
