# Basic risk helpers used by strategies.
from __future__ import annotations
import os, json
from pathlib import Path
from datetime import datetime, time, timedelta, date
from zoneinfo import ZoneInfo
from typing import Tuple, Optional, Dict, Any, List

RISK_PATH = Path(os.getenv("RISK_FILE", "data/risk.json"))
_PT = ZoneInfo("America/Los_Angeles")

_DEFAULT = {
    "enabled": True,
    "max_usd_per_trade": 1000.0,
    "max_open_positions": 5,
    "max_daily_loss_usd": 200.0,
    "symbol_whitelist": [],
    "trading_hours_pt": {"start": "06:30", "end": "13:00"},
    "flatten_before_close_min": 5,
}

def load_cfg() -> Dict[str, Any]:
    try:
        if RISK_PATH.exists():
            return json.loads(RISK_PATH.read_text())
    except Exception:
        pass
    RISK_PATH.parent.mkdir(parents=True, exist_ok=True)
    RISK_PATH.write_text(json.dumps(_DEFAULT, indent=2))
    return dict(_DEFAULT)

def _parse_hhmm(s: str) -> time:
    hh, mm = s.split(":")
    return time(int(hh), int(mm))

def market_open_now(cfg: Optional[Dict[str, Any]] = None, now: Optional[datetime] = None) -> bool:
    cfg = cfg or load_cfg()
    now = now or datetime.now(_PT)
    hours = cfg.get("trading_hours_pt", {"start": "06:30", "end": "13:00"})
    start = _parse_hhmm(hours.get("start", "06:30"))
    end = _parse_hhmm(hours.get("end", "13:00"))
    t = now.time()
    return (t >= start) and (t <= end)

def in_flatten_window(cfg: Optional[Dict[str, Any]] = None, now: Optional[datetime] = None) -> bool:
    cfg = cfg or load_cfg()
    now = now or datetime.now(_PT)
    end_s = cfg.get("trading_hours_pt", {}).get("end", "13:00")
    end_t = _parse_hhmm(end_s)
    end_dt = datetime.combine(now.date(), end_t, tzinfo=_PT)
    mins = int(cfg.get("flatten_before_close_min", 5) or 0)
    return now >= (end_dt - timedelta(minutes=mins))

def symbol_allowed(symbol: str, cfg: Optional[Dict[str, Any]] = None) -> bool:
    cfg = cfg or load_cfg()
    wl: List[str] = cfg.get("symbol_whitelist") or []
    if not wl:
        return True
    sym = symbol.split(".")[-1].upper()
    wl_norm = [s.split(".")[-1].upper() for s in wl]
    return sym in wl_norm

def _is_us_holiday(d: date) -> bool:
    """
    Lightweight holiday check:
    - Always skip weekends.
    - If python-holidays is available and env US_HOLIDAYS!=0, use it.
    - Otherwise only weekend filter is applied.
    """
    if d.weekday() >= 5:  # 5=Sat, 6=Sun
        return True
    use_holidays = os.getenv("US_HOLIDAYS", "1") != "0"
    if use_holidays:
        try:
            import holidays  # type: ignore
            us = holidays.UnitedStates()  # NYSE holidays close enough for dev
            return d in us
        except Exception:
            return False
    return False

def is_trading_day_now(now: Optional[datetime] = None) -> bool:
    now = now or datetime.now(_PT)
    return not _is_us_holiday(now.date())

def market_ok_to_trade(cfg: Optional[Dict[str, Any]] = None, now: Optional[datetime] = None) -> Tuple[bool, str]:
    """
    Combined trading-day + hours gate.
    """
    cfg = cfg or load_cfg()
    now = now or datetime.now(_PT)
    if not is_trading_day_now(now):
        return False, "Market closed today (weekend/holiday)"
    if not market_open_now(cfg=cfg, now=now):
        return False, "Outside trading hours"
    return True, "ok"

def check_trade_limits(
    symbol: str,
    side: str,
    qty: float,
    price: float,
    open_positions_count: int,
    cfg: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    cfg = cfg or load_cfg()
    if not cfg.get("enabled", True):
        return True, "risk disabled"

    if not symbol_allowed(symbol, cfg):
        return False, f"symbol not in whitelist: {symbol}"

    max_pos = int(cfg.get("max_open_positions", 5))
    if open_positions_count is not None and open_positions_count >= max_pos and side.upper() == "BUY":
        return False, f"max open positions reached: {open_positions_count}/{max_pos}"

    max_usd = float(cfg.get("max_usd_per_trade", 1000.0) or 0.0)
    notional = abs(float(qty) * float(price))
    if max_usd > 0 and side.upper() == "BUY" and notional > max_usd:
        return False, f"trade notional {notional:.2f} exceeds max {max_usd:.2f}"
    return True, "ok"
