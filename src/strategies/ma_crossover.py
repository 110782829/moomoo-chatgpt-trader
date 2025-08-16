"""
Moving Average Crossover strategy implementation.

This strategy calculates a fast and a slow simple moving average (SMA) over the
incoming price data. When the fast SMA crosses above the slow SMA, it
generates a buy signal; when the fast SMA crosses below the slow SMA, it
signals a sell. Orders are returned as simple dictionaries that can later be
translated into broker-specific order requests.
"""

from typing import Dict, Any, List, Optional
import math

from core.moomoo_client import MoomooClient, TrdEnv
from core.storage import insert_run, pnl_today

# --- Risk integration (imports with safe fallbacks) ---
try:
    from risk.limits import (
        enforce_order_limits,
        load_cfg,
        market_open_now,
        in_flatten_window,
        check_trade_limits,
        market_ok_to_trade,
    )
except Exception:
    # If risk module isn't available, define no-op fallbacks so strategy still runs.
    enforce_order_limits = None  # placing orders will skip centralized checks

    def load_cfg():
        # minimal shape expected elsewhere
        return {
            "enabled": False,
            "max_usd_per_trade": 1e12,
            "max_open_positions": 999,
            "max_daily_loss_usd": 1e12,
            "symbol_whitelist": [],
            "trading_hours_pt": {"start": "06:30", "end": "13:00"},
            "flatten_before_close_min": 0,
        }

    def market_open_now(*args, **kwargs) -> bool:
        return True

    def in_flatten_window(*args, **kwargs) -> bool:
        return False

    def check_trade_limits(*args, **kwargs) -> None:
        return None

    def market_ok_to_trade(*args, **kwargs) -> bool:
        return True


# data provider (futu first, yfinance fallback)
from core.market_data import get_bars_safely

def _normalize(symbol: str) -> str:
    return symbol if "." in symbol else f"US.{symbol.upper()}"

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

def _open_positions_count(client: MoomooClient) -> int:
    try:
        poss = client.get_positions()
        return len(poss) if isinstance(poss, list) else 0
    except Exception:
        return 0

def step(strategy_id: int, client: MoomooClient, symbol: str, params: Dict[str, Any]) -> None:
    # core params
    fast = int(params.get("fast", 20))
    slow = int(params.get("slow", 50))
    ktype = str(params.get("ktype", "K_1M"))

    # sizing
    qty_param = float(params.get("qty", 1))
    size_mode = str(params.get("size_mode", "shares")).lower()
    dollar_size = float(params.get("dollar_size", 0))

    # risk
    sl_pct = float(params.get("stop_loss_pct", 0))
    tp_pct = float(params.get("take_profit_pct", 0))
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

        # daily loss guard (based on realized PnL from fills)
        cfg = load_cfg()
        try:
            loss_cap = float(cfg.get("max_daily_loss_usd", 0) or 0)
        except Exception:
            loss_cap = 0.0
        if loss_cap > 0:
            today = pnl_today().get("realized_pnl", 0.0)
            if float(today) <= -abs(loss_cap):
                # optional: flatten if holding
                pos_qty, _ = _current_position(client, symbol)
                if pos_qty > 0:
                    client.place_order(symbol=symbol, qty=pos_qty, side="SELL", order_type="MARKET")
                    insert_run(strategy_id, "TRADE", f"[PnL] Loss cap hit; FLATTEN {pos_qty}")
                insert_run(strategy_id, "SKIP", f"[PnL] Daily loss limit reached (today={today}, cap={loss_cap})")
                return

        # fetch bars via unified provider (futu → yfinance fallback)
        bars, source = get_bars_safely(client, symbol, ktype, slow + 1)
        closes = [float(b.get("close", 0) or 0) for b in bars if float(b.get("close", 0) or 0) > 0]
        if len(closes) < slow:
            insert_run(strategy_id, "SKIP", f"Not enough bars from {source}: have {len(closes)}, need {slow}")
            return

        last_price = closes[-1]
        fast_prev = _sma(closes[-(fast + 1):-1])
        slow_prev = _sma(closes[-(slow + 1):-1])
        fast_now = _sma(closes[-fast:])
        slow_now = _sma(closes[-slow:])

        pos_qty, avg_cost = _current_position(client, symbol)
        # flatten-before-close: exit positions even if no cross
        if pos_qty > 0 and in_flatten_window(cfg=cfg):
            client.place_order(symbol=symbol, qty=pos_qty, side="SELL", order_type="MARKET")
            insert_run(strategy_id, "TRADE", f"[{source}] FLATTEN SELL {pos_qty} @~{last_price}")
            return

        # market-hours guard: never open new outside hours; allow exits
        ok_mkt, mkt_reason = market_ok_to_trade(cfg=cfg)
        if not ok_mkt and pos_qty == 0:
            insert_run(strategy_id, "SKIP", mkt_reason)
            return

        # exits first (if in position)
        if pos_qty > 0:
            exited = False
            if tp_pct > 0 and last_price >= avg_cost * (1.0 + tp_pct):
                client.place_order(symbol=symbol, qty=pos_qty, side="SELL", order_type="MARKET")
                insert_run(strategy_id, "TRADE", f"[{source}] TP SELL {pos_qty} @~{last_price} (avg {avg_cost}, tp {tp_pct})")
                exited = True
            elif sl_pct > 0 and last_price <= avg_cost * (1.0 - sl_pct):
                client.place_order(symbol=symbol, qty=pos_qty, side="SELL", order_type="MARKET")
                insert_run(strategy_id, "TRADE", f"[{source}] SL SELL {pos_qty} @~{last_price} (avg {avg_cost}, sl {sl_pct})")
                exited = True

            if not exited and fast_prev >= slow_prev and fast_now < slow_now:
                client.place_order(symbol=symbol, qty=pos_qty, side="SELL", order_type="MARKET")
                insert_run(strategy_id, "TRADE", f"[{source}] CROSS-DOWN SELL {pos_qty} @~{last_price}")
                exited = True

            if exited:
                return
            else:
                insert_run(strategy_id, "OK",
                           f"[{source}] Holding {pos_qty}; fast={fast_now:.4f}, slow={slow_now:.4f}, last={last_price:.4f}")
                return

        # no position: look for entry (cross-up)
        if fast_prev <= slow_prev and fast_now > slow_now:
            trade_qty = qty_param
            if size_mode == "usd" and dollar_size > 0 and last_price > 0:
                trade_qty = math.floor(dollar_size / last_price)
                if trade_qty < 1:
                    insert_run(strategy_id, "SKIP", f"[{source}] Size too small at last={last_price:.4f}")
                    return

            open_count = _open_positions_count(client)
            ok, reason = check_trade_limits(
                symbol=symbol,
                side="BUY",
                qty=trade_qty,
                price=last_price,
                open_positions_count=open_count,
            )
            if not ok:
                insert_run(strategy_id, "SKIP", f"[{source}] Risk blocked entry: {reason}")
                return

            client.place_order(symbol=symbol, qty=trade_qty, side="BUY", order_type="MARKET")
            insert_run(strategy_id, "TRADE",
                       f"[{source}] BUY {trade_qty} @~{last_price} (fast {fast_now:.4f} > slow {slow_now:.4f})")
            return

        insert_run(strategy_id, "OK",
                   f"[{source}] No cross. fast={fast_now:.4f}, slow={slow_now:.4f}, last={last_price:.4f}")

    except Exception as e:
        insert_run(strategy_id, "SKIP", f"Bars/exec unavailable: {e}")
