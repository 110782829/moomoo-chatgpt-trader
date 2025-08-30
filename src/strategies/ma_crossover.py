"""
Moving Average Crossover (signal-only).

This module now emits signals only and does NOT place orders.
It computes fast/slow SMAs and logs a signal when a cross occurs:
  - cross_up   → potential long bias
  - cross_down → potential exit/short bias

Signals are recorded via:
  - insert_run(..., status="SIGNAL", message=...)
  - insert_action_log(action="strategy_signal", reason="ma_crossover", extra={...})

Execution is handled by Autopilot using these and other signals; this strategy
no longer performs any buying or selling on its own.
"""

from typing import Dict, Any, List, Optional
import math

from core.moomoo_client import MoomooClient, TrdEnv
from core.storage import insert_run, pnl_today, insert_action_log

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

def _emit_signal(strategy_id: int, symbol: str, ktype: str, source: str,
                 fast: int, slow: int, fast_prev: float, slow_prev: float,
                 fast_now: float, slow_now: float, direction: str) -> None:
    """Record a signal event into runs + action_log."""
    strength = 0.0
    try:
        # simple relative distance as a proxy for confidence
        if slow_now != 0:
            strength = float((fast_now / slow_now) - 1.0)
    except Exception:
        strength = 0.0

    msg = (
        f"[{source}] {direction.upper()} fast {fast_now:.4f} vs slow {slow_now:.4f} "
        f"(prev {fast_prev:.4f}/{slow_prev:.4f})"
    )
    insert_run(strategy_id, "SIGNAL", msg)
    try:
        insert_action_log(
            "strategy_signal",
            mode="auto",
            symbol=_normalize(symbol),
            reason="ma_crossover",
            status="ok",
            extra={
                "ktype": ktype,
                "fast": fast,
                "slow": slow,
                "fast_prev": fast_prev,
                "slow_prev": slow_prev,
                "fast_now": fast_now,
                "slow_now": slow_now,
                "direction": direction,
                "strength": strength,
                "source": source,
            },
        )
    except Exception:
        pass

def step(strategy_id: int, client: MoomooClient, symbol: str, params: Dict[str, Any]) -> None:
    # core params
    fast = int(params.get("fast", 20))
    slow = int(params.get("slow", 50))
    ktype = str(params.get("ktype", "K_1M"))

    # legacy params (ignored for signal-only but kept for compatibility)
    _qty_param = float(params.get("qty", 1))
    _size_mode = str(params.get("size_mode", "shares")).lower()
    _dollar_size = float(params.get("dollar_size", 0))
    _sl_pct = float(params.get("stop_loss_pct", 0))
    _tp_pct = float(params.get("take_profit_pct", 0))
    _allow_real = bool(params.get("allow_real", False))

    if slow <= fast:
        insert_run(strategy_id, "ERROR", f"Invalid params: slow({slow}) must be > fast({fast})")
        return

    try:
        # Account/env checks retained only to avoid noisy signals when not connected
        if not client.account_id:
            insert_run(strategy_id, "SKIP", "No account selected")
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

        # Emit cross signals only (no trading actions)
        if fast_prev <= slow_prev and fast_now > slow_now:
            _emit_signal(strategy_id, symbol, ktype, source,
                         fast, slow, fast_prev, slow_prev, fast_now, slow_now, direction="cross_up")
            return
        if fast_prev >= slow_prev and fast_now < slow_now:
            _emit_signal(strategy_id, symbol, ktype, source,
                         fast, slow, fast_prev, slow_prev, fast_now, slow_now, direction="cross_down")
            return

        insert_run(strategy_id, "OK", f"[{source}] No cross. fast={fast_now:.4f}, slow={slow_now:.4f}, last={last_price:.4f}")

    except Exception as e:
        insert_run(strategy_id, "SKIP", f"Bars/exec unavailable: {e}")
