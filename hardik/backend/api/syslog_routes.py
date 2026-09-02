from datetime import datetime
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.models import SyslogRecord, SyslogCorrelationRule, User
router=APIRouter(prefix='/api/v1/syslog',tags=['Syslog'])
@router.get('/records')
def records(device_id:int|None=None,severity:int|None=Query(None,ge=0,le=7),pattern:str|None=None,after:datetime|None=None,limit:int=Query(100,ge=1,le=1000),db:Session=Depends(get_db),_:User=Depends(require_permission('syslog:read'))):
 q=db.query(SyslogRecord)
 if device_id is not None:q=q.filter_by(device_id=device_id)
 if severity is not None:q=q.filter_by(severity=severity)
 if pattern:q=q.filter(SyslogRecord.message.ilike(f'%{pattern}%'))
 if after:q=q.filter(SyslogRecord.event_timestamp>=after)
 return q.order_by(SyslogRecord.event_timestamp.desc()).limit(limit).all()
class RulePayload(BaseModel):
 name:str=Field(min_length=1,max_length=160); pattern:str=Field(min_length=1,max_length=500); min_severity:int|None=Field(default=None,ge=0,le=7); alert_severity:str='warning'; cooldown_seconds:int=Field(default=300,ge=1)
@router.get('/rules')
def rules(db:Session=Depends(get_db),_:User=Depends(require_permission('syslog:read'))): return db.query(SyslogCorrelationRule).order_by(SyslogCorrelationRule.name).all()
@router.post('/rules',status_code=201)
def add_rule(payload:RulePayload,db:Session=Depends(get_db),user:User=Depends(require_permission('syslog:manage'))):
 item=SyslogCorrelationRule(**payload.model_dump(),created_by=user.id,created_at=datetime.utcnow());db.add(item);db.commit();db.refresh(item);return item
