from fastapi import APIRouter, Depends, HTTPException
from execution.container import get_execution
from execution.base import ExecutionService


def _get_client():
    """Import lazily to avoid circular reference."""
    try:
        from server import get_client

        return get_client()
    except Exception:
        return None


router = APIRouter(prefix="/exec/sync", tags=["execution"])


@router.post("/deals")
def sync_deals(exec_service: ExecutionService = Depends(get_execution)):
    c = _get_client()
    # Require link and account
    if c is None or not getattr(c, "connected", False):
        raise HTTPException(status_code=400, detail="Not connected")
    if not getattr(c, "account_id", None):
        raise HTTPException(status_code=400, detail="No account selected")
    if not hasattr(exec_service, "sync_deals"):
        raise HTTPException(status_code=400, detail="Sync not supported")
    try:
        recs = c.get_deals()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch deals: {e}")
    inserted = exec_service.sync_deals(recs)  # type: ignore[attr-defined]
    return {"ok": True, "inserted": inserted}
