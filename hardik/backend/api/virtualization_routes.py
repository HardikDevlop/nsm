from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.models import VirtualObject
from backend.virtualization import get_adapter
router=APIRouter(prefix="/api/v1/virtualization",tags=["Virtualization"])
class InventoryPayload(BaseModel): provider:str=Field(pattern="^(vmware|hyperv|kvm)$"); objects:list[dict]=Field(min_length=1,max_length=10000)
@router.get("/objects")
def objects(provider:str|None=None, db:Session=Depends(get_db), _:object=Depends(require_permission("virtualization:read"))):
 q=db.query(VirtualObject); return q.filter_by(provider=provider).all() if provider else q.order_by(VirtualObject.provider,VirtualObject.object_type).all()
@router.post("/inventory")
def inventory(payload:InventoryPayload,db:Session=Depends(get_db),_:object=Depends(require_permission("virtualization:manage"))):
 now=datetime.utcnow(); count=0
 for value in payload.objects:
  key=str(value.get("external_key") or "").strip(); kind=str(value.get("object_type") or "").strip()
  if not key or kind not in {"host","vm","cluster","datastore","virtual_switch"}: raise HTTPException(422,"external_key and supported object_type are required")
  item=db.query(VirtualObject).filter_by(provider=payload.provider,external_key=key).first()
  if item is None: item=VirtualObject(provider=payload.provider,external_key=key,object_type=kind,name=str(value.get("name") or key),parent_external_key=value.get("parent_external_key"),attributes=value.get("attributes") or {},state=str(value.get("state") or "unknown"),cmdb_ci_id=value.get("cmdb_ci_id"),observed_at=now); db.add(item)
  else: item.name=str(value.get("name") or item.name); item.state=str(value.get("state") or item.state); item.attributes=value.get("attributes") or item.attributes; item.observed_at=now
  count+=1
 db.commit(); return {"accepted":count,"provider":payload.provider}
@router.get("/topology")
def topology(db:Session=Depends(get_db),_:object=Depends(require_permission("virtualization:read"))):
 rows=db.query(VirtualObject).all(); by_key={(x.provider,x.external_key):x.id for x in rows}; links=[]
 for x in rows:
  if x.parent_external_key and (x.provider,x.parent_external_key) in by_key: links.append({"source_id":by_key[(x.provider,x.parent_external_key)],"target_id":x.id,"relationship":"contains"})
 return {"nodes":[{"id":x.id,"provider":x.provider,"object_type":x.object_type,"name":x.name,"state":x.state,"cmdb_ci_id":x.cmdb_ci_id,"attributes":x.attributes} for x in rows],"links":links}
