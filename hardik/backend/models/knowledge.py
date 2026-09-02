from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database.session import Base


class KnowledgeArticle(Base):
    __tablename__ = "knowledge_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    number: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(220), index=True)
    article_type: Mapped[str] = mapped_column(String(30), index=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime)

    versions: Mapped[list["KnowledgeArticleVersion"]] = relationship(cascade="all, delete-orphan")
    incident_links: Mapped[list["KnowledgeIncidentLink"]] = relationship(cascade="all, delete-orphan")
    problem_links: Mapped[list["KnowledgeProblemLink"]] = relationship(cascade="all, delete-orphan")
    device_links: Mapped[list["KnowledgeDeviceLink"]] = relationship(cascade="all, delete-orphan")
    service_links: Mapped[list["KnowledgeServiceLink"]] = relationship(cascade="all, delete-orphan")


class KnowledgeArticleVersion(Base):
    __tablename__ = "knowledge_article_versions"
    __table_args__ = (UniqueConstraint("article_id", "version", name="uq_knowledge_article_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    changed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class KnowledgeIncidentLink(Base):
    __tablename__ = "knowledge_incident_links"
    __table_args__ = (UniqueConstraint("article_id", "incident_id", name="uq_knowledge_incident"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incidents.id", ondelete="CASCADE"), index=True)
    linked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime)


class KnowledgeProblemLink(Base):
    __tablename__ = "knowledge_problem_links"
    __table_args__ = (UniqueConstraint("article_id", "problem_id", name="uq_knowledge_problem"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True)
    problem_id: Mapped[int] = mapped_column(ForeignKey("problems.id", ondelete="CASCADE"), index=True)
    linked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime)


class KnowledgeDeviceLink(Base):
    __tablename__ = "knowledge_device_links"
    __table_args__ = (UniqueConstraint("article_id", "device_id", name="uq_knowledge_device"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    linked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime)


class KnowledgeServiceLink(Base):
    __tablename__ = "knowledge_service_links"
    __table_args__ = (UniqueConstraint("article_id", "service_id", name="uq_knowledge_service"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("knowledge_articles.id", ondelete="CASCADE"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("apm_services.id", ondelete="CASCADE"), index=True)
    linked_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    linked_at: Mapped[datetime] = mapped_column(DateTime)
