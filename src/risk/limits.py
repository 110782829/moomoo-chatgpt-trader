# src/risk/limits.py
"""
Shared order-limit checks used by API endpoints and automated strategies.
Raises ValueError("reason") when a check fails; callers translate to HTTP 400 or SKIP.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
import json
from typing import Optional, Sequence, Dict, Any

from core.market_data import get_bars_safely


_DEFAULT_CFG = {
    "enabled": True,
    "max_usd_per_trade": 1000.0,
    "max_open_positions": 5,
    "max_daily_loss_usd": 200.0,  # not enforced here yet
    "symbol_whitelist": [],
    "trading_hours_pt": {"start": "06:30", "end": "13:00"},
    "flatten_before_close_min": 10,
}


def load_risk_cfg() -> Dict[str, Any]:
    """Load risk config from data/risk.json with sensible defaults."""
    p = Path("data/risk.json")
    if p.exists():
        try:
            cfg = json.loads(p.read_text())
            # merge defaults
            m = _DEFAULT_CFG.copy()
            m.update({k: v for k, v in cfg.items() if v is not None})
            return m
        except Exception:
            pass
    return _DEFAULT_CFG.copy()


def _parse_hhmm(s: str) -> time:
    hh, mm = s.split(":")
    return time(int(hh), int(mm))


def _now_local() -> datetime:
    # Keep it simple: use system-local time (your dev is PT).
    return datetime.now()


def _is_outside_trading_hours(cfg: Dict[str, Any]) -> bool:
    th = cfg.get("trading_hours_pt") or {}
    start = _parse_hhmm(str(th.get("start", "06:30")))
    end = _parse_hhmm(str(th.get("end", "13:00")))
    now = _now_local().time()
    return not (start <= now <= end)


def _within_flatten_window(cfg: Dict[str, Any]) -> bool:
    mins = int(cfg.get("flatten_before_close_min") or 0)
    if mins <= 0:
        return False
    th = cfg.get("trading_hours_pt") or {}
    end = _parse_hhmm(str(th.get("end", "13:00")))
    now = _now_local()
    close_dt = now.replace(hour=end.hour, minute=end.minute, second=0, microsecond=0)
    return now >= (close_dt - timedelta(minutes=mins))


def _estimate_price(client, symbol: str, order_type: str, price: Optional[float]) -> float:
    if price and float(price) > 0:
        return float(price)
    if (order_type or "").upper() != "MARKET":
        return float(price or 0)
    # try last close via safe fallback (futu→yfinance)
    try:
        bars, _src = get_bars_safely(client, symbol, "K_1M", 1)
        if bars:
            px = float(bars[-1].get("close", 0) or 0)
            return px
    except Exception:
        pass
    return 0.0


def _count_open_positions(client) -> int:
    try:
        pos = client.get_positions()
        return sum(1 for p in pos if float(p.get("qty", 0) or 0) > 0)
    except Exception:
        return 0


def enforce_order_limits(
    client,
    symbol: str,
    qty: float,
    side: str,
    order_type: str = "MARKET",
    price: Optional[float] = None,
) -> None:
    """
    Raises ValueError with message if a limit would be violated.
    """
    cfg = load_risk_cfg()
    if not cfg.get("enabled", True):
        return

    side_u = (side or "").upper()

    # Whitelist (only enforced for new buys)
    wl = cfg.get("symbol_whitelist") or []
    if wl and side_u.startswith("BUY") and symbol not in wl:
        raise ValueError(f"{symbol} not in whitelist")

    # Trading hours (block buys outside; allow sells to exit risk)
    if side_u.startswith("BUY") and _is_outside_trading_hours(cfg):
        raise ValueError("outside trading hours")

    # Flatten-before-close (block new buys close to end)
    if side_u.startswith("BUY") and _within_flatten_window(cfg):
        mins = int(cfg.get("flatten_before_close_min") or 0)
        raise ValueError(f"within {mins} min of close")

    # Per-trade notional cap
    est_px = _estimate_price(client, symbol, order_type, price)
    if est_px > 0:
        cap = float(cfg.get("max_usd_per_trade") or 0)
        if cap > 0 and est_px * float(qty) > cap:
            raise ValueError(f"notional ${est_px * float(qty):.2f} exceeds cap ${cap:.2f}")

    # Open positions count cap (buys only)
    cap_pos = int(cfg.get("max_open_positions") or 0)
    if side_u.startswith("BUY") and cap_pos > 0:
        open_cnt = _count_open_positions(client)
        if open_cnt >= cap_pos:
            raise ValueError(f"open positions {open_cnt} reached cap {cap_pos}")