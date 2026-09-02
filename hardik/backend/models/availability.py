from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.database.session import Base
class AvailabilityReport(Base):
    __tablename__ = "availability_reports"
    __table_args__ = (UniqueConstraint("entity_type", "entity_id", "window_start", "window_end", name="uq_availability_report_window"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(30), index=True); entity_id: Mapped[int] = mapped_column(Integer, index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime, index=True); window_end: Mapped[datetime] = mapped_column(DateTime)
    total_seconds: Mapped[int] = mapped_column(Integer)
    monitored_duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    uptime_seconds: Mapped[int] = mapped_column(Integer, default=0)
    downtime_seconds: Mapped[int] = mapped_column(Integer, default=0)
    unknown_seconds: Mapped[int] = mapped_column(Integer, default=0)
    planned_downtime_seconds: Mapped[int] = mapped_column(Integer, default=0)
    unplanned_downtime_seconds: Mapped[int] = mapped_column(Integer, default=0)
    coverage_percent: Mapped[float | None] = mapped_column(nullable=True)
    availability_percent: Mapped[float | None] = mapped_column(nullable=True)
    outage_count: Mapped[int] = mapped_column(Integer, default=0)
    mttr_seconds: Mapped[float | None] = mapped_column(nullable=True)
    mtbf_seconds: Mapped[float | None] = mapped_column(nullable=True)
    sla_target_percent: Mapped[float] = mapped_column(default=99.0)
    sla_breached: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    downtime_reasons: Mapped[dict] = mapped_column(JSON, default=dict)
    generated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True); generated_at: Mapped[datetime] = mapped_column(DateTime)
    outages: Mapped[list["AvailabilityOutage"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class AvailabilityOutage(Base):
    __tablename__ = "availability_outages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("availability_reports.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(30), index=True)
    entity_id: Mapped[int] = mapped_column(Integer, index=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    end_time: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[int] = mapped_column(Integer)
    ongoing: Mapped[bool] = mapped_column(Boolean, default=False)
    planned: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    report: Mapped[AvailabilityReport] = relationship(back_populates="outages")
