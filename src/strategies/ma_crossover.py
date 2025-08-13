"""
Moving Average Crossover strategy implementation.

This strategy calculates a fast and a slow simple moving average (SMA) over the
incoming price data. When the fast SMA crosses above the slow SMA, it
generates a buy signal; when the fast SMA crosses below the slow SMA, it
signals a sell. Orders are returned as simple dictionaries that can later be
translated into broker-specific order requests.
"""

# Moving-Average Crossover strategy step.
# Buys on fast>slow cross, sells on fast<slow cross. Skips if bars unavailable.

from typing import Dict, Any, List, Optional
import math

from core.moomoo_client import MoomooClient, TrdEnv
from core.storage import insert_run

def _normalize(symbol: str) -> str:
    return symbol if "." in symbol else f"US.{symbol.upper()}"

def _get_bars(client: MoomooClient, symbol: str, ktype: str, n: int) -> List[Dict[str, Any]]:
    if not client.quote_ctx:
        raise RuntimeError("Quote context not available")
    code = _normalize(symbol)
    tried = [
        {"code": code, "ktype": ktype, "max_count": n},
        {"code": code, "ktype": ktype, "num": n},
        {"codes": [code], "ktype": ktype, "max_count": n},
    ]
    last_err = None
    for kwargs in tried:
        try:
            ret, df = client.quote_ctx.get_cur_kline(**kwargs)  # type: ignore[arg-type]
            if ret != 0:
                raise RuntimeError(f"get_cur_kline failed: {df}")
            from core.moomoo_client import _df_to_records
            recs = _df_to_records(df)
            return recs[-n:] if isinstance(recs, list) else []
        except TypeError as e:
            last_err = e
            continue
    raise RuntimeError(f"get_cur_kline incompatible with this futu build: {last_err}")

def _sma(vals: List[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0

def _current_position(client: MoomooClient, symbol: str) -> tuple[float, float]:
    """Return (qty, avg_cost) for symbol; 0,0 if none."""
    try:
        code = _normalize(symbol)
        poss = client.get_positions()
        for p in poss:
            if str(p.get("code") or p.get("stock_code")) == code:
                qty = float(p.get("qty") or p.get("stock_qty") or p.get("position") or 0)
                avg = float(p.get("cost_price") or p.get("cost_price_ex") or p.get("avg_cost") or 0)
                return qty, avg
    except Exception:
        pass
    return 0.0, 0.0

def step(strategy_id: int, client: MoomooClient, symbol: str, params: Dict[str, Any]) -> None:
    # core params
    fast = int(params.get("fast", 20))
    slow = int(params.get("slow", 50))
    ktype = str(params.get("ktype", "K_1M"))

    # sizing
    qty_param = float(params.get("qty", 1))
    size_mode = str(params.get("size_mode", "shares")).lower()  # 'shares' | 'usd'
    dollar_size = float(params.get("dollar_size", 0))

    # risk
    sl_pct = float(params.get("stop_loss_pct", 0))         # e.g., 0.02 = 2%
    tp_pct = float(params.get("take_profit_pct", 0))       # e.g., 0.03 = 3%
    allow_real = bool(params.get("allow_real", False))

    if slow <= fast:
        insert_run(strategy_id, "ERROR", f"Invalid params: slow({slow}) must be > fast({fast})")
        return

    try:
        if not client.account_id:
            insert_run(strategy_id, "SKIP", "No account selected")
            return
        if client.env != TrdEnv.SIMULATE and not allow_real:
            insert_run(strategy_id, "SKIP", "Real trading disabled (allow_real=False)")
            return

        # fetch bars; last close acts as 'last price' proxy
        bars = _get_bars(client, symbol, ktype, slow + 1)
        closes = [float(b.get("close", 0) or 0) for b in bars if float(b.get("close", 0) or 0) > 0]
        if len(closes) < slow:
            insert_run(strategy_id, "SKIP", f"Not enough bars: have {len(closes)}, need {slow}")
            return

        last_price = closes[-1]
        fast_prev = _sma(closes[-(fast + 1):-1])
        slow_prev = _sma(closes[-(slow + 1):-1])
        fast_now = _sma(closes[-fast:])
        slow_now = _sma(closes[-slow:])

        pos_qty, avg_cost = _current_position(client, symbol)

        # exits first (if in position)
        if pos_qty > 0:
            exited = False
            # TP/SL checks
            if tp_pct > 0 and last_price >= avg_cost * (1.0 + tp_pct):
                client.place_order(symbol=symbol, qty=pos_qty, side="SELL", order_type="MARKET")
                insert_run(strategy_id, "TRADE", f"TP SELL {pos_qty} @~{last_price} (avg {avg_cost}, tp {tp_pct})")
                exited = True
            elif sl_pct > 0 and last_price <= avg_cost * (1.0 - sl_pct):
                client.place_order(symbol=symbol, qty=pos_qty, side="SELL", order_type="MARKET")
                insert_run(strategy_id, "TRADE", f"SL SELL {pos_qty} @~{last_price} (avg {avg_cost}, sl {sl_pct})")
                exited = True

            # optional: cross-down exit
            if not exited and fast_prev >= slow_prev and fast_now < slow_now:
                client.place_order(symbol=symbol, qty=pos_qty, side="SELL", order_type="MARKET")
                insert_run(strategy_id, "TRADE", f"CROSS-DOWN SELL {pos_qty} @~{last_price}")
                exited = True

            if exited:
                return
            else:
                insert_run(strategy_id, "OK",
                           f"Holding {pos_qty}; fast={fast_now:.4f}, slow={slow_now:.4f}, last={last_price:.4f}")
                return

        # no position: look for entry (cross-up)
        if fast_prev <= slow_prev and fast_now > slow_now:
            # size calc
            trade_qty = qty_param
            if size_mode == "usd" and dollar_size > 0 and last_price > 0:
                trade_qty = math.floor(dollar_size / last_price)
                if trade_qty < 1:
                    insert_run(strategy_id, "SKIP", f"Size too small at last={last_price:.4f}")
                    return
            client.place_order(symbol=symbol, qty=trade_qty, side="BUY", order_type="MARKET")
            insert_run(strategy_id, "TRADE",
                       f"BUY {trade_qty} @~{last_price} (cross-up; fast {fast_now:.4f} > slow {slow_now:.4f})")
            return

        insert_run(strategy_id, "OK",
                   f"No cross. fast={fast_now:.4f}, slow={slow_now:.4f}, last={last_price:.4f}")

    except Exception as e:
        insert_run(strategy_id, "SKIP", f"Bars/exec unavailable: {e}")