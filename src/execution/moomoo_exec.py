from __future__ import annotations

import time
from typing import Callable, Dict, List, Optional, Any, Iterable, Union

from .base import ExecutionService, ExecutionContext
from .types import OrderSpec, PlacedOrder, FillRecord, OrderStatus, OrderType, OrderSide, TimeInForce


def _utc_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _side_to_text(side: Any) -> str:
    s = str(side or "").upper()
    return OrderSide.buy.value if s.startswith("B") else OrderSide.sell.value


def _type_to_text(t: Any) -> str:
    s = str(t or "").upper()
    if s in ("MARKET",):
        return OrderType.market.value
    # Futu uses NORMAL for limit
    if s in ("STOP", "MARKET_IF_TOUCHED"):
        return OrderType.stop.value
    if s in ("STOP_LIMIT",):
        return OrderType.stop_limit.value
    if s in ("TRAILING_STOP",):
        return OrderType.trailing_stop.value
    if s in ("TRAILING_STOP_LIMIT",):
        return OrderType.trailing_stop_limit.value
    return OrderType.limit.value


def _status_to_text(st: Any) -> str:
    s = str(st or "").upper()
    # Normalize a variety of broker status strings
    if "REJECT" in s or "FAIL" in s or "ERROR" in s:
        return OrderStatus.rejected.value
    if "CANCEL" in s:
        return OrderStatus.canceled.value
    if "FILL" in s or "DEAL" in s or "COMPLETE" in s or s == "DONE":
        if "PART" in s or "PARTI" in s:
            return OrderStatus.partially_filled.value
        return OrderStatus.filled.value
    if "SUBMIT" in s or "NEW" in s or "ACCEPT" in s or "PENDING" in s or "INACTIVE" in s:
        return OrderStatus.pending.value
    return OrderStatus.open.value


class MoomooExecutionService(ExecutionService):
    """
    Execution driver that proxies directly to the Moomoo OpenD broker.

    - No local storage of orders/fills/positions.
    - All reads reflect current broker state.
    - STOP orders are not emulated locally; only MARKET/LIMIT supported.
    """

    def __init__(self, client_accessor: Callable[[], object]):
        self._client_accessor = client_accessor

    # ---- mapping helpers ----
    def _map_order(self, r: Dict[str, Any]) -> PlacedOrder:
        oid = str(r.get("order_id") or r.get("orderId") or r.get("orderID") or r.get("id") or "")
        sym = str(r.get("code") or r.get("stock_code") or r.get("symbol") or "")
        side = _side_to_text(r.get("trd_side") or r.get("side"))
        otype = _type_to_text(r.get("order_type") or r.get("type"))
        status = _status_to_text(r.get("order_status") or r.get("status"))
        tif = TimeInForce.day.value
        limit_px = r.get("price")
        req_qty = int(r.get("qty") or r.get("qty_total") or r.get("qty_submitted") or r.get("quantity") or 0)
        filled = int(r.get("dealt_qty") or r.get("filled_qty") or r.get("fill_qty") or 0)
        avg = r.get("dealt_avg_price") or r.get("avg_price") or r.get("fill_avg_price")
        # Use broker-provided timestamps only; avoid falling back to 'now' to prevent flicker
        created = str(r.get("create_time") or r.get("created_at") or r.get("time") or "")
        updated = str(r.get("updated_time") or r.get("last_time") or r.get("updated_at") or created or "")
        reject_reason = r.get("remark") or r.get("last_err_msg") or r.get("reject_reason")
        return PlacedOrder(
            order_id=oid or "",
            status=OrderStatus(status),
            symbol=sym,
            side=OrderSide(side),
            order_type=OrderType(otype),
            limit_price=float(limit_px) if (limit_px is not None and str(limit_px) != "") else None,
            requested_qty=req_qty,
            filled_qty=filled,
            avg_fill_price=float(avg) if (avg is not None and str(avg) != "") else None,
            tif=TimeInForce(tif),
            decision_id=None,
            created_at=created,
            updated_at=updated,
            reject_reason=str(reject_reason) if reject_reason else None,
        )

    def _map_fill(self, r: Dict[str, Any]) -> FillRecord:
        fid = str(r.get("deal_id") or r.get("id") or r.get("fill_id") or r.get("ts") or _utc_ts())
        oid = str(r.get("order_id") or r.get("orderId") or r.get("orderID") or "")
        sym = str(r.get("code") or r.get("stock_code") or r.get("symbol") or "")
        qty = int(r.get("deal_qty") or r.get("qty") or r.get("fill_qty") or 0)
        price = float(r.get("deal_price") or r.get("price") or r.get("fill_price") or 0)
        ts = str(r.get("create_time") or r.get("time") or r.get("ts") or _utc_ts())
        return FillRecord(fill_id=fid, order_id=oid, symbol=sym, qty=qty, price=price, ts=ts)

    # ---- interface ----
    def place_order(self, spec: OrderSpec, ctx: ExecutionContext) -> PlacedOrder:
        try:
            client = self._client_accessor()
        except Exception as e:
            raise RuntimeError(f"no broker client: {e}")

        # Determine qty from sizing
        last = float((ctx.last_prices or {}).get(spec.symbol) or 0.0)
        if spec.size_type == "shares":
            qty = int(spec.size_value)
        elif spec.size_type == "notional":
            qty = int(float(spec.size_value) // float(last or 1.0))
        else:  # risk_bps
            notional = float(ctx.equity) * (float(spec.size_value) / 10000.0)
            qty = int(notional // float(last or 1.0))
        if qty < 1:
            return PlacedOrder(
                order_id="",
                status=OrderStatus.rejected,
                symbol=spec.symbol,
                side=spec.side,
                order_type=spec.order_type,
                limit_price=spec.limit_price,
                requested_qty=0,
                filled_qty=0,
                avg_fill_price=None,
                tif=spec.tif,
                decision_id=spec.decision_id,
                created_at=_utc_ts(),
                updated_at=_utc_ts(),
                reject_reason="sizing_zero_qty",
            )

        if spec.order_type == OrderType.stop:
            # Map to broker STOP (market) using limit_price as trigger (aux_price)
            res = client.place_order(
                symbol=spec.symbol,
                qty=int(max(1, qty)),
                side=("BUY" if spec.side == OrderSide.buy else "SELL"),
                order_type="STOP",
                price=0,
                aux_price=float(spec.stop_trigger or spec.limit_price or 0.0),
            )
            recs = (res or {}).get("result") or []
            if isinstance(recs, list) and recs:
                return self._map_order(recs[0])
            ts = _utc_ts()
            return PlacedOrder(
                order_id="",
                status=OrderStatus.pending,
                symbol=spec.symbol,
                side=spec.side,
                order_type=spec.order_type,
                limit_price=spec.limit_price,
                requested_qty=qty,
                filled_qty=0,
                avg_fill_price=None,
                tif=spec.tif,
                decision_id=spec.decision_id,
                created_at=ts,
                updated_at=ts,
                reject_reason=None,
            )

        elif spec.order_type == OrderType.stop_limit:
            res = client.place_order(
                symbol=spec.symbol,
                qty=qty,
                side=("BUY" if spec.side == OrderSide.buy else "SELL"),
                order_type="STOP_LIMIT",
                price=(spec.limit_price),
                aux_price=(spec.stop_trigger if spec.stop_trigger is not None else spec.limit_price),
            )
            recs = (res or {}).get("result") or []
            if isinstance(recs, list) and recs:
                return self._map_order(recs[0])
        elif spec.order_type in (OrderType.trailing_stop, OrderType.trailing_stop_limit):
            res = client.place_order(
                symbol=spec.symbol,
                qty=qty,
                side=("BUY" if spec.side == OrderSide.buy else "SELL"),
                order_type=("TRAILING_STOP" if spec.order_type==OrderType.trailing_stop else "TRAILING_STOP_LIMIT"),
                price=(spec.limit_price if spec.order_type==OrderType.trailing_stop_limit else 0),
                trail_type=spec.trail_type,
                trail_value=spec.trail_value,
                trail_spread=spec.trail_spread,
            )
            recs = (res or {}).get("result") or []
            if isinstance(recs, list) and recs:
                return self._map_order(recs[0])
        # MARKET/LIMIT
        res = client.place_order(
            symbol=spec.symbol,
            qty=qty,
            side=("BUY" if spec.side == OrderSide.buy else "SELL"),
            order_type=("MARKET" if spec.order_type == OrderType.market else "LIMIT"),
            price=(spec.limit_price if spec.order_type == OrderType.limit else None),
        )
        recs = (res or {}).get("result") or []
        if isinstance(recs, list) and recs:
            return self._map_order(recs[0])
        # Fallback minimal echo when broker returned no record
        ts = _utc_ts()
        return PlacedOrder(
            order_id="",
            status=OrderStatus.pending,
            symbol=spec.symbol,
            side=spec.side,
            order_type=spec.order_type,
            limit_price=spec.limit_price,
            requested_qty=qty,
            filled_qty=0,
            avg_fill_price=None,
            tif=spec.tif,
            decision_id=spec.decision_id,
            created_at=ts,
            updated_at=ts,
            reject_reason=None,
        )

    def cancel_order(self, order_id: str) -> bool:
        try:
            client = self._client_accessor()
        except Exception:
            return False
        try:
            client.cancel_order(order_id)
            return True
        except Exception:
            return False

    def try_fill_resting(self, last_prices: Dict[str, float]) -> None:
        # No-op: broker maintains order state; we do not emulate stops locally
        return None

    def list_orders(self, *, symbol: Optional[str] = None,
                    status: Optional[Union[str, Iterable[str]]] = None,
                    limit: int = 200) -> List[PlacedOrder]:
        try:
            client = self._client_accessor()
            raw = client.get_orders() or []
        except Exception:
            raw = []
        # Map and filter
        out: List[PlacedOrder] = []
        want_status: Optional[set[str]] = None
        if status is not None:
            want_status = set(status) if isinstance(status, (list, tuple, set)) else {str(status)}
        for r in raw:
            try:
                po = self._map_order(r)
                if symbol and po.symbol != symbol:
                    continue
                if want_status and po.status.value not in want_status:
                    continue
                out.append(po)
            except Exception:
                continue
        # Sort by created (fallback to updated) desc; avoid jitter when timestamps are missing
        def _k(o: PlacedOrder):
            return (o.created_at or o.updated_at or "", o.order_id or "")
        out.sort(key=_k, reverse=True)
        return out[:limit]

    def list_fills(self, *, symbol: Optional[str] = None, limit: int = 500) -> List[FillRecord]:
        try:
            client = self._client_accessor()
            raw = client.get_deals() or []
        except Exception:
            raw = []
        out: List[FillRecord] = []
        for r in raw:
            try:
                f = self._map_fill(r)
                if symbol and f.symbol != symbol:
                    continue
                out.append(f)
            except Exception:
                continue
        out.sort(key=lambda x: x.ts or "", reverse=True)
        return out[:limit]

    # Optional positions view for UI (direct from broker)
    def list_positions(self) -> List[Dict[str, Any]]:
        try:
            client = self._client_accessor()
        except Exception:
            client = None
        if client is None:
            return []
        try:
            poss = client.get_positions() or []
        except Exception:
            poss = []
        def _to_float(val: Any) -> Optional[float]:
            if val is None:
                return None
            try:
                if isinstance(val, str):
                    txt = val.strip()
                    if not txt:
                        return None
                    txt = txt.replace(",", "")
                    return float(txt)
                return float(val)
            except Exception:
                return None

        def _first_float(record: Dict[str, Any], keys: Iterable[str]) -> Optional[float]:
            for k in keys:
                v = _to_float(record.get(k))
                if v is not None:
                    return v
            return None

        out: List[Dict[str, Any]] = []
        for p in poss:
            code = p.get("code") or p.get("stock_code") or p.get("symbol")
            if not code:
                continue
            qty_val = _first_float(p, ["qty", "qty_total", "qty_today", "position_qty", "position_qty_s", "can_sell_qty"])
            avg_val = _first_float(p, ["cost_price", "avg_cost_price", "cost", "cost_price_real_time"])
            if qty_val is None or qty_val == 0:
                continue
            qty = float(qty_val)
            last_px = _first_float(p, ["nominal_price", "last_price", "real_time_price", "market_price", "price", "latest_price"]) or None
            mv_val = _first_float(p, ["market_val", "market_value", "marketValue"])
            if mv_val is None:
                if last_px is not None:
                    mv_val = last_px * qty
                elif avg_val is not None:
                    mv_val = avg_val * qty
            upl_val = _first_float(p, [
                "pl_val",
                "pl_val_real_time",
                "unrealized_pl",
                "pl_value",
                "floating_pl",
                "pl_val_today",
            ])
            # Some APIs report P/L per share; fall back to price delta * qty when available
            if upl_val is None and last_px is not None and avg_val is not None:
                upl_val = (last_px - avg_val) * qty
            rpl_today = _first_float(p, [
                "today_realized_pl",
                "realized_pl_val_today",
                "pl_realized_today",
                "realized_pl",
            ]) or 0.0
            out.append({
                "symbol": str(code),
                "qty": int(qty),
                "avg_cost": float(avg_val or 0.0),
                "last": last_px,
                "mv": mv_val,
                "upl": upl_val,
                "rpl_today": rpl_today,
            })
        return out
