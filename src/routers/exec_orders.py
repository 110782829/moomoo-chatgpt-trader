from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from execution.container import get_execution
from execution.base import ExecutionService, ExecutionContext
from execution.types import PlacedOrder, FillRecord, OrderSpec, OrderSide, OrderType, TimeInForce

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


# ---------- Positions (SIM) ----------

class PositionView(BaseModel):
    symbol: str
    qty: int
    avg_cost: float
    last: Optional[float] = None
    mv: Optional[float] = None
    upl: Optional[float] = None
    rpl_today: float


@router.get("/positions", response_model=List[PositionView])
def list_positions(exec_service: ExecutionService = Depends(get_execution)):
    # SimBroker returns List[Dict]; response_model coerces/validates
    return exec_service.list_positions()


# ---------- PnL (SIM) ----------

class PnLToday(BaseModel):
    date: str
    realized_pnl: float


@router.get("/pnl/today", response_model=PnLToday)
def pnl_today(exec_service: ExecutionService = Depends(get_execution)):
    # Available on SimBroker; for other drivers return zero gracefully
    if hasattr(exec_service, "pnl_today"):
        return getattr(exec_service, "pnl_today")()
    return {"date": "1970-01-01", "realized_pnl": 0.0}


# ---------- Flatten (SIM) ----------

class FlattenRequest(BaseModel):
    symbols: Optional[List[str]] = None  # if omitted -> flatten ALL non-zero positions


@router.post("/flatten")
def flatten(body: FlattenRequest = FlattenRequest(), exec_service: ExecutionService = Depends(get_execution)):
    # Get current positions; choose targets
    positions: List[Dict] = exec_service.list_positions()
    targets = [p for p in positions if p.get("qty")]
    if body.symbols:
        only = set([s.strip() for s in body.symbols if s and s.strip()])
        targets = [p for p in targets if p["symbol"] in only]

    if not targets:
        return {"ok": True, "placed": 0, "orders": []}

    # Build last_prices map from most recent fills (fallback to avg_cost if no fills)
    last_prices: Dict[str, float] = {}
    for p in targets:
        sym = p["symbol"]
        fills = exec_service.list_fills(symbol=sym, limit=1)
        if fills:
            last_prices[sym] = float(fills[0].price)
        else:
            last_prices[sym] = float(p.get("avg_cost") or 0.0)

    # Equity isn't required for 'shares' sizing; supply any number
    ctx = ExecutionContext(account_id="SIM-LOCAL", last_prices=last_prices, equity=0.0, simulate=True)

    placed = []
    for p in targets:
        sym = p["symbol"]
        qty = int(p["qty"])
        if qty == 0:
            continue
        side = OrderSide.sell if qty > 0 else OrderSide.buy  # offset position
        spec = OrderSpec(
            symbol=sym,
            side=side,
            order_type=OrderType.market,
            limit_price=None,
            size_type="shares",
            size_value=abs(qty),
            tif=TimeInForce.day,
            decision_id=None,
        )
        order = exec_service.place_order(spec, ctx)
        placed.append({"symbol": sym, "order_id": order.order_id, "status": str(order.status.value)})

    # Opportunistic fills for any resting orders (if no last price available they may remain open)
    exec_service.try_fill_resting(last_prices)
    return {"ok": True, "placed": len(placed), "orders": placed}
