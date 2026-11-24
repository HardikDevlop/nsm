"""Unregistered schema definitions for future realtime fencing work.

These tables are intentionally kept out of the application's model metadata and
migration registry until transactional fencing has been approved for rollout.
Importing this module only constructs SQLAlchemy metadata; it performs no I/O.
"""

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Column,
    text,
)


metadata = MetaData()

REALTIME_MONITOR_OWNERSHIP_STATES = (
    "stopped",
    "starting",
    "running",
    "stopping",
    "incomplete_stop",
    "lease_lost",
    "error",
)

realtime_monitor_ownership = Table(
    "realtime_monitor_ownership",
    metadata,
    Column("worker_name", String(64), primary_key=True),
    Column("epoch", BigInteger, nullable=False, server_default=text("0")),
    Column("owner_token", String(160), nullable=True),
    Column("state", String(24), nullable=False),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("epoch >= 0", name="ck_realtime_ownership_epoch_nonnegative"),
    CheckConstraint(
        "state IN ('stopped', 'starting', 'running', 'stopping', 'incomplete_stop', 'lease_lost', 'error')",
        name="ck_realtime_ownership_state_valid",
    ),
    CheckConstraint(
        "(state = 'stopped' AND owner_token IS NULL AND lease_expires_at IS NULL) OR "
        "(state <> 'stopped' AND owner_token IS NOT NULL AND lease_expires_at IS NOT NULL)",
        name="ck_realtime_ownership_token_matches_state",
    ),
)

Index(
    "ix_realtime_monitor_ownership_lease_expires_at",
    realtime_monitor_ownership.c.lease_expires_at,
)
Index("ix_realtime_monitor_ownership_state", realtime_monitor_ownership.c.state)

realtime_notification_outbox = Table(
    "realtime_notification_outbox",
    metadata,
    Column("id", BigInteger, primary_key=True, autoincrement=True),
    Column("event_key", String(180), nullable=False, unique=True),
    Column("alert_id", Integer, ForeignKey("alerts.id", ondelete="RESTRICT"), nullable=False),
    Column("channel", String(60), nullable=False),
    Column("recipient", String(255), nullable=False),
    Column("payload", JSON, nullable=False),
    Column("status", String(24), nullable=False, server_default=text("'pending'")),
    Column("attempt_count", Integer, nullable=False, server_default=text("0")),
    Column("next_attempt_at", DateTime(timezone=True), nullable=False),
    Column("claimed_by", String(160), nullable=True),
    Column("claimed_until", DateTime(timezone=True), nullable=True),
    Column("last_error", String(2000), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("sent_at", DateTime(timezone=True), nullable=True),
    CheckConstraint(
        "status IN ('pending', 'claimed', 'sent', 'failed', 'suppressed')",
        name="ck_realtime_outbox_status_valid",
    ),
    CheckConstraint(
        "attempt_count >= 0",
        name="ck_realtime_outbox_attempt_count_nonnegative",
    ),
    CheckConstraint(
        "(status = 'claimed' AND claimed_by IS NOT NULL AND claimed_until IS NOT NULL) OR "
        "(status <> 'claimed' AND claimed_by IS NULL AND claimed_until IS NULL)",
        name="ck_realtime_outbox_claim_fields_match_status",
    ),
    CheckConstraint(
        "(status = 'sent' AND sent_at IS NOT NULL) OR (status <> 'sent')",
        name="ck_realtime_outbox_sent_timestamp_required",
    ),
)

Index(
    "ix_realtime_outbox_dispatch_due",
    realtime_notification_outbox.c.status,
    realtime_notification_outbox.c.next_attempt_at,
)
Index(
    "ix_realtime_outbox_claim_expiry",
    realtime_notification_outbox.c.claimed_until,
)
Index(
    "ix_realtime_outbox_alert_id",
    realtime_notification_outbox.c.alert_id,
)


__all__ = [
    "metadata",
    "REALTIME_MONITOR_OWNERSHIP_STATES",
    "realtime_monitor_ownership",
    "realtime_notification_outbox",
]
