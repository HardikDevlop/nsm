from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.database.session import get_db
from backend.dependencies import require_permission
from backend.services.effective_memory_aggregation import build_effective_memory_aggregate

router = APIRouter(prefix="/api/v1/dashboard", tags=["Dashboard"])


@router.get("/memory-aggregate")
def memory_aggregate(db: Session = Depends(get_db), _=Depends(require_permission("dashboard:read"))):
    return build_effective_memory_aggregate(db)
