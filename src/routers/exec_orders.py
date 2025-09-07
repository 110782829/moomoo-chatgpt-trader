from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from execution.container import get_execution
from execution.base import ExecutionService, ExecutionContext
from execution.types import PlacedOrder, FillRecord, OrderSpec, OrderSide, OrderType, TimeInForce

router = APIRouter(prefix="/exec", tags=["execution"])

# Simple in-process caches to avoid transient empty blinks in UI.
# These caches are per-worker-process and best-effort only.
_LAST_ORDERS: List[Dict] = []
_LAST_ORDERS_TS: float = 0.0
_LAST_POSITIONS: List[Dict] = []
_LAST_POSITIONS_TS: float = 0.0
_CACHE_TTL_SEC: float = 5.0


@router.get("/orders", response_model=List[PlacedOrder])
def list_orders(symbol: Optional[str] = None,
                status: Optional[List[str]] = Query(None),
                limit: int = 200,
                fresh: bool = Query(False),
                exec_service: ExecutionService = Depends(get_execution)):
    import time
    global _LAST_ORDERS, _LAST_ORDERS_TS
    try:
        full = exec_service.list_orders(symbol=None, status=None, limit=limit)
        # Only update cache if non-empty or cache is stale or caller requested fresh
        if fresh or full or (time.time() - _LAST_ORDERS_TS) > _CACHE_TTL_SEC:
            _LAST_ORDERS = [o.model_dump() if hasattr(o, 'model_dump') else o for o in full]  # type: ignore
            _LAST_ORDERS_TS = time.time()
        base = full if (fresh or full) else _LAST_ORDERS
    except Exception:
        # On error, use cache if recent
        base = _LAST_ORDERS if (time.time() - _LAST_ORDERS_TS) <= 30.0 else []

    # Apply filters after choosing base list
    out = base
    if symbol:
        out = [o for o in out if str(o.get('symbol') or '') == symbol]
    if status:
        want = set(status)
        out = [o for o in out if str(o.get('status') or '') in want]
    return out[:limit]


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
def list_positions(fresh: bool = Query(False), exec_service: ExecutionService = Depends(get_execution)):
    # Broker-backed: return last non-empty snapshot when broker is momentarily empty
    import time
    global _LAST_POSITIONS, _LAST_POSITIONS_TS
    try:
        cur = exec_service.list_positions()
        if fresh or cur or (time.time() - _LAST_POSITIONS_TS) > _CACHE_TTL_SEC:
            _LAST_POSITIONS = cur
            _LAST_POSITIONS_TS = time.time()
        return cur if (fresh or cur) else _LAST_POSITIONS
    except Exception:
        return _LAST_POSITIONS if (time.time() - _LAST_POSITIONS_TS) <= 30.0 else []


# ---------- PnL (SIM) ----------

class PnLToday(BaseModel):
    date: str
    realized_pnl: float


@router.get("/pnl/today", response_model=PnLToday)
def pnl_today(exec_service: ExecutionService = Depends(get_execution)):
    # Not tracked via broker; return zero gracefully
    return {"date": "1970-01-01", "realized_pnl": 0.0}


# ---------- Flatten (Broker) ----------

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
    ctx = ExecutionContext(account_id="BROKER", last_prices=last_prices, equity=0.0, simulate=True)

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
