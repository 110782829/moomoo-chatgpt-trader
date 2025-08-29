from __future__ import annotations

"""
Universe discovery: score and surface promising symbols without a static watchlist.
Uses a seed list (settings overrideable) and computes features from recent bars
via core.market_data.get_bars_safely, then ranks by volatility and activity.
"""

from typing import Any, Dict, List, Tuple
import os

DEFAULT_SEED = [
    # Mega-cap tech and liquid names
    "US.AAPL","US.MSFT","US.NVDA","US.AMZN","US.META","US.GOOGL","US.GOOG","US.TSLA","US.AVGO","US.BRK.B",
    "US.XOM","US.JPM","US.V","US.UNH","US.WMT","US.LLY","US.MA","US.COST","US.PG","US.HD",
    # High-volume traders / semis / mega movers
    "US.AMD","US.SNOW","US.NFLX","US.CRM","US.NKE","US.PYPL","US.COIN","US.PDD","US.BABA","US.MARA",
    "US.PLTR","US.ABA","US.SOUN","US.SPY","US.QQQ","US.IWM",
]


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _features_from_bars(bars: List[Dict[str, Any]]) -> Dict[str, float]:
    # expects list of dicts with keys: open/high/low/close/Volume (yfinance) or lower-case
    closes = [_safe_float(b.get("close", b.get("Close"))) for b in bars if _safe_float(b.get("close", b.get("Close"))) > 0]
    highs = [_safe_float(b.get("high", b.get("High"))) for b in bars]
    lows = [_safe_float(b.get("low", b.get("Low"))) for b in bars]
    vols = [_safe_float(b.get("volume", b.get("Volume"))) for b in bars]
    if not closes:
        return {}
    px = closes[-1]
    # ATR(14)
    trs: List[float] = []
    for i in range(1, min(len(highs), len(lows), len(closes))):
        h, l, pc = highs[i], lows[i], closes[i-1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = (sum(trs[-14:]) / 14.0) if len(trs) >= 14 else (sum(trs) / len(trs) if trs else 0.0)
    atr_pct = (atr / px * 100.0) if px > 0 else 0.0
    # rel volume (today vs 20-day avg)
    rel_vol = 1.0
    if vols:
        avg20 = (sum(vols[-20:]) / min(20, len(vols))) if vols else 0.0
        lastv = vols[-1]
        rel_vol = (lastv / avg20) if avg20 > 0 else 1.0
    # 1d change
    prev_close = closes[-2] if len(closes) >= 2 else px
    chg1 = ((px - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0
    return {"px": px, "atr": atr, "atr_pct": atr_pct, "rel_vol": rel_vol, "change_1d_pct": chg1}


def _score(feat: Dict[str, float]) -> float:
    s = 0.0
    s += min(15.0, abs(feat.get("atr_pct", 0.0))) * 0.8
    s += min(10.0, abs(feat.get("change_1d_pct", 0.0))) * 0.4
    s += min(10.0, feat.get("rel_vol", 1.0)) * 0.5
    return s


def _load_seed(get_setting) -> List[str]:  # type: ignore
    try:
        raw = get_setting("autopilot.discovery_seed")
        if raw:
            import json
            v = json.loads(raw)
            if isinstance(v, list) and v:
                out = []
                for s in v:
                    s = str(s or "").strip().upper()
                    if not s:
                        continue
                    out.append(s if "." in s else f"US.{s}")
                return out
    except Exception:
        pass
    return DEFAULT_SEED


def discover_symbols(client, limit: int = 20, ktype: str = "K_DAY", seed_cap: int = 60) -> List[str]:
    """
    Returns a ranked list of US.TICKER symbols discovered from a seed
    (settings override or DEFAULT_SEED), scored by ATR%, 1d change, and rel volume.
    """
    try:
        from core.storage import get_setting  # type: ignore
    except Exception:
        get_setting = None  # type: ignore

    seed = DEFAULT_SEED
    if get_setting is not None:
        seed = _load_seed(get_setting)

    # trim seed so discovery is fast
    seed = seed[: int(os.getenv("AUTOPILOT_DISCOVERY_SEED_CAP", str(seed_cap)) or seed_cap)]

    from core.market_data import get_bars_safely
    feats: List[Tuple[str, Dict[str, float]]] = []
    for sym in seed:
        try:
            bars, _src = get_bars_safely(client, sym, ktype, 60)
            f = _features_from_bars(bars or [])
            if f:
                feats.append((sym, f))
        except Exception:
            continue

    ranked = sorted(feats, key=lambda t: _score(t[1]), reverse=True)
    return [sym for sym, _ in ranked[:limit]]
