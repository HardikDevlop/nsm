from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.session import Base


class CIType(Base):
    __tablename__ = "cmdb_ci_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, default="custom")
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class ConfigurationItem(Base):
    __tablename__ = "cmdb_configuration_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ci_type_id: Mapped[int] = mapped_column(ForeignKey("cmdb_ci_types.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    external_key: Mapped[str | None] = mapped_column(String(180))
    lifecycle_state: Mapped[str] = mapped_column(String(40), nullable=False, default="planned")
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"))
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id", ondelete="SET NULL"))
    interface_id: Mapped[int | None] = mapped_column(ForeignKey("interfaces.id", ondelete="SET NULL"))
    site_id: Mapped[int | None] = mapped_column(ForeignKey("sites.id", ondelete="SET NULL"))
    application_id: Mapped[int | None] = mapped_column(ForeignKey("apm_applications.id", ondelete="SET NULL"))
    environment: Mapped[str | None] = mapped_column(String(80))
    attributes: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default=text("'{}'"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    first_discovered: Mapped[datetime | None] = mapped_column(DateTime)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime)
    last_synchronized: Mapped[datetime | None] = mapped_column(DateTime)
    sync_source: Mapped[str | None] = mapped_column(String(40), default="manual")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class CIRelationship(Base):
    __tablename__ = "cmdb_ci_relationships"
    __table_args__ = (UniqueConstraint("source_ci_id", "target_ci_id", "relationship_type", name="uq_cmdb_ci_relationship"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_ci_id: Mapped[int] = mapped_column(ForeignKey("cmdb_configuration_items.id", ondelete="CASCADE"), nullable=False)
    target_ci_id: Mapped[int] = mapped_column(ForeignKey("cmdb_configuration_items.id", ondelete="CASCADE"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    managed_by: Mapped[str] = mapped_column(String(40), nullable=False, default="manual")
    source_key: Mapped[str | None] = mapped_column(String(240))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class CIHistory(Base):
    __tablename__ = "cmdb_ci_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ci_id: Mapped[int] = mapped_column(ForeignKey("cmdb_configuration_items.id", ondelete="CASCADE"), nullable=False)
    changed_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(120))
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
