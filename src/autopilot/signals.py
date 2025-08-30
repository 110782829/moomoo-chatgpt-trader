from __future__ import annotations

"""
Signal computation library (advice only, no orders).

Produces lightweight, per-symbol signals used by the planner:
  - macd_cross:     MACD vs Signal line cross with strength from distance
  - bb_breakout:    Close breaks Bollinger bands; strength from z-score
  - stoch_rsi_ext:  Stochastic RSI extremes; strength by distance from band

Each signal dict has keys:
  {"strategy": str, "sym": str, "signal": "long"|"short", "strength": float 0..1,
   "ttl_sec": int, "metadata": dict }

All functions are pure and defensively coded to return [] on bad inputs.
"""

from typing import Dict, List, Sequence, Tuple

try:
    import math
except Exception:  # pragma: no cover
    math = None  # type: ignore


def _ema(seq: Sequence[float], period: int) -> List[float]:
    seq = [float(x) for x in seq if x is not None]
    if period <= 1 or len(seq) == 0:
        return list(seq)
    k = 2.0 / (period + 1.0)
    out: List[float] = []
    ema = seq[0]
    for x in seq:
        ema = (x * k) + (ema * (1.0 - k))
        out.append(ema)
    return out


def _std(seq: Sequence[float]) -> float:
    n = len(seq)
    if n <= 1:
        return 0.0
    mean = sum(seq) / n
    var = sum((x - mean) ** 2 for x in seq) / n
    return var ** 0.5


def _last_two(values: Sequence[float]) -> Tuple[float, float]:
    if not values:
        return 0.0, 0.0
    if len(values) == 1:
        return float(values[-1]), float(values[-1])
    return float(values[-2]), float(values[-1])


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def macd_values(closes: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[List[float], List[float], List[float]]:
    if not closes or len(closes) < max(fast, slow, signal) + 2:
        return [], [], []
    ema_fast = _ema(closes, fast)
    ema_slow = _ema(closes, slow)
    # align lengths
    n = min(len(ema_fast), len(ema_slow))
    macd_line = [ema_fast[i] - ema_slow[i] for i in range(-n, 0)]
    sig_line = _ema(macd_line, signal)
    m = min(len(macd_line), len(sig_line))
    macd_line = macd_line[-m:]
    sig_line = sig_line[-m:]
    hist = [macd_line[i] - sig_line[i] for i in range(m)]
    return macd_line, sig_line, hist


def macd_cross_signals(sym: str, closes: Sequence[float]) -> List[Dict]:
    macd_line, sig_line, _ = macd_values(closes)
    if len(macd_line) < 2 or len(sig_line) < 2:
        return []
    m_prev, m_now = _last_two(macd_line)
    s_prev, s_now = _last_two(sig_line)
    crossed_up = (m_prev <= s_prev) and (m_now > s_now)
    crossed_dn = (m_prev >= s_prev) and (m_now < s_now)
    if not (crossed_up or crossed_dn):
        return []
    dist = abs(m_now - s_now)
    base = abs(closes[-1]) or 1.0
    strength = _clamp01(dist / base * 5.0)  # heuristically scale
    return [{
        "strategy": "macd_cross",
        "sym": sym,
        "signal": "long" if crossed_up else "short",
        "strength": strength,
        "ttl_sec": 180,
        "metadata": {"macd": m_now, "signal": s_now, "dist": dist}
    }]


def bb_breakout_signals(sym: str, closes: Sequence[float], period: int = 20, mult: float = 2.0) -> List[Dict]:
    if not closes or len(closes) < period + 2:
        return []
    window = [float(x) for x in closes[-period:]]
    mid = sum(window) / len(window)
    sd = _std(window)
    upper = mid + mult * sd
    lower = mid - mult * sd
    last = float(closes[-1])
    z = 0.0 if sd == 0 else (last - mid) / sd
    if last > upper:
        return [{
            "strategy": "bb_breakout",
            "sym": sym,
            "signal": "long",
            "strength": _clamp01(abs(z) / mult),
            "ttl_sec": 180,
            "metadata": {"mid": mid, "upper": upper, "lower": lower, "z": z}
        }]
    if last < lower:
        return [{
            "strategy": "bb_breakout",
            "sym": sym,
            "signal": "short",
            "strength": _clamp01(abs(z) / mult),
            "ttl_sec": 180,
            "metadata": {"mid": mid, "upper": upper, "lower": lower, "z": z}
        }]
    return []


def _rsi_series(closes: Sequence[float], period: int = 14) -> List[float]:
    # simple RSI series (not optimized)
    if not closes or len(closes) < period + 2:
        return []
    gains: List[float] = []
    losses: List[float] = []
    rsis: List[float] = []
    for i in range(1, len(closes)):
        chg = float(closes[i]) - float(closes[i - 1])
        gains.append(max(0.0, chg))
        losses.append(max(0.0, -chg))
        if i >= period:
            g = sum(gains[i - period:i]) / period
            l = sum(losses[i - period:i]) / period
            rs = (g / l) if l > 0 else float('inf')
            rsi = 100.0 - (100.0 / (1.0 + rs)) if l > 0 else 100.0
            rsis.append(rsi)
    return rsis


def stoch_rsi_k(closes: Sequence[float], period: int = 14, smooth_k: int = 3) -> float:
    rsis = _rsi_series(closes, period=period)
    if len(rsis) < period + 1:
        return 50.0
    window = rsis[-period:]
    lo = min(window)
    hi = max(window)
    k_raw = 50.0 if hi == lo else (rsis[-1] - lo) / (hi - lo) * 100.0
    # smooth
    ks = [k_raw]
    for _ in range(smooth_k - 1):
        ks.append(k_raw)
    return sum(ks) / len(ks)


def stoch_rsi_signals(sym: str, closes: Sequence[float]) -> List[Dict]:
    k = stoch_rsi_k(closes)
    out: List[Dict] = []
    if k <= 20.0:
        out.append({
            "strategy": "stoch_rsi_extreme",
            "sym": sym,
            "signal": "long",
            "strength": _clamp01((20.0 - k) / 20.0),
            "ttl_sec": 180,
            "metadata": {"k": k}
        })
    elif k >= 80.0:
        out.append({
            "strategy": "stoch_rsi_extreme",
            "sym": sym,
            "signal": "short",
            "strength": _clamp01((k - 80.0) / 20.0),
            "ttl_sec": 180,
            "metadata": {"k": k}
        })
    return out


def signals_for_series(sym: str, highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> List[Dict]:
    try:
        out: List[Dict] = []
        if not closes or len(closes) < 5:
            return out
        out.extend(macd_cross_signals(sym, closes))
        out.extend(bb_breakout_signals(sym, closes))
        out.extend(stoch_rsi_signals(sym, closes))
        return out
    except Exception:
        return []

