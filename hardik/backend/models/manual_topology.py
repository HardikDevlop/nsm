"""Database records for manual topology baselines and live reconciliation."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.session import Base
from backend.models.snmp import SNMPBase, now


class ManualTopologySnapshot(SNMPBase, Base):
    __tablename__ = "manual_topology_snapshots"

    name: Mapped[str] = mapped_column(String(160), default="Manual topology")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reconcile_status: Mapped[str] = mapped_column(String(30), default="not_checked")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)


class ManualTopologyChange(SNMPBase, Base):
    __tablename__ = "manual_topology_changes"

    snapshot_id: Mapped[int] = mapped_column(ForeignKey("manual_topology_snapshots.id", ondelete="CASCADE"), index=True)
    change_type: Mapped[str] = mapped_column(String(50), index=True)
    signature: Mapped[str] = mapped_column(String(500), index=True)
    expected_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    observed_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
