from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base


class Problem(Base):
    __tablename__ = "problems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(180))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(60), index=True)
    priority: Mapped[str] = mapped_column(String(2), default="p3", index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    root_cause: Mapped[str | None] = mapped_column(Text, nullable=True)
    workaround: Mapped[str | None] = mapped_column(Text, nullable=True)
    known_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    permanent_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    incidents: Mapped[list["ProblemIncident"]] = relationship(cascade="all, delete-orphan")
    history: Mapped[list["ProblemHistory"]] = relationship(cascade="all, delete-orphan")


class ProblemIncident(Base):
    __tablename__ = "problem_incidents"
    __table_args__ = (UniqueConstraint("problem_id", "incident_id", name="uq_problem_incident"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    linked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime)


class ProblemHistory(Base):
    __tablename__ = "problem_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(60))
    field_name: Mapped[str | None] = mapped_column(String(80), nullable=True)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
