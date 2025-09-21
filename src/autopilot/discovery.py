from __future__ import annotations

"""
Universe discovery: score and surface promising symbols without a static watchlist.
Uses a seed list (settings overrideable) and computes features from recent bars
via core.market_data.get_bars_safely, then ranks by volatility and activity.
"""

from typing import Any, Dict, Iterable, List, Sequence
import os
import json
from datetime import datetime, timezone

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


def _normalize_symbols(symbols: Iterable[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for raw in symbols:
        sym = str(raw or "").strip().upper()
        if not sym:
            continue
        if "." not in sym:
            sym = f"US.{sym}"
        if sym not in seen:
            seen.add(sym)
            out.append(sym)
    return out


def _load_seed_override() -> List[str]:
    try:
        from core.storage import get_setting  # type: ignore
    except Exception:  # pragma: no cover
        return []
    try:
        raw = get_setting("autopilot.discovery_seed")
        if not raw:
            return []
        data = json.loads(raw)
        if isinstance(data, Sequence):
            return _normalize_symbols(data)
    except Exception:
        return []
    return []


def compute_symbol_universe(
    client,
    symbols: Sequence[str],
    *,
    ktype: str = "K_DAY",
    lookback: int = 60,
) -> List[Dict[str, Any]]:
    """
    Return feature dicts for the provided symbols with discovery score metadata.
    Each entry: {"symbol", "score", "features": {...}, "source": str}
    """
    from core.market_data import get_bars_safely

    universe: List[Dict[str, Any]] = []
    for sym in _normalize_symbols(symbols):
        try:
            bars, source = get_bars_safely(client, sym, ktype, lookback)
        except Exception:
            continue
        feats = _features_from_bars(bars or [])
        if not feats:
            continue
        score = _score(feats)
        universe.append({
            "symbol": sym,
            "score": score,
            "features": feats,
            "source": source,
        })
    universe.sort(key=lambda row: float(row.get("score") or 0.0), reverse=True)
    return universe


def discover_symbols(
    client,
    limit: int = 20,
    *,
    ktype: str = "K_DAY",
    seed_cap: int = 60,
    seed: Sequence[str] | None = None,
) -> List[str]:
    """Backward-compatible helper to surface a ranked list of discovery symbols."""
    if seed is None:
        override = _load_seed_override()
        seed = override or DEFAULT_SEED
    seed = list(seed)[: int(os.getenv("AUTOPILOT_DISCOVERY_SEED_CAP", str(seed_cap)) or seed_cap)]
    ranked = compute_symbol_universe(client, seed, ktype=ktype, lookback=60)
    return [row["symbol"] for row in ranked[:limit]]


def stamp_now() -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "run_at": now.isoformat(),
        "run_day": now.astimezone().strftime("%Y-%m-%d"),
    }
