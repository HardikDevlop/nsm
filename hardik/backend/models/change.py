from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base


class ChangeRequest(Base):
    __tablename__ = "change_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(50), index=True)
    risk: Mapped[str] = mapped_column(String(30), index=True)
    impact: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approval_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    maintenance_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    maintenance_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    implementation_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    rollback_plan: Mapped[str | None] = mapped_column(Text, nullable=True)
    closure_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cis: Mapped[list["ChangeCI"]] = relationship(cascade="all, delete-orphan")
    incidents: Mapped[list["ChangeIncident"]] = relationship(cascade="all, delete-orphan")
    history: Mapped[list["ChangeHistory"]] = relationship(cascade="all, delete-orphan")


class ChangeCI(Base):
    __tablename__ = "change_cis"
    __table_args__ = (UniqueConstraint("change_id", "ci_id", name="uq_change_ci"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    change_id: Mapped[int] = mapped_column(ForeignKey("change_requests.id", ondelete="CASCADE"), index=True)
    ci_id: Mapped[int] = mapped_column(ForeignKey("cmdb_configuration_items.id", ondelete="CASCADE"), index=True)
    linked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime)


class ChangeIncident(Base):
    __tablename__ = "change_incidents"
    __table_args__ = (UniqueConstraint("change_id", "incident_id", name="uq_change_incident"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    change_id: Mapped[int] = mapped_column(ForeignKey("change_requests.id", ondelete="CASCADE"), index=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    linked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime)


class ChangeHistory(Base):
    __tablename__ = "change_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    change_id: Mapped[int] = mapped_column(ForeignKey("change_requests.id", ondelete="CASCADE"), index=True)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    field_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
