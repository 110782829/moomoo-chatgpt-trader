from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from execution.container import get_execution
from execution.base import ExecutionService
from execution.types import PlacedOrder, FillRecord

router = APIRouter(prefix="/exec", tags=["execution"])

@router.get("/orders", response_model=List[PlacedOrder])
def list_orders(symbol: Optional[str] = None, status: Optional[str] = None, limit: int = 200,
                exec_service: ExecutionService = Depends(get_execution)):
    return exec_service.list_orders(symbol=symbol, status=status, limit=limit)

@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: str, exec_service: ExecutionService = Depends(get_execution)):
    ok = exec_service.cancel_order(order_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Cancel not allowed or order not found")
    return {"ok": True, "order_id": order_id}

@router.get("/fills", response_model=List[FillRecord])
def list_fills(symbol: Optional[str] = None, limit: int = 500,
               exec_service: ExecutionService = Depends(get_execution)):
    return exec_service.list_fills(symbol=symbol, limit=limit)
