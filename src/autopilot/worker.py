
# src/autopilot/worker.py
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Optional market data (yfinance)
try:
    import yfinance as yf  # type: ignore
except Exception:  # pragma: no cover
    yf = None  # type: ignore

# Storage (optional)
try:
    from ..core.storage import insert_action_log  # type: ignore
    _HAS_STORAGE = True
except Exception:  # pragma: no cover
    _HAS_STORAGE = False

from .planner_client import get_planner_client
from .schemas import PlannerOutput, validate_output
from . import indicators as ind


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_bars(symbol: str, period: str = "6mo", interval: str = "1d") -> tuple[list[float], list[float], list[float]]:
    """
    Return (highs, lows, closes) using yfinance if available; else empty lists.
    Symbols like 'US.AAPL' are normalized to 'AAPL' for yfinance.
    """
    if yf is None:
        return [], [], []
    try:
        yf_sym = symbol.replace("US.", "")
        df = yf.download(yf_sym, period=period, interval=interval, auto_adjust=True, progress=False)
        if df is None or df.empty:
            return [], [], []
        highs = [float(x) for x in df["High"].tolist()]
        lows = [float(x) for x in df["Low"].tolist()]
        closes = [float(x) for x in df["Close"].tolist()]
        return highs, lows, closes
    except Exception:
        return [], [], []


class AutopilotManager:
    def __init__(self, get_client, risk_loader):
        self.get_client = get_client
        self.risk_loader = risk_loader
        self._task: Optional[asyncio.Task] = None
        self._running: bool = False
        self.tick_sec: int = 15

        self.last_input: Optional[Dict[str, Any]] = None
        self.last_output: Optional[Dict[str, Any]] = None
        self.last_tick_ts: Optional[str] = None

        self.stats: Dict[str, int] = {"ticks": 0, "accepted": 0, "rejected": 0}
        self.reject_streak: int = 0

        self._planner = get_planner_client()
        self._logs: List[Dict[str, Any]] = []

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        task = self._task
        self._task = None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    def status(self) -> Dict[str, Any]:
        return {
            "on": self._running,
            "last_tick": self.last_tick_ts,
            "last_decision": (self.last_output or {}).get("decisions", [])[:3],
            "stats": dict(self.stats),
            "reject_streak": self.reject_streak,
        }

    def get_logs(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        return self._logs[offset : offset + limit]

    async def preview(self) -> Dict[str, Any]:
        ctx = await self._sense()
        out = self._think(ctx)
        ok = True
        err: Optional[str] = None
        try:
            validate_output(out)
        except Exception as e:
            ok = False
            err = str(e)
        res = {"input": ctx, "raw_output": out, "validation": {"ok": ok, "error": err}}
        self.last_input = ctx
        self.last_output = out
        return res

    async def _run(self) -> None:
        while self._running:
            try:
                ctx = await self._sense()
                out = self._think(ctx)
                try:
                    validated: PlannerOutput = validate_output(out)
                    self.stats["accepted"] += 1
                    self.reject_streak = 0
                except Exception as e:
                    self.stats["rejected"] += 1
                    self.reject_streak += 1
                    self._log("planner_invalid_json", {"error": str(e)})
                    await asyncio.sleep(self.tick_sec)
                    continue

                self._act(ctx, validated)
                self.last_input = ctx
                self.last_output = out
                self.last_tick_ts = _utcnow_iso()
                self.stats["ticks"] += 1
            except Exception as e:  # pragma: no cover
                self._log("autopilot_exception", {"error": str(e)})
            await asyncio.sleep(self.tick_sec)

    async def _sense(self) -> Dict[str, Any]:
        # Account + positions
        c = self.get_client()
        account: Dict[str, float] = {"equity": 0.0, "bp": 0.0, "pnl_today": 0.0}
        positions_raw: List[Dict[str, Any]] = []
        if c is not None and getattr(c, "connected", False):
            try:
                positions_raw = c.get_positions()
            except Exception:
                positions_raw = []

        # Normalize positions
        pos_norm: List[Dict[str, Any]] = []
        for p in positions_raw or []:
            sym = p.get("code") or p.get("stock_code") or p.get("symbol") or ""
            qty = float(p.get("qty") or p.get("qty_total") or p.get("qty_today") or 0.0)
            avg = float(p.get("cost_price") or p.get("avg_cost_price") or 0.0)
            if sym:
                pos_norm.append({"sym": sym, "qty": qty, "avg": avg})

        # Risk snapshot
        risk_cfg = self.risk_loader() or {}
        risk: Dict[str, Any] = {
            "max_positions": int(risk_cfg.get("max_open_positions") or 0),
            "max_risk_bps": 0,
            "max_day_dd_bps": 0,
            "per_symbol_max_bps": 0,
        }

        # Universe with indicators
        watchlist = os.getenv("AUTOPILOT_WATCHLIST", "US.AAPL,US.MSFT,US.TSLA").split(",")
        universe: List[Dict[str, Any]] = []
        for sym in [s.strip() for s in watchlist if s.strip()]:
            highs, lows, closes = _fetch_bars(sym, period="6mo", interval="1d")
            if not closes:
                universe.append(
                    {"sym": sym, "px": 0.0, "atr": 0.0, "rsi": 50, "ma50": 0.0, "ma200": 0.0, "trend": "flat"}
                )
                continue
            px = float(closes[-1])
            ma50 = ind.sma(closes, 50)
            ma200 = ind.sma(closes, 200)
            rsi_val = int(round(ind.rsi(closes, 14)))
            atr_val = ind.atr(highs, lows, closes, 14)
            trend = ind.trend_from_mas(ma50, ma200)
            universe.append(
                {"sym": sym, "px": px, "atr": atr_val, "rsi": rsi_val, "ma50": ma50, "ma200": ma200, "trend": trend}
            )

        ctx: Dict[str, Any] = {
            "timestamp": _utcnow_iso(),
            "mode": "auto",
            "account": account,
            "risk": risk,
            "positions": pos_norm,
            "universe": universe,
            "style_summary": "",
            "strategy_signals": [],
        }
        return ctx

    def _think(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        out_model = self._planner.plan(ctx)
        return out_model.dict()

    
def _act(self, ctx: Dict[str, Any], out: PlannerOutput) -> None:
    if out.decisions:
        # Summary entry
        self._log("planner_decisions", {"n": len(out.decisions)})
        # Row-level entries for Activity Log (Autopilot)
        for d in out.decisions:
            try:
                row = {
                    "ts": _utcnow_iso(),
                    "mode": "auto",
                    "action": getattr(d, "action", None),
                    "symbol": getattr(d, "sym", None),
                    "side": getattr(d, "side", None),
                    "qty": f"{getattr(d, 'size_type', '')}:{getattr(d, 'size_value', '')}",
                    "price": getattr(d, "limit_price", None) or "",
                    "reason": f"{getattr(d, 'rationale', '')} (conf={getattr(d, 'confidence', 0.0):.2f})",
                    "status": "planned",
                }
                self._logs.append(row)
            except Exception:
                # best-effort logging
                pass
    else:
        self._log("planner_idle", {"msg": "no decisions"})

    def _log(self, reason: str, extra: Optional[Dict[str, Any]] = None) -> None:
        entry = {"ts": _utcnow_iso(), "reason": reason, "extra": extra or {}}
        self._logs.append(entry)
        if _HAS_STORAGE:
            try:
                insert_action_log("autopilot", mode="auto", reason=reason, status="ok", extra=extra or {})
            except Exception:
                pass
