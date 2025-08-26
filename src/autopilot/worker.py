# src/autopilot/worker.py (robust imports + guardrails + SIM Act)
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

# Optional durable action log
try:
    from core.storage import insert_action_log  # type: ignore
    _HAS_STORAGE = True
except Exception:  # pragma: no cover
    _HAS_STORAGE = False

# Planner client (support both module layouts)
try:
    from planner_client import get_planner_client  # type: ignore
except Exception:  # pragma: no cover
    from autopilot.planner_client import get_planner_client  # type: ignore

# Planner schemas (support both layouts)
try:
    from schemas import PlannerOutput, validate_output  # type: ignore
except Exception:  # pragma: no cover
    from autopilot.schemas import PlannerOutput, validate_output  # type: ignore

# Indicators (support both layouts)
try:
    import indicators as ind  # type: ignore
except Exception:  # pragma: no cover
    from autopilot import indicators as ind  # type: ignore

# Execution (absolute imports avoid relative-import issues)
try:
    from execution.base import ExecutionContext  # type: ignore
    from execution.types import OrderSpec, OrderSide, OrderType, TimeInForce  # type: ignore
except Exception:  # pragma: no cover
    ExecutionContext = None  # type: ignore
    OrderSpec = None  # type: ignore
    OrderSide = None  # type: ignore
    OrderType = None  # type: ignore
    TimeInForce = None  # type: ignore

# Guardrails
try:
    from risk.limits import enforce_order_limits  # type: ignore
except Exception:  # pragma: no cover
    def enforce_order_limits(**kwargs):  # type: ignore
        return None


REJECT_PAUSE_THRESHOLD = 2  # pause Autopilot when continuous rejects reach this


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fetch_bars(symbol: str, period: str = "6mo", interval: str = "1d") -> tuple[list[float], list[float], list[float]]:
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
    def __init__(self, get_client, risk_loader, get_execution=None):
        """
        get_client: () -> broker client
        risk_loader: () -> dict
        get_execution: Optional[() -> ExecutionService]  # for Act()
        """
        self.get_client = get_client
        self.risk_loader = risk_loader
        self._get_execution = get_execution or (lambda: None)

        self._task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._lock: asyncio.Lock = asyncio.Lock()
        self.tick_sec: int = 15

        self.last_input: Optional[Dict[str, Any]] = None
        self.last_output: Optional[Dict[str, Any]] = None
        self.last_tick_ts: Optional[str] = None

        self.stats: Dict[str, int] = {"ticks": 0, "accepted": 0, "rejected": 0}
        self.reject_streak: int = 0

        self._planner = get_planner_client()
        self._logs: List[Dict[str, Any]] = []

    async def start(self) -> None:
        async with self._lock:
            if self._running and self._task and not self._task.done():
                return
            self._running = True
            self.reject_streak = 0
            self._task = asyncio.create_task(self._run(), name="autopilot_worker")

    async def stop(self) -> None:
        async with self._lock:
            self._running = False
            task = self._task
            self._task = None
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:  # pragma: no cover
                self._log("autopilot_stop_exception", {"error": str(e)})

    def status(self) -> Dict[str, Any]:
        return {
            "on": self._running and self._task is not None and not self._task.done(),
            "last_tick": self.last_tick_ts,
            "last_decision": (self.last_output or {}).get("decisions", [])[:3] if isinstance(self.last_output, dict) else None,
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
                    if self.reject_streak >= REJECT_PAUSE_THRESHOLD:
                        await self._pause_due_to_rejects("planner_json")
                    self.last_tick_ts = _utcnow_iso()
                    await asyncio.sleep(self.tick_sec)
                    continue

                try:
                    self._act(ctx, validated)
                except Exception as e:  # pragma: no cover
                    self._log("act_exception", {"error": str(e)})

                self.last_input = ctx
                self.last_output = out
                self.last_tick_ts = _utcnow_iso()
                self.stats["ticks"] += 1
            except asyncio.CancelledError:
                break
            except Exception as e:  # pragma: no cover
                self._log("autopilot_exception", {"error": str(e)})
            await asyncio.sleep(self.tick_sec)

    async def _pause_due_to_rejects(self, reason: str) -> None:
        self._log("autopilot_paused", {"reason": reason, "reject_streak": self.reject_streak})
        await self.stop()

    async def _sense(self) -> Dict[str, Any]:
        c = self.get_client()
        account: Dict[str, float] = {"equity": 0.0, "bp": 0.0, "pnl_today": 0.0}
        positions_raw: List[Dict[str, Any]] = []

        # Also include SIM positions from the execution service (if available)
        try:
            exec_service = self._get_execution()
        except Exception:
            exec_service = None
        if exec_service is not None and hasattr(exec_service, "list_positions"):
            try:
                for sp in exec_service.list_positions() or []:
                    sym = str(sp.get("symbol") or sp.get("sym") or "")
                    qty = float(sp.get("qty") or 0.0)
                    avg = float(sp.get("avg_cost") or sp.get("avg") or 0.0)
                    if sym:
                        positions_raw.append({"symbol": sym, "qty": qty, "cost_price": avg})
            except Exception:
                pass

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
            "max_risk_bps": int(risk_cfg.get("per_trade_max_bps") or 0),
            "max_day_dd_bps": int(risk_cfg.get("max_day_drawdown_bps") or 0),
            "per_symbol_max_bps": int(risk_cfg.get("per_symbol_max_bps") or 0),
            "symbol_blocklist": list(risk_cfg.get("symbol_blocklist") or []),
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
            universe.append({"sym": sym, "px": px, "atr": atr_val, "rsi": rsi_val, "ma50": ma50, "ma200": ma200, "trend": trend})

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
        return out_model.dict() if hasattr(out_model, "dict") else out_model  # type: ignore

    # ---- helpers for Act ----
    @staticmethod
    def _last_price_map(ctx: Dict[str, Any]) -> Dict[str, float]:
        return {u["sym"]: float(u.get("px") or 0.0) for u in ctx.get("universe", [])}

    @staticmethod
    def _pos_map(ctx: Dict[str, Any]) -> Dict[str, float]:
        m: Dict[str, float] = {}
        for p in ctx.get("positions", []) or []:
            m[p["sym"]] = float(p.get("qty") or 0.0)
        return m

    @staticmethod
    def _qty_from_size(d, last_px: float, equity: float) -> int:
        size_type = getattr(d, "size_type", None) or (d.get("size_type") if isinstance(d, dict) else "shares")
        size_value = float(getattr(d, "size_value", 0.0) or (d.get("size_value") if isinstance(d, dict) else 0.0) or 0.0)
        if last_px <= 0:
            return 0
        if size_type == "shares":
            return max(0, int(size_value))
        if size_type == "notional":
            return max(0, int(size_value // last_px))
        if size_type == "risk_bps":
            notional = max(0.0, float(equity) * (size_value / 10000.0))
            return max(0, int(notional // last_px))
        return 0

    def _act(self, ctx: Dict[str, Any], out: PlannerOutput) -> None:
        try:
            exec_service = self._get_execution()
        except Exception:
            exec_service = None

        last_prices = self._last_price_map(ctx)
        pos = self._pos_map(ctx)
        equity = float((ctx.get("account") or {}).get("equity") or 0.0)
        client = self.get_client()

        decisions = list(getattr(out, "decisions", []) or [])
        if not decisions:
            self._log("planner_idle", {"msg": "no_decisions"})
            return

        self._log("planner_decisions", {"n": len(decisions)})

        for idx, d in enumerate(decisions):
            sym = getattr(d, "sym", None) or getattr(d, "symbol", None) or (d.get("sym") if isinstance(d, dict) else None) or (d.get("symbol") if isinstance(d, dict) else None)
            if not sym:
                self._logs.append({"ts": _utcnow_iso(), "status": "rejected", "reason": "missing_symbol"})
                continue

            side_field = getattr(d, "side", None) or (d.get("side") if isinstance(d, dict) else "buy") or "buy"
            action = getattr(d, "action", None) or (d.get("action") if isinstance(d, dict) else "open") or "open"

            if action == "close":
                cur_qty = float(pos.get(sym) or 0.0)
                if cur_qty == 0:
                    self._logs.append({"ts": _utcnow_iso(), "mode": "auto", "action": "close",
                                       "symbol": sym, "side": None, "qty": "", "price": "",
                                       "reason": "no_position_to_close", "status": "skipped"})
                    continue
                side = "sell" if cur_qty > 0 else "buy"
            else:
                side = side_field

            last_px = float(last_prices.get(sym) or 0.0)
            est_qty = self._qty_from_size(d, last_px, equity)
            order_type = "MARKET" if (getattr(d, "entry", None) or (d.get("entry") if isinstance(d, dict) else "market")) == "market" else "LIMIT"
            limit_price = getattr(d, "limit_price", None) or (d.get("limit_price") if isinstance(d, dict) else None)

            # Guardrails
            try:
                enforce_order_limits(
                    client=client,
                    symbol=sym,
                    qty=float(est_qty),
                    side="BUY" if side == "buy" else "SELL",
                    order_type=order_type,
                    price=limit_price,
                )
            except ValueError as e:
                self.reject_streak += 1
                self._logs.append({"ts": _utcnow_iso(), "mode": "auto", "action": action,
                                   "symbol": sym, "side": side,
                                   "qty": f"{getattr(d,'size_type','shares') if not isinstance(d, dict) else d.get('size_type','shares')}:{getattr(d,'size_value',0) if not isinstance(d, dict) else d.get('size_value',0)}",
                                   "price": limit_price or "", "reason": f"guardrail:{str(e)}", "status": "rejected"})
                if self.reject_streak >= REJECT_PAUSE_THRESHOLD:
                    asyncio.create_task(self._pause_due_to_rejects("guardrails"))
                if _HAS_STORAGE:
                    try:
                        insert_action_log("autopilot_act", mode="auto",
                                          symbol=sym, side=side.upper(), qty=est_qty, price=limit_price,
                                          reason="guardrail", status="blocked", extra={"msg": str(e)})
                    except Exception:
                        pass
                continue

            if exec_service is None or OrderSpec is None:
                # Plan only (no execution service wired)
                self._logs.append({"ts": _utcnow_iso(), "mode": "auto", "action": action,
                                   "symbol": sym, "side": side,
                                   "qty": f"{getattr(d,'size_type','shares') if not isinstance(d, dict) else d.get('size_type','shares')}:{getattr(d,'size_value',0) if not isinstance(d, dict) else d.get('size_value',0)}",
                                   "price": limit_price or "", "reason": "no_execution_service", "status": "planned"})
                continue

            tif_val = getattr(d, "time_in_force", None) or (d.get("time_in_force") if isinstance(d, dict) else "day") or "day"
            spec = OrderSpec(
                symbol=sym,
                side=OrderSide.buy if side == "buy" else OrderSide.sell,
                order_type=OrderType.market if order_type == "MARKET" else OrderType.limit,
                limit_price=limit_price,
                size_type=str(getattr(d, "size_type", None) or (d.get("size_type") if isinstance(d, dict) else "shares")),
                size_value=float(getattr(d, "size_value", 0.0) or (d.get("size_value") if isinstance(d, dict) else 0.0) or 0.0),
                tif=TimeInForce.day if tif_val == "day" else TimeInForce.gtc,
                decision_id=idx,
            )

            ctx_exec = ExecutionContext(
                account_id=getattr(self.get_client(), "account_id", None) or "SIM-LOCAL",
                last_prices=self._last_price_map(ctx),
                equity=equity,
                simulate=True,
            )
            order = exec_service.place_order(spec, ctx_exec)

            self._logs.append({"ts": _utcnow_iso(), "mode": "auto", "action": action,
                               "symbol": sym, "side": side,
                               "qty": f"{spec.size_type}:{spec.size_value}",
                               "price": limit_price or "", "reason": f"order:{order.order_id}",
                               "status": str(order.status.value)})
            if _HAS_STORAGE:
                try:
                    insert_action_log("autopilot_act", mode="auto",
                                      symbol=sym, side=side.upper(), qty=est_qty, price=limit_price,
                                      reason="order", status=str(order.status.value),
                                      extra={"order_id": order.order_id})
                except Exception:
                    pass

        # Try fill any resting limits
        try:
            if exec_service is not None:
                exec_service.try_fill_resting(self._last_price_map(ctx))
        except Exception:
            pass

    def _log(self, reason: str, extra: Optional[Dict[str, Any]] = None) -> None:
        entry = {"ts": _utcnow_iso(), "reason": reason, "extra": extra or {}}
        self._logs.append(entry)
        if _HAS_STORAGE:
            try:
                insert_action_log("autopilot", mode="auto", reason=reason, status="ok", extra=extra or {})
            except Exception:
                pass
