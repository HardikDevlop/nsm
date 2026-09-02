from datetime import datetime,timedelta
from fastapi import APIRouter,Depends,Query
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.models import BGPObservation,User
router=APIRouter(prefix='/api/v1/bgp',tags=['BGP'])
class BGPObservationPayload(BaseModel):
 device_id:int=Field(gt=0); neighbor:str=Field(min_length=1,max_length=64); state:str=Field(min_length=1,max_length=40); remote_as:int|None=Field(default=None,gt=0); next_hop:str|None=None; prefixes:int=Field(default=0,ge=0); as_path:str|None=Field(default=None,max_length=1000); observed_at:datetime; raw_fields:dict={}
@router.post('/observations',status_code=201)
def add(payload:BGPObservationPayload,db:Session=Depends(get_db),_:User=Depends(require_permission('bgp:ingest'))):
 x=BGPObservation(**payload.model_dump());db.add(x);db.commit();db.refresh(x);return x
@router.get('/neighbors')
def neighbors(device_id:int|None=None,hours:int=Query(24,ge=1,le=720),db:Session=Depends(get_db),_:User=Depends(require_permission('bgp:read'))):
 q=db.query(BGPObservation).filter(BGPObservation.observed_at>=datetime.utcnow()-timedelta(hours=hours));
 if device_id is not None:q=q.filter_by(device_id=device_id)
 return q.order_by(BGPObservation.observed_at.desc()).limit(2000).all()
