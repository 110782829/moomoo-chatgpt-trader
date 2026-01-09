from __future__ import annotations
from typing import List, Dict, Tuple
from datetime import datetime

from core.market_data import get_bars_safely


def fetch_deals(client, simulate_if_absent: bool = True) -> Tuple[List[Dict[str, any]], str]:
    """Return recent fills from broker with optional synthetic fallback.

    Returns a tuple of (records, source) where source is "broker_deals" or
    "orders_fallback".
    """
    if client is None or not getattr(client, "connected", False):
        raise RuntimeError("Not connected")

    # First try real deals
    try:
        recs = client.get_deals()
        out: List[Dict[str, any]] = []
        for r in recs:
            oid = r.get("order_id") or r.get("orderId") or ""
            code = r.get("code") or r.get("stock_code") or ""
            side = str(r.get("trd_side") or r.get("side") or "").upper()
            qty = float(r.get("deal_qty") or r.get("qty") or r.get("fill_qty") or 0)
            price = float(r.get("deal_price") or r.get("price") or r.get("fill_price") or 0)
            ts = str(r.get("create_time") or r.get("time") or r.get("ts") or "")
            if not code or qty <= 0 or price <= 0 or not ts:
                continue
            out.append({
                "order_id": str(oid),
                "symbol": str(code),
                "side": "BUY" if "BUY" in side else "SELL",
                "qty": float(qty),
                "price": float(price),
                "ts": ts,
            })
        return out, "broker_deals"
    except RuntimeError as e:
        msg = str(e)
    except Exception as e:
        raise RuntimeError(f"deal fetch failed: {e}")

    # Fallback via orders
    try_fallback = simulate_if_absent or "Simulated trade does not support deal list" in msg or "deal_list_query" in msg
    if not try_fallback:
        raise RuntimeError(msg)

    try:
        orders = client.get_orders()
    except Exception as e2:
        raise RuntimeError(f"Failed to fetch orders for fallback: {e2}")

    out: List[Dict[str, any]] = []
    for o in orders:
        status = str(o.get("order_status") or "").upper()
        code = str(o.get("code") or o.get("stock_code") or "")
        side = str(o.get("trd_side") or "").upper()
        oid = str(o.get("order_id") or o.get("orderId") or "")
        qty = float(o.get("qty") or 0)
        if not code or not oid or qty <= 0:
            continue
        price = float(o.get("dealt_avg_price") or 0)
        is_filled = status in {"FILLED", "FILLED_ALL", "DEALT", "SUCCESS"}
        may_synthesize = simulate_if_absent and status in {"SUBMITTED", "SUBMITTING"} and price <= 0
        if price <= 0 and (is_filled or may_synthesize):
            try:
                bars, _ = get_bars_safely(client, code, "K_1M", 1)
                if bars:
                    price = float(bars[-1].get("close", 0) or 0)
            except Exception:
                price = 0.0
        if (is_filled or may_synthesize) and price > 0:
            ts = str(o.get("updated_time") or o.get("create_time") or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
            out.append({
                "order_id": oid,
                "symbol": code,
                "side": "BUY" if "BUY" in side else "SELL",
                "qty": float(qty),
                "price": float(price),
                "ts": ts,
            })
    return out, "orders_fallback"
