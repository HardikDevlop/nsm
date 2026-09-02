from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, Float, String, JSON
from sqlalchemy.orm import Mapped, mapped_column
from backend.database.session import Base
class QoSSample(Base):
    __tablename__ = "qos_samples"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id", ondelete="CASCADE"), index=True)
    interface_id: Mapped[int | None] = mapped_column(ForeignKey("interfaces.id", ondelete="SET NULL"), nullable=True, index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    tos: Mapped[int | None] = mapped_column(Integer); dscp: Mapped[int | None] = mapped_column(Integer); phb: Mapped[str | None] = mapped_column(String(40)); traffic_class: Mapped[str | None] = mapped_column(String(80)); queue_utilization: Mapped[float | None] = mapped_column(Float); queue_drops: Mapped[int] = mapped_column(Integer, default=0); source: Mapped[str] = mapped_column(String(40), default="standard"); raw_fields: Mapped[dict] = mapped_column(JSON, default=dict)
