from __future__ import annotations

import hashlib
from difflib import SequenceMatcher
from datetime import datetime

from sqlalchemy.orm import Session

from backend.models import AuditLog, ConfigurationComparison, Device, DeviceConfigurationVersion
from backend.utils.crypto import decrypt_secret, encrypt_secret


def record_configuration(db: Session, device_id: int, content: str, source: str, captured_by: int | None = None, is_startup: bool = False) -> tuple[DeviceConfigurationVersion, bool]:
    if not content or not content.strip():
        raise ValueError("Configuration content cannot be empty")
    if db.query(Device).filter(Device.id == device_id).first() is None:
        raise LookupError("Device not found")
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    latest = db.query(DeviceConfigurationVersion).filter_by(device_id=device_id).order_by(DeviceConfigurationVersion.version.desc()).first()
    if latest and latest.checksum == checksum:
        db.add(AuditLog(user_id=captured_by, action="CONFIGURATION_CAPTURE_UNCHANGED", resource_name=f"device_configurations:{device_id}:v{latest.version}"))
        db.flush()
        return latest, False
    version = (latest.version + 1) if latest else 1
    item = DeviceConfigurationVersion(device_id=device_id, version=version, source=source, checksum=checksum, encrypted_content=encrypt_secret(content), is_startup=is_startup, captured_at=datetime.utcnow(), captured_by=captured_by)
    db.add(item); db.flush()
    db.add(AuditLog(user_id=captured_by, action="CONFIGURATION_CAPTURE", resource_name=f"device_configurations:{device_id}:v{version}"))
    return item, True


def compare_configurations(db: Session, device_id: int, from_version: int, to_version: int, initiated_by: int | None = None) -> ConfigurationComparison:
    if from_version == to_version:
        raise ValueError("Configuration comparison requires two different versions")
    versions = db.query(DeviceConfigurationVersion).filter(DeviceConfigurationVersion.device_id == device_id, DeviceConfigurationVersion.version.in_((from_version, to_version))).all()
    by_version = {item.version: item for item in versions}
    if len(by_version) != 2:
        raise LookupError("Both configuration versions must exist for this device")
    before = (decrypt_secret(by_version[from_version].encrypted_content) or "").splitlines()
    after = (decrypt_secret(by_version[to_version].encrypted_content) or "").splitlines()
    added, removed, changed = [], [], []
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, before, after).get_opcodes():
        if tag == "insert": added.extend(after[j1:j2])
        elif tag == "delete": removed.extend(before[i1:i2])
        elif tag == "replace":
            changed.append({"from_line": before[i1:i2], "to_line": after[j1:j2], "from_number": i1 + 1, "to_number": j1 + 1})
    item = ConfigurationComparison(device_id=device_id, from_version=from_version, to_version=to_version, added_lines=added, removed_lines=removed, changed_lines=changed, initiated_by=initiated_by, created_at=datetime.utcnow())
    db.add(item); db.flush(); db.add(AuditLog(user_id=initiated_by, action="CONFIGURATION_COMPARE", resource_name=f"device_configurations:{device_id}:v{from_version}->v{to_version}"))
    return item
