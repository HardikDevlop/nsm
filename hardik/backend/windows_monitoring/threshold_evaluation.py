"""Device-scoped Windows threshold evaluation without global alerts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Any

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .models import WindowsThresholdConfig, WindowsThresholdNotificationState, windows_now

DEFAULT_THRESHOLD = 40.0
METRICS = {"cpu", "memory", "disk"}
ALERT_TITLES = {
    "cpu": "Windows CPU Usage Threshold",
    "memory": "Windows Memory Usage Threshold",
    "disk": "Windows Disk Usage Threshold",
}


@dataclass(frozen=True)
class ThresholdTransition:
    device_id: int
    metric_name: str
    previous_state: str | None
    state: str | None
    usage: float | None
    threshold: float
    transition: str | None
    evaluated: bool


def _finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _usage_for_metric(metric_name: str, data: Any) -> float | None:
    if metric_name in {"cpu", "memory"}:
        return _finite_number(data.get("usage_percent")) if isinstance(data, dict) else None
    if metric_name != "disk" or not isinstance(data, list):
        return None
    values = [_finite_number(row.get("usage_percent")) for row in data if isinstance(row, dict)]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def _threshold(db: Session, device_id: int, metric_name: str) -> float:
    config = db.query(WindowsThresholdConfig).filter(
        WindowsThresholdConfig.device_id == device_id
    ).first()
    if config is None:
        return DEFAULT_THRESHOLD
    return _finite_number(getattr(config, f"{metric_name}_threshold", None)) or DEFAULT_THRESHOLD


def evaluate_metric(db: Session, device_id: int, metric_name: str, data: Any) -> ThresholdTransition:
    """Evaluate one latest metric snapshot inside the caller's transaction."""
    if metric_name not in METRICS:
        raise ValueError(f"Unsupported Windows threshold metric: {metric_name}")

    threshold = _threshold(db, device_id, metric_name)
    usage = _usage_for_metric(metric_name, data)
    state_query = db.query(WindowsThresholdNotificationState).filter(
        WindowsThresholdNotificationState.device_id == device_id,
        WindowsThresholdNotificationState.metric_name == metric_name,
    )
    state = state_query.with_for_update().first()

    if usage is None:
        return ThresholdTransition(device_id, metric_name, getattr(state, "state", None), getattr(state, "state", None), None, threshold, None, False)

    next_state = "warning" if usage >= threshold else "normal"
    previous_state = state.state if state is not None else "normal"
    if state is None:
        statement = pg_insert(WindowsThresholdNotificationState).values(
            device_id=device_id,
            metric_name=metric_name,
            state=next_state,
            last_value=usage,
            threshold_at_transition=threshold if next_state == "warning" else None,
            last_transition_at=windows_now() if next_state == "warning" else None,
        ).on_conflict_do_nothing(
            index_elements=[WindowsThresholdNotificationState.device_id, WindowsThresholdNotificationState.metric_name]
        ).returning(WindowsThresholdNotificationState.id)
        inserted_id = db.execute(statement).scalar_one_or_none()
        db.flush()
        state = state_query.with_for_update().first()
        if inserted_id is None:
            # Another transaction won the unique key race; its locked row is
            # authoritative for transition detection.
            previous_state = state.state

    transition = None
    if previous_state != next_state:
        transition = "warning" if next_state == "warning" else "recovery"
        state.state = next_state
        state.threshold_at_transition = threshold
        state.last_transition_at = windows_now()
    state.last_value = usage
    state.last_error = None
    db.flush()
    return ThresholdTransition(device_id, metric_name, previous_state, next_state, usage, threshold, transition, True)


def evaluate_metrics(db: Session, device_id: int, metrics: dict[str, Any]) -> list[ThresholdTransition]:
    """Evaluate available CPU, memory and disk data; no email or alert side effects."""
    return [evaluate_metric(db, device_id, name, metrics[name]) for name in ("cpu", "memory", "disk") if name in metrics]


def apply_transition_alert(
    db: Session,
    transition: ThresholdTransition,
    *,
    device_label: str,
    notification_intents: list[Any],
) -> None:
    """Project one Windows transition into the existing alert lifecycle."""
    if transition.transition is None:
        return
    from backend.models import Alert
    from backend.services.alerting import create_threshold_alert, resolve_alert

    title = ALERT_TITLES[transition.metric_name]
    usage = "unavailable" if transition.usage is None else f"{transition.usage:.2f}%"
    if transition.transition == "warning":
        create_threshold_alert(
            db,
            transition.device_id,
            title,
            f"Windows device {device_label}: {transition.metric_name} usage is {usage}; configured threshold is {transition.threshold:.2f}%.",
            "warning",
            notification_intents=notification_intents,
        )
        return

    active = db.query(Alert).filter(
        Alert.device_id == transition.device_id,
        Alert.title == title,
        Alert.status.in_({"open", "acknowledged"}),
        Alert.deleted_at.is_(None),
    ).order_by(Alert.created_at.desc()).first()
    if active is not None:
        resolve_alert(
            db,
            active,
            f"Windows device {device_label}: {transition.metric_name} usage recovered to {usage}, below the configured threshold of {transition.threshold:.2f}%.",
            notification_intents=notification_intents,
        )
