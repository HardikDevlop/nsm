from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.models import QoSSample, User
router=APIRouter(prefix="/api/v1/qos",tags=["QoS"])
class QoSPayload(BaseModel):
 device_id:int=Field(gt=0); interface_id:int|None=Field(default=None,gt=0); observed_at:datetime; tos:int|None=None; dscp:int|None=Field(default=None,ge=0,le=63); phb:str|None=None; traffic_class:str|None=None; queue_utilization:float|None=Field(default=None,ge=0); queue_drops:int=Field(default=0,ge=0); source:str="standard"; raw_fields:dict={}
@router.post("/samples",status_code=201)
def add_sample(payload:QoSPayload,db:Session=Depends(get_db),_:User=Depends(require_permission("qos:ingest"))):
 item=QoSSample(**payload.model_dump()); db.add(item); db.commit(); db.refresh(item); return item
@router.get("/samples")
def samples(device_id:int|None=None,interface_id:int|None=None,hours:int=Query(24,ge=1,le=720),db:Session=Depends(get_db),_:User=Depends(require_permission("qos:read"))):
 q=db.query(QoSSample).filter(QoSSample.observed_at>=datetime.utcnow()-timedelta(hours=hours))
 if device_id is not None:q=q.filter_by(device_id=device_id)
 if interface_id is not None:q=q.filter_by(interface_id=interface_id)
 return q.order_by(QoSSample.observed_at.desc()).limit(1000).all()
