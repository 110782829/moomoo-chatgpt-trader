# Grid search for MA-crossover on preloaded bars.
from __future__ import annotations
from typing import List, Dict
from .engine import run_ma_crossover

def run_ma_grid(
    bars,
    fast_min: int, fast_max: int, fast_step: int,
    slow_min: int, slow_max: int, slow_step: int,
    qty: float,
    size_mode: str,
    dollar_size: float,
    stop_loss_pct: float,
    take_profit_pct: float,
    commission_per_share: float,
    slippage_bps: float,
    top_n: int = 10,
) -> List[Dict]:
    out: List[Dict] = []
    for fast in range(int(fast_min), int(fast_max) + 1, int(fast_step)):
        for slow in range(int(slow_min), int(slow_max) + 1, int(slow_step)):
            if slow <= fast:
                continue
            res = run_ma_crossover(
                bars=bars,
                fast=fast,
                slow=slow,
                qty=qty,
                size_mode=size_mode,
                dollar_size=dollar_size,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
                commission_per_share=commission_per_share,
                slippage_bps=slippage_bps,
            )
            out.append({
                "fast": fast, "slow": slow,
                **res.metrics
            })
    # sort by gross_pnl desc, then win_rate desc
    out.sort(key=lambda d: (d.get("gross_pnl", 0.0), d.get("win_rate", 0.0)), reverse=True)
    return out[:max(1, int(top_n))]
