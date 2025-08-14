"""
Backtesting engine for evaluating trading strategies.
"""
# Simple backtest engine for MA-crossover strategies.
# Uses local CSV bars: data/bars/{SYMBOL}_{KTYPE}.csv
# CSV columns: time,open,high,low,close,volume

from __future__ import annotations
import csv, math, os
from dataclasses import dataclass
from typing import Dict, List, Iterable

BAR_DIR = os.getenv("BAR_DIR", "data/bars")

@dataclass
class Bar:
    ts: str
    o: float
    h: float
    l: float
    c: float
    v: float

def load_bars_csv(symbol: str, ktype: str) -> List[Bar]:
    sym = symbol if "." not in symbol else symbol.split(".", 1)[1]
    path = os.path.join(BAR_DIR, f"{sym.upper()}_{ktype}.csv")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Bars file not found: {path}")
    out: List[Bar] = []
    with open(path, "r", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            out.append(Bar(
                ts=str(row["time"]),
                o=float(row["open"]),
                h=float(row["high"]),
                l=float(row["low"]),
                c=float(row["close"]),
                v=float(row.get("volume", 0) or 0),
            ))
    if not out:
        raise RuntimeError(f"No rows in {path}")
    # Ensure ascending time (fixes entry_ts <= exit_ts)
    out.sort(key=lambda b: b.ts)
    return out

def sma(seq: Iterable[float]) -> float:
    seq = list(seq)
    return sum(seq) / len(seq) if seq else 0.0

@dataclass
class Trade:
    entry_ts: str
    exit_ts: str
    side: str
    entry_px: float
    exit_px: float
    qty: float
    pnl: float

@dataclass
class BTResult:
    metrics: Dict[str, float]
    trades: List[Trade]

def run_ma_crossover(
    bars: List[Bar],
    fast: int,
    slow: int,
    qty: float = 1.0,
    size_mode: str = "shares",      # 'shares' | 'usd'
    dollar_size: float = 0.0,
    stop_loss_pct: float = 0.0,
    take_profit_pct: float = 0.0,
    commission_per_share: float = 0.0,
    slippage_bps: float = 0.0,      # bps applied on entry + exit
) -> BTResult:
    if slow <= fast:
        raise ValueError("slow must be > fast")
    closes = [b.c for b in bars]

    pos_qty = 0.0
    avg_cost = 0.0
    entry_ts = ""          # real entry timestamp (next bar)
    entry_px_mem = 0.0

    trades: List[Trade] = []
    equity = 0.0
    peak_equity = 0.0
    max_dd = 0.0
    wins = 0
    losses = 0

    def slip(px: float) -> float:
        return px * (1.0 + (slippage_bps/1e4))

    for i in range(1, len(bars)):  # start at 1 to have a previous window
        # SMAs up to current bar i
        fast_prev = sma(closes[max(0, i-fast-1): i])
        slow_prev = sma(closes[max(0, i-slow-1): i])
        fast_now  = sma(closes[max(0, i-fast+1): i+1])
        slow_now  = sma(closes[max(0, i-slow+1): i+1])

        # Next-bar fill semantics
        has_next = (i + 1 < len(bars))
        next_ts = bars[i+1].ts if has_next else bars[i].ts
        next_open = bars[i+1].o if has_next else bars[i].c  # fallback

        # --- exits first (if in position) ---
        if pos_qty > 0:
            if take_profit_pct > 0 and bars[i].c >= avg_cost * (1.0 + take_profit_pct):
                exit_px = slip(next_open)
                pnl = (exit_px - avg_cost) * pos_qty - commission_per_share*pos_qty
                trades.append(Trade(entry_ts, next_ts, "LONG", entry_px_mem, exit_px, pos_qty, pnl))
                equity += pnl
                pos_qty = 0.0; avg_cost = 0.0; entry_ts = ""; entry_px_mem = 0.0
            elif stop_loss_pct > 0 and bars[i].c <= avg_cost * (1.0 - stop_loss_pct):
                exit_px = slip(next_open)
                pnl = (exit_px - avg_cost) * pos_qty - commission_per_share*pos_qty
                trades.append(Trade(entry_ts, next_ts, "LONG", entry_px_mem, exit_px, pos_qty, pnl))
                equity += pnl
                pos_qty = 0.0; avg_cost = 0.0; entry_ts = ""; entry_px_mem = 0.0
            elif fast_prev >= slow_prev and fast_now < slow_now:
                exit_px = slip(next_open)
                pnl = (exit_px - avg_cost) * pos_qty - commission_per_share*pos_qty
                trades.append(Trade(entry_ts, next_ts, "LONG", entry_px_mem, exit_px, pos_qty, pnl))
                equity += pnl
                pos_qty = 0.0; avg_cost = 0.0; entry_ts = ""; entry_px_mem = 0.0

        # --- entry if flat and cross-up ---
        if pos_qty == 0 and fast_prev <= slow_prev and fast_now > slow_now:
            fill_px = slip(next_open)
            actual_qty = qty
            if size_mode.lower() == "usd" and dollar_size > 0 and fill_px > 0:
                actual_qty = math.floor(dollar_size / fill_px)
                if actual_qty < 1:
                    pass  # too small; skip
                else:
                    pos_qty = actual_qty; avg_cost = fill_px; entry_ts = next_ts; entry_px_mem = fill_px
                    equity -= commission_per_share*pos_qty
            else:
                pos_qty = actual_qty; avg_cost = fill_px; entry_ts = next_ts; entry_px_mem = fill_px
                equity -= commission_per_share*pos_qty

        # drawdown update
        peak_equity = max(peak_equity, equity)
        max_dd = min(max_dd, equity - peak_equity)

    # close at last bar if still open
    if pos_qty > 0:
        exit_ts = bars[-1].ts
        exit_px = slip(bars[-1].c)
        pnl = (exit_px - avg_cost) * pos_qty - commission_per_share*pos_qty
        trades.append(Trade(entry_ts or bars[-1].ts, exit_ts, "LONG", entry_px_mem or avg_cost, exit_px, pos_qty, pnl))
        equity += pnl

    for t in trades:
        if t.pnl >= 0: wins += 1
        else: losses += 1

    metrics = {
        "trades": float(len(trades)),
        "wins": float(wins),
        "losses": float(losses),
        "win_rate": (wins/len(trades))*100.0 if trades else 0.0,
        "gross_pnl": sum(t.pnl for t in trades),
        "avg_pnl": (sum(t.pnl for t in trades)/len(trades)) if trades else 0.0,
        "max_drawdown": float(max_dd),
    }
    return BTResult(metrics=metrics, trades=trades)
