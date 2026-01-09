"""
Unified market data helpers.

Uses the configured provider without fallback.
"""

from __future__ import annotations
from typing import Dict, Any, List, Tuple
import contextlib
import io
import os
import re

# local client utils
from core.moomoo_client import MoomooClient, _df_to_records
from moomoo import SubType
from core.storage import get_setting

# --- Moomoo ---

def _normalize(symbol: str) -> str:
    return symbol if "." in symbol else f"US.{symbol.upper()}"

def _bars_from_futu(client: MoomooClient, symbol: str, ktype: str, n: int) -> List[Dict[str, Any]]:
    if not client.quote_ctx:
        raise RuntimeError("Quote context not available")
    code = _normalize(symbol)
    subtype = getattr(SubType, ktype.upper(), SubType.K_1M)
    # subscribe before fetching bars
    ret, data = client.quote_ctx.subscribe([code], [subtype], True)
    if ret != 0:
        raise RuntimeError(f"subscribe failed: {data}")
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
            recs = _df_to_records(df)
            return recs[-n:] if isinstance(recs, list) else []
        except TypeError as e:
            last_err = e
            continue
    raise RuntimeError(f"get_cur_kline incompatible with this futu build: {last_err}")

# --- Yahoo Finance ---

def _yf_interval(ktype: str) -> str:
    ktype = ktype.upper()
    mapping = {
        "K_1M": "1m",
        "K_5M": "5m",
        "K_15M": "15m",
        "K_30M": "30m",
        "K_60M": "60m",
        "K_DAY": "1d",
        "K_1D": "1d",
    }
    return mapping.get(ktype, "1m")

def _symbol_for_yf(symbol: str) -> str:
    # US.AAPL -> AAPL
    return symbol.split(".")[-1]


def _yf_period(interval: str, n: int) -> str:
    # cover at least n bars
    interval = interval.lower()
    if interval.endswith("m"):
        per_day = {"1m": 390, "5m": 78, "15m": 26, "30m": 13, "60m": 6}
        bpd = per_day.get(interval, 390)
        days = (n + bpd - 1) // bpd
        cap = 7 if interval == "1m" else 60
        days = max(5, min(days, cap))
        return f"{days}d"
    if n <= 60:
        return f"{n}d"
    return "2y" if n <= 365 * 2 else "max"

def _bars_from_yf(symbol: str, ktype: str, n: int) -> List[Dict[str, Any]]:
    try:
        import yfinance as yf  # install at runtime if needed
    except Exception as e:
        raise RuntimeError("yfinance not installed; run `pip install yfinance`") from e

    interval = _yf_interval(ktype)
    period = _yf_period(interval, n)

    # Suppress yfinance noisy stderr (e.g., delisted symbols). Try raise_errors flag if available.
    dl_kwargs = dict(
        tickers=_symbol_for_yf(symbol),
        period=period,
        interval=interval,
        auto_adjust=False,
        progress=False,
        threads=False,
        group_by="column",
    )
    df = None
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            df = yf.download(**dl_kwargs, raise_errors=False)  # type: ignore[call-arg]
        except TypeError:
            # Older yfinance without raise_errors
            df = yf.download(**dl_kwargs)
    if df is None or df.empty:
        return []

    import pandas as pd  # local import
    if isinstance(df.columns, pd.MultiIndex):  # flatten ticker columns
        df.columns = [c[0] for c in df.columns]

    # Standardize to list[dict]
    df = df.tail(n)
    out: List[Dict[str, Any]] = []
    for ts, row in df.iterrows():
        open_v = row.get("Open")
        high_v = row.get("High")
        low_v = row.get("Low")
        close_v = row.get("Close")
        vol_v = row.get("Volume")
        out.append({
            "time": str(ts.to_pydatetime()),
            "open": float(open_v) if open_v is not None else 0.0,
            "high": float(high_v) if high_v is not None else 0.0,
            "low": float(low_v) if low_v is not None else 0.0,
            "close": float(close_v) if close_v is not None else 0.0,
            "volume": float(vol_v) if vol_v is not None else 0.0,
        })
    return out

# --- Public API ---

_ENTITLEMENT_MSG = re.compile(r"No right to get the quote", re.IGNORECASE)

def _data_source() -> str:
    s = get_setting("autopilot.data_source")
    if s:
        return str(s).lower()
    env = os.getenv("AUTOPILOT_DATA_SOURCE")
    if env:
        return env.lower()
    return "yfinance"

def get_bars_safely(client: MoomooClient, symbol: str, ktype: str, n: int) -> Tuple[List[Dict[str, Any]], str]:
    """
    Return (bars, source). Source is 'futu' or 'yfinance'.
    """
    src = _data_source()
    if src == "yfinance":
        # simple retry/backoff for transient Yahoo issues
        import time as _t
        bars = []
        for i in range(3):
            try:
                bars = _bars_from_yf(symbol, ktype, n)
                if bars:
                    break
            except Exception:
                pass
            _t.sleep(0.3 * (i + 1))
        if not bars:
            raise RuntimeError("yfinance returned no data")
        return bars, "yfinance"
    if src in ("futu", "moomoo"):
        if not client:
            raise RuntimeError("Moomoo client not available")
        bars = _bars_from_futu(client, symbol, ktype, n)
        return bars, "futu"
    raise RuntimeError(f"unknown data source: {src}")
