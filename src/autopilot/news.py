from __future__ import annotations

"""
Lightweight news caching for symbols.
Uses settings storage (keyed by 'news:US.TICKER') to cache a compact summary
and tone for recent headlines. Falls back gracefully when yfinance is missing.
"""

import json
import os
import time
from typing import Any, Dict, List, Tuple

try:
    from core.storage import get_setting, set_setting  # type: ignore
except Exception:  # pragma: no cover
    get_setting = None  # type: ignore
    set_setting = None  # type: ignore


def _now_ts() -> int:
    return int(time.time())


def _symbol_core(sym: str) -> str:
    return sym.replace("US.", "").strip().upper()


def _fetch_news_rows(sym: str, lookback_sec: int = 36 * 3600) -> List[Dict[str, Any]]:
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return []

    try:
        tkr = yf.Ticker(_symbol_core(sym))  # type: ignore[attr-defined]
        raw = getattr(tkr, "news", None)
        if not isinstance(raw, list):
            return []
        now = _now_ts()
        rows: List[Dict[str, Any]] = []
        for it in raw:
            ts = int(it.get("providerPublishTime") or it.get("pubDate", 0) or 0)
            if ts and (now - ts) <= lookback_sec:
                rows.append({
                    "title": str(it.get("title") or "").strip(),
                    "ts": ts,
                    "link": it.get("link") or it.get("url"),
                    "publisher": it.get("publisher") or it.get("provider") or "",
                })
        rows.sort(key=lambda r: r.get("ts") or 0, reverse=True)
        return rows
    except Exception:
        return []


_BULLISH = ("beat", "beats", "upgrade", "upgraded", "raises guidance", "surge", "soar", "soars", "rally")
_BEARISH = ("miss", "misses", "downgrade", "downgraded", "cuts guidance", "plunge", "falls", "weak")


def _summarize(rows: List[Dict[str, Any]], max_items: int = 2) -> Tuple[str, str, int]:
    if not rows:
        return "", "neutral", 0
    head = rows[:max_items]
    titles = "; ".join([str(r.get("title") or "").strip() for r in head if r.get("title")])[:280]
    low = titles.lower()
    tone = "neutral"
    if any(x in low for x in _BULLISH):
        tone = "bullish"
    if any(x in low for x in _BEARISH):
        tone = "bearish"
    ts = int(head[0].get("ts") or 0)
    return titles, tone, ts


def get_cached_news(sym: str, ttl_sec: int = 1800, max_items: int = 2) -> Dict[str, Any]:
    """
    Returns {sym, summary, tone, ts}. Uses settings as cache.
    """
    key = f"news:{sym}"
    now = _now_ts()
    cached: Dict[str, Any] = {}
    if get_setting is not None:
        try:
            raw = get_setting(key)
            if raw:
                cached = json.loads(raw)
        except Exception:
            cached = {}

    cached_at = int(cached.get("cached_at") or 0)
    if cached and (now - cached_at) <= int(ttl_sec):
        return {
            "sym": sym,
            "summary": str(cached.get("summary") or ""),
            "tone": str(cached.get("tone") or "neutral"),
            "ts": int(cached.get("ts") or 0),
        }

    rows = _fetch_news_rows(sym)
    summary, tone, ts = _summarize(rows, max_items=max_items)
    payload = {"summary": summary, "tone": tone, "ts": ts, "cached_at": now}
    if set_setting is not None:
        try:
            set_setting(key, payload)
        except Exception:
            pass
    return {"sym": sym, **payload}


def get_news_bulk(symbols: List[str], ttl_sec: int = 1800, max_items: int = 2, cap: int = 6) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for sym in symbols[:cap]:
        try:
            out.append(get_cached_news(sym, ttl_sec=ttl_sec, max_items=max_items))
        except Exception:
            continue
    return out

