
# src/autopilot/indicators.py
from __future__ import annotations
from typing import List

def sma(values: List[float], window: int) -> float:
    if not values or window <= 0 or len(values) < window:
        return 0.0
    return sum(values[-window:]) / float(window)

def rsi(closes: List[float], period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains = 0.0
    losses = 0.0
    for i in range(-period, 0):
        diff = closes[i] - closes[i-1]
        if diff >= 0: gains += diff
        else: losses -= diff
    if losses == 0:
        return 100.0
    rs = (gains / period) / (losses / period)
    return 100.0 - (100.0 / (1.0 + rs))

def atr(highs: List[float], lows: List[float], closes: List[float], period: int = 14) -> float:
    n = min(len(highs), len(lows), len(closes))
    if n < period + 1:
        return 0.0
    trs = []
    for i in range(1, n):
        h = highs[i]
        l = lows[i]
        pc = closes[i-1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
    if len(trs) < period:
        return 0.0
    return sum(trs[-period:]) / float(period)

def trend_from_mas(ma50: float, ma200: float) -> str:
    if ma50 > ma200 * 1.002:  # small buffer
        return "up"
    if ma50 < ma200 * 0.998:
        return "down"
    return "flat"
