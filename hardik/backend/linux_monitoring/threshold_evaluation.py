"""Linux utilization threshold evaluation for completed metric collections."""

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.models import Alert
from backend.services.alerting import create_threshold_alert, resolve_alert
from .models import LinuxServer, LinuxServerThresholdConfig


@dataclass(frozen=True)
class ThresholdResult:
    metric_name: str
    value: float | None
    state: str
    warning_threshold: float
    critical_threshold: float


def classify_metric(value: float | None, warning: float, critical: float) -> str:
    """Classify a value without treating unavailable metrics as recovery."""
    if value is None:
        return "UNAVAILABLE"
    if value >= critical:
        return "CRITICAL"
    if value >= warning:
        return "WARNING"
    return "NORMAL"


def _active_alert(db: Session, server_id: int, title: str) -> Alert | None:
    return db.query(Alert).filter(
        # Linux servers are stored outside the generic devices table; keep
        # the stable server identity in the title rather than violating the
        # Alert.device_id foreign key.
        Alert.linux_server_id == server_id,
        Alert.title == title,
        Alert.status.in_(("open", "acknowledged")),
        Alert.deleted_at.is_(None),
    ).order_by(Alert.created_at.desc()).first()


def _evaluate_one(
    db: Session,
    server: LinuxServer,
    metric_name: str,
    value: float | None,
    warning: float,
    critical: float,
) -> ThresholdResult:
    state = classify_metric(value, warning, critical)
    result = ThresholdResult(metric_name, value, state, warning, critical)
    if state == "UNAVAILABLE":
        return result

    title = f"Linux {metric_name.upper()} threshold: {server.hostname}"
    active = _active_alert(db, server.id, title)
    if state == "NORMAL":
        if active is not None:
            resolve_alert(
                db,
                active,
                f"{metric_name.upper()} recovered to {value:.2f}%, below the configured warning threshold of {warning:.2f}%.",
            )
        return result

    severity = "critical" if state == "CRITICAL" else "warning"
    if active is not None and active.severity == severity:
        return result
    if active is not None:
        resolve_alert(
            db,
            active,
            f"{metric_name.upper()} changed from {active.severity.upper()} to {state}; superseding the previous threshold alert.",
        )
    threshold = critical if state == "CRITICAL" else warning
    create_threshold_alert(
        db,
        device_id=None,
        linux_server_id=server.id,
        title=title,
        description=f"Linux server {server.hostname}: {metric_name.upper()} is {value:.2f}%, at or above the configured {state.lower()} threshold of {threshold:.2f}%.",
        severity=severity,
    )
    return result


def evaluate_sample(db: Session, server_id: int, sample) -> list[ThresholdResult]:
    """Evaluate one successful sample using the server's current policy."""
    server = db.query(LinuxServer).filter(
        LinuxServer.id == server_id,
        LinuxServer.deleted_at.is_(None),
    ).first()
    if server is None:
        return []
    config = db.query(LinuxServerThresholdConfig).filter_by(
        linux_server_id=server_id,
        enabled=True,
    ).first()
    if config is None:
        return []

    return [
        _evaluate_one(db, server, "cpu", sample.cpu_percent, config.cpu_warning_percent, config.cpu_critical_percent),
        _evaluate_one(db, server, "memory", sample.memory_percent, config.memory_warning_percent, config.memory_critical_percent),
        _evaluate_one(db, server, "disk", sample.disk_percent, config.disk_warning_percent, config.disk_critical_percent),
    ]
