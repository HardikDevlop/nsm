from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from backend.database.session import Base
class VirtualObject(Base):
    __tablename__ = "virtualization_objects"
    __table_args__ = (UniqueConstraint("provider", "external_key", name="uq_virtual_object_key"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    provider: Mapped[str] = mapped_column(String(30), index=True); object_type: Mapped[str] = mapped_column(String(30), index=True)
    external_key: Mapped[str] = mapped_column(String(240)); name: Mapped[str] = mapped_column(String(240)); state: Mapped[str] = mapped_column(String(40), default="unknown")
    parent_external_key: Mapped[str | None] = mapped_column(String(240)); attributes: Mapped[dict] = mapped_column(JSON, default=dict); cmdb_ci_id: Mapped[int | None] = mapped_column(ForeignKey("cmdb_configuration_items.id", ondelete="SET NULL"), nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime)
