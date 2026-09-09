from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from backend.models.change import ChangeHistory, ChangeRequest


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"submitted"},
    "submitted": {"approved", "rejected"},
    "approved": {"scheduled"},
    "scheduled": {"implementing"},
    "implementing": {"implemented", "rolled_back"},
    "implemented": {"closed"},
    "rolled_back": {"closed"},
    "rejected": set(),
    "closed": set(),
}

TRANSITION_ACTIONS = {
    "submitted": "submitted",
    "approved": "approved",
    "rejected": "rejected",
    "scheduled": "scheduled",
    "implementing": "implementation_started",
    "implemented": "implementation_completed",
    "rolled_back": "rolled_back",
    "closed": "closed",
}


class ChangeTransitionError(ValueError):
    pass


def transition_change(db: Session, change: ChangeRequest, target: str, user_id: int) -> None:
    current = change.status
    if target == current:
        raise ChangeTransitionError(f"Change is already {current}")
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ChangeTransitionError(f"Invalid change transition: {current} -> {target}")

    change.status = target
    change.updated_at = datetime.utcnow()
    if target == "closed":
        change.closed_at = change.closed_at or datetime.utcnow()
    db.add(ChangeHistory(
        change_id=change.id,
        changed_by=user_id,
        action=TRANSITION_ACTIONS[target],
        old_value=current,
        new_value=target,
        created_at=datetime.utcnow(),
    ))
