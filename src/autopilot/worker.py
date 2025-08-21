
# src/autopilot/worker.py
from __future__ import annotations
import asyncio, time
from typing import Any, Dict, Optional, List, Tuple
from datetime import datetime, timezone

try:
    from ..core.storage import insert_action_log  # type: ignore
    _HAS_STORAGE = True
except Exception:
    _HAS_STORAGE = False

from .planner_client import get_planner_client
from .schemas import PlannerInput, PlannerOutput, validate_output

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

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
        self.stats = {"ticks": 0, "accepted": 0, "rejected": 0}
        self.reject_streak = 0
        self._planner = get_planner_client()
        self._logs: List[Dict[str, Any]] = []

    async def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._running = False
        t = self._task
        self._task = None
        if t:
            t.cancel()
            try: await t
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

    def get_logs(self, limit=100, offset=0):
        return self._logs[offset:offset+limit]

    async def preview(self) -> Dict[str, Any]:
        ctx = await self._sense()
        out = self._think(ctx)
        valid = True
        err = None
        try:
            validate_output(out)
        except Exception as e:
            valid = False
            err = str(e)
        res = {"input": ctx, "raw_output": out, "validation": {"ok": valid, "error": err}}
        self.last_input = ctx
        self.last_output = out
        return res

    async def _run(self):
        while self._running:
            try:
                ctx = await self._sense()
                out = self._think(ctx)
                # validate
                validated = None
                try:
                    validated = validate_output(out)
                    self.stats["accepted"] += 1
                    self.reject_streak = 0
                except Exception as e:
                    self.stats["rejected"] += 1
                    self.reject_streak += 1
                    self._log("planner_invalid_json", {"error": str(e)})
                    await asyncio.sleep(self.tick_sec)
                    continue
                # act (stubbed)
                self._act(ctx, validated)
                self.last_input = ctx
                self.last_output = out
                self.last_tick_ts = _utcnow_iso()
                self.stats["ticks"] += 1
            except Exception as e:
                self._log("autopilot_exception", {"error": str(e)})
            await asyncio.sleep(self.tick_sec)

    async def _sense(self) -> Dict[str, Any]:
        c = self.get_client()
        account = {"equity": 0.0, "bp": 0.0, "pnl_today": 0.0}
        positions: List[Dict[str, Any]] = []
        try:
            if c is not None and getattr(c, "connected", False):
                try:
                    positions = c.get_positions()
                except Exception:
                    positions = []
        except Exception:
            pass
        # Risk from server-side loader
        risk_cfg = self.risk_loader() or {}
        risk = {
            "max_positions": int(risk_cfg.get("max_open_positions") or 0),
            "max_risk_bps": 0,
            "max_day_dd_bps": 0,
            "per_symbol_max_bps": 0,
        }
        # Normalize positions
        pos_norm = []
        for p in positions or []:
            sym = p.get("code") or p.get("stock_code") or p.get("symbol") or ""
            qty = float(p.get("qty") or p.get("qty_total") or p.get("qty_today") or 0.0)
            avg = float(p.get("cost_price") or p.get("avg_cost_price") or 0.0)
            if sym:
                pos_norm.append({"sym": sym, "qty": qty, "avg": avg})

        ctx = {
            "timestamp": _utcnow_iso(),
            "mode": "auto",
            "account": account,
            "risk": risk,
            "positions": pos_norm,
            "universe": [],  # v1 empty; fill later with indicators
            "style_summary": "",
            "strategy_signals": [],
        }
        return ctx

    def _think(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        out_model = self._planner.plan(ctx)
        return out_model.dict()

    def _act(self, ctx: Dict[str, Any], out: "PlannerOutput"):
        # Stub: no real orders. Log accepted decisions.
        if out.decisions:
            self._log("planner_decisions", {"n": len(out.decisions)})
        else:
            self._log("planner_idle", {"msg": "no decisions"})

    def _log(self, reason: str, extra: Dict[str, Any] | None = None):
        entry = {
            "ts": _utcnow_iso(),
            "reason": reason,
            "extra": extra or {},
        }
        self._logs.append(entry)
        if _HAS_STORAGE:
            try:
                insert_action_log("autopilot", mode="auto", reason=reason, status="ok", extra=extra or {})
            except Exception:
                pass
