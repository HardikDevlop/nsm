from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, JSON
from sqlalchemy.orm import Mapped, mapped_column
from backend.database.session import Base
class BGPObservation(Base):
    __tablename__='bgp_observations'
    id:Mapped[int]=mapped_column(Integer,primary_key=True,index=True); device_id:Mapped[int]=mapped_column(ForeignKey('devices.id',ondelete='CASCADE'),index=True); neighbor:Mapped[str]=mapped_column(String(64),index=True); state:Mapped[str]=mapped_column(String(40)); remote_as:Mapped[int|None]=mapped_column(Integer); next_hop:Mapped[str|None]=mapped_column(String(64)); prefixes:Mapped[int]=mapped_column(Integer,default=0); as_path:Mapped[str|None]=mapped_column(String(1000)); observed_at:Mapped[datetime]=mapped_column(DateTime,index=True); raw_fields:Mapped[dict]=mapped_column(JSON,default=dict)
