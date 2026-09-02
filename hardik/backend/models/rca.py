from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base


def utc_now() -> datetime:
    return datetime.now(ZoneInfo("Asia/Kolkata")).replace(tzinfo=None)


class RCAIncident(Base):
    __tablename__ = "rca_incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    correlation_key: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    root_kind: Mapped[str] = mapped_column(String(30))
    root_label: Mapped[str] = mapped_column(String(180))
    root_device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    root_interface_id: Mapped[int | None] = mapped_column(ForeignKey("interfaces.id", ondelete="SET NULL"), nullable=True)
    root_ci_id: Mapped[int | None] = mapped_column(ForeignKey("cmdb_configuration_items.id", ondelete="SET NULL"), nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    impact_summary: Mapped[str] = mapped_column(Text)
    window_start: Mapped[datetime] = mapped_column(DateTime, index=True)
    window_end: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    evidence: Mapped[list["RCAEvidence"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )


class RCAEvidence(Base):
    __tablename__ = "rca_evidence"
    __table_args__ = (
        UniqueConstraint("incident_id", "evidence_type", "alert_id", "relationship_id", name="uq_rca_evidence_item"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("rca_incidents.id", ondelete="CASCADE"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(40))
    alert_id: Mapped[int | None] = mapped_column(ForeignKey("alerts.id", ondelete="SET NULL"), nullable=True, index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id", ondelete="SET NULL"), nullable=True)
    relationship_id: Mapped[int | None] = mapped_column(ForeignKey("cmdb_ci_relationships.id", ondelete="SET NULL"), nullable=True)
    score: Mapped[float] = mapped_column(Float, default=0)
    reason: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    incident: Mapped[RCAIncident] = relationship(back_populates="evidence")
