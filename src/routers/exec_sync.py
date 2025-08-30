from fastapi import APIRouter, Depends, HTTPException
from execution.container import get_execution
from execution.base import ExecutionService

try:
    from server import get_client
except Exception:  # pragma: no cover
    def get_client():
        return None

router = APIRouter(prefix="/exec/sync", tags=["execution"])


@router.post("/deals")
def sync_deals(exec_service: ExecutionService = Depends(get_execution)):
    c = get_client()
    if c is None:
        raise HTTPException(status_code=400, detail="Not connected")
    if not hasattr(exec_service, "sync_deals"):
        raise HTTPException(status_code=400, detail="Sync not supported")
    try:
        recs = c.get_deals()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch deals: {e}")
    inserted = exec_service.sync_deals(recs)  # type: ignore[attr-defined]
    return {"ok": True, "inserted": inserted}
