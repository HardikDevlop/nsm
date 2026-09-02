from datetime import datetime
from sqlalchemy.orm import Session
from backend.models import AuditLog, ConfigurationCompliancePolicy, ConfigurationComplianceViolation, DeviceConfigurationVersion
from backend.utils.crypto import decrypt_secret

def evaluate_policy(db: Session, policy_id: int, device_id: int, initiated_by: int | None = None):
    policy = db.get(ConfigurationCompliancePolicy, policy_id)
    version = db.query(DeviceConfigurationVersion).filter_by(device_id=device_id).order_by(DeviceConfigurationVersion.version.desc()).first()
    if not policy or not version: raise LookupError("Policy or configuration version not found")
    lines = (decrypt_secret(version.encrypted_content) or "").splitlines(); rules = policy.rules or {}
    missing = [line for line in rules.get("required", []) if line not in lines]; found = [line for line in rules.get("forbidden", []) if line in lines]
    existing = db.query(ConfigurationComplianceViolation).filter_by(policy_id=policy_id, device_id=device_id, version=version.version).first()
    if not missing and not found:
        if existing and existing.status != "resolved": existing.status = "resolved"; existing.resolved_at = datetime.utcnow(); existing.resolved_by = initiated_by
        db.add(AuditLog(user_id=initiated_by, action="CONFIGURATION_COMPLIANCE_EVALUATE", resource_name=f"policy:{policy_id}:device:{device_id}:compliant")); db.flush(); return None
    if existing: return existing
    item = ConfigurationComplianceViolation(policy_id=policy_id, device_id=device_id, version=version.version, severity=rules.get("severity", "medium"), status="open", evidence={"missing": missing, "forbidden": found}, recommendation=rules.get("recommendation", "Review the configuration; no automatic changes were made."), detected_at=datetime.utcnow())
    db.add(item); db.add(AuditLog(user_id=initiated_by, action="CONFIGURATION_COMPLIANCE_VIOLATION", resource_name=f"policy:{policy_id}:device:{device_id}:v{version.version}")); db.flush(); return item
