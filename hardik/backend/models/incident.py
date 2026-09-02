from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(60), index=True)
    priority: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    correlation_key: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    rca_incident_id: Mapped[int | None] = mapped_column(ForeignKey("rca_incidents.id", ondelete="SET NULL"), nullable=True, index=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("apm_services.id", ondelete="SET NULL"), nullable=True, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    acknowledged_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    alerts: Mapped[list["IncidentAlert"]] = relationship(cascade="all, delete-orphan")
    comments: Mapped[list["IncidentComment"]] = relationship(cascade="all, delete-orphan")
    attachments: Mapped[list["IncidentAttachment"]] = relationship(cascade="all, delete-orphan")


class IncidentAlert(Base):
    __tablename__ = "incident_alerts"
    __table_args__ = (UniqueConstraint("incident_id", "alert_id", name="uq_incident_alert"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), index=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime)


class IncidentComment(Base):
    __tablename__ = "incident_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class IncidentAttachment(Base):
    __tablename__ = "incident_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    storage_key: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class IncidentHistory(Base):
    __tablename__ = "incident_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class IncidentSLAConfig(Base):
    __tablename__ = "incident_sla_configs"
    __table_args__ = (UniqueConstraint("priority", "service_id", name="uq_incident_sla_policy"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    priority: Mapped[str] = mapped_column(String(30), index=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("apm_services.id", ondelete="CASCADE"), nullable=True, index=True)
    response_target_minutes: Mapped[int] = mapped_column(Integer)
    resolution_target_minutes: Mapped[int] = mapped_column(Integer)
    pause_states: Mapped[list] = mapped_column(JSON, default=lambda: ["pending"])
    escalation_after_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalation_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class IncidentSLATimer(Base):
    __tablename__ = "incident_sla_timers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), unique=True, index=True)
    config_id: Mapped[int] = mapped_column(ForeignKey("incident_sla_configs.id", ondelete="RESTRICT"))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    response_deadline: Mapped[datetime] = mapped_column(DateTime)
    resolution_deadline: Mapped[datetime] = mapped_column(DateTime)
    first_responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paused_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    paused_seconds: Mapped[int] = mapped_column(Integer, default=0)
    response_breached: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution_breached: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class IncidentSLAHistory(Base):
    __tablename__ = "incident_sla_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    timer_id: Mapped[int | None] = mapped_column(ForeignKey("incident_sla_timers.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(50))
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
