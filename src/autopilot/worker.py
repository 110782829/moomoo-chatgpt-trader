# src/autopilot/worker.py (robust imports + guardrails + SIM Act)
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
import time as _time
from typing import Any, Dict, List, Optional

# Optional durable action log + settings + fills
try:
    from core.storage import insert_action_log, get_setting, record_fill  # type: ignore
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

# Optional shared signals
try:
    from autopilot.signals import signals_for_series  # type: ignore
except Exception:  # pragma: no cover
    def signals_for_series(*a, **k):  # type: ignore
        return []

# Guardrails
try:
    from risk.limits import enforce_order_limits  # type: ignore
except Exception:  # pragma: no cover
    def enforce_order_limits(**kwargs):  # type: ignore
        return None


REJECT_PAUSE_THRESHOLD = 2  # pause Autopilot when continuous rejects reach this


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _yf_period(interval: str, n: int) -> str:
    # cover at least n bars
    interval = interval.lower()
    if interval.endswith("m"):
        per_day = {"1m": 390, "5m": 78, "15m": 26, "30m": 13, "60m": 6}
        bpd = per_day.get(interval, 390)
        days = (n + bpd - 1) // bpd
        cap = 7 if interval == "1m" else 60
        days = max(1, min(days, cap))
        return f"{days}d"
    if n <= 60:
        return f"{n}d"
    return "2y" if n <= 365 * 2 else "max"


def _fetch_bars(symbol: str, n: int = 180, interval: str = "1d") -> tuple[list[float], list[float], list[float]]:
    if yf is None:
        return [], [], []
    try:
        import contextlib, io as _io
        yf_sym = symbol.replace("US.", "")
        period = _yf_period(interval, n)
        # Suppress noisy stderr from yfinance (e.g., delisted tickers)
        with contextlib.redirect_stderr(_io.StringIO()):
            try:
                df = yf.download(yf_sym, period=period, interval=interval, auto_adjust=True, progress=False, raise_errors=False)  # type: ignore[call-arg]
            except TypeError:
                df = yf.download(yf_sym, period=period, interval=interval, auto_adjust=True, progress=False)
        if df is None or df.empty:
            return [], [], []
        import pandas as pd
        if isinstance(df.columns, pd.MultiIndex):  # flatten ticker columns
            df.columns = [c[0] for c in df.columns]
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
        # Adaptive re-weight cadence (sec)
        try:
            self._retune_sec = int(os.getenv("AUTOPILOT_REWEIGHT_SEC", "1800") or "1800")
        except Exception:
            self._retune_sec = 1800
        self._last_retune: float = 0.0

        self.last_input: Optional[Dict[str, Any]] = None
        self.last_output: Optional[Dict[str, Any]] = None
        self.last_tick_ts: Optional[str] = None

        self.stats: Dict[str, int] = {"ticks": 0, "accepted": 0, "rejected": 0}
        self.reject_streak: int = 0

        self._planner = get_planner_client()
        self._logs: List[Dict[str, Any]] = []

        # runtime stats helpers
        self._started_ts: float | None = None
        self._think_avg_ms: float = 0.0
        self._think_samples: int = 0
        self._decisions_day: str | None = None
        self.stats.setdefault("avg_think_ms", 0)
        self.stats.setdefault("decisions_today", 0)
        # Idempotence map: decision key -> expiry_ts
        self._live_decisions: Dict[str, float] = {}
        # Light memory of recent decisions per symbol for the planner
        self._decision_history: Dict[str, List[Dict[str, Any]]] = {}

        # Periodic broker deal sync (to keep local mirror authoritative)
        self.deal_sync_sec: int = int(os.getenv("AUTOPILOT_DEALS_SYNC_SEC", "180") or "180")
        self._last_deal_sync_ts: float = 0.0

        # Throttle low-confidence planned logs per symbol
        self._low_conf_log_ts: Dict[str, float] = {}
        # Last planner stages for UI diffs
        self._last_proposed: List[Dict[str, Any]] = []
        self._last_evaluated: List[Dict[str, Any]] = []
        # Breadth AD-line (cumulative adv-decl)
        self._ad_line: float = 0.0

    async def start(self) -> None:
        async with self._lock:
            if self._running and self._task and not self._task.done():
                return
            self._running = True
            self.reject_streak = 0
            self._started_ts = _time.time()
            # daily rolling counter
            self._decisions_day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
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
        # compute friendly uptime
        def _fmt_uptime(sec: float) -> str:
            if sec <= 0:
                return "0s"
            m = int(sec // 60)
            h = m // 60
            if h > 0:
                return f"{h}h {m%60}m"
            s = int(sec % 60)
            return f"{m}m {s}s" if m > 0 else f"{s}s"

        up = 0.0
        if self._started_ts:
            up = max(0.0, _time.time() - self._started_ts)
        stats = dict(self.stats)
        stats["uptime"] = _fmt_uptime(up)
        stats["avg_think_ms"] = int(round(self._think_avg_ms))
        return {
            "on": self._running and self._task is not None and not self._task.done(),
            "last_tick": self.last_tick_ts,
            "last_decision": (self.last_output or {}).get("decisions", [])[:3] if isinstance(self.last_output, dict) else None,
            "stats": stats,
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
                t0 = _time.perf_counter()
                out = self._think(ctx)
                dt_ms = ( _time.perf_counter() - t0 ) * 1000.0
                # rolling average (EMA-ish)
                self._think_samples += 1
                alpha = 0.2 if self._think_samples > 1 else 1.0
                self._think_avg_ms = (1.0 - alpha) * self._think_avg_ms + alpha * dt_ms

                try:
                    validated: PlannerOutput = validate_output(out)
                    self.stats["accepted"] += 1
                    self.reject_streak = 0
                    # decisions/day counter
                    try:
                        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        if self._decisions_day != today:
                            self._decisions_day = today
                            self.stats["decisions_today"] = 0
                        n = len(getattr(validated, "decisions", []) or [])
                        self.stats["decisions_today"] = int(self.stats.get("decisions_today", 0) or 0) + int(n)
                    except Exception:
                        pass
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
                    # --- transparency: log planner_proposed ---
                    try:
                        proposed = [
                            (d.dict() if hasattr(d, 'dict') else (d if isinstance(d, dict) else {}))
                            for d in (getattr(validated, 'decisions', []) or [])
                        ]
                    except Exception:
                        proposed = []
                    # store for diff endpoint
                    try:
                        self._last_proposed = list(proposed)
                    except Exception:
                        pass
                    pol = self._derive_policy((ctx.get('style_summary') or ''), (ctx.get('prefs') or {}))
                    self._log("planner_proposed", {"n": len(proposed), "policy": pol, "decisions": proposed[:6], "syms": [d.get('sym') for d in proposed]})
                    if _HAS_STORAGE:
                        try:
                            insert_action_log("planner_proposed", mode="auto", reason="ok", status="ok", extra={"n": len(proposed), "policy": pol, "decisions": proposed[:6]})
                        except Exception:
                            pass

                    # --- validator: enforce policy ---
                    pos_map_now = self._pos_map(ctx)
                    vres = self._validate_and_transform(proposed, pol, pos_map_now)
                    final_list = vres.get("decisions") or []
                    self._log("validator_result", {"n": len(final_list), "transformed": vres.get("transformed",0), "dropped": vres.get("dropped",0)})
                    if _HAS_STORAGE:
                        try:
                            insert_action_log("validator_result", mode="auto", reason="ok", status="ok", extra={"n": len(final_list), "transformed": vres.get("transformed",0), "dropped": vres.get("dropped",0)})
                        except Exception:
                            pass

                    # --- evaluator: score and gate low-quality decisions ---
                    eres = self._evaluate(final_list, ctx)
                    eval_list = eres.get("decisions") or []
                    try:
                        self._last_evaluated = list(eval_list)
                    except Exception:
                        pass
                    self._log("evaluator_result", {
                        "n": len(eval_list),
                        "dropped": eres.get("dropped",0),
                        "threshold": eres.get("threshold"),
                        "scores": eres.get("scores",[])[:6],
                        "kept_syms": [d.get('sym') for d in eval_list],
                    })
                    if _HAS_STORAGE:
                        try:
                            insert_action_log("evaluator_result", mode="auto", reason="ok", status="ok", extra={"n": len(eval_list), "dropped": eres.get("dropped",0), "threshold": eres.get("threshold"), "kept_syms": [d.get('sym') for d in eval_list]})
                        except Exception:
                            pass

                    # Rebuild a PlannerOutput-like object for _act
                    class _TmpOut:
                        def __init__(self, decisions): self.decisions = decisions
                    tmp = _TmpOut(eval_list)
                    # small evaluator-based feedback to signal weights
                    try:
                        self._apply_eval_feedback(ctx, eval_list, eres.get("scores") or [])
                    except Exception:
                        pass
                    self._act(ctx, tmp)  # type: ignore[arg-type]
                except Exception as e:  # pragma: no cover
                    self._log("act_exception", {"error": str(e)})

                # Opportunistic broker deal sync (paper/live): keep local storage updated
                try:
                    await self._maybe_sync_deals()
                except Exception:
                    pass

                self.last_input = ctx
                self.last_output = out
                self.last_tick_ts = _utcnow_iso()
                self.stats["ticks"] += 1
            except asyncio.CancelledError:
                break
            except Exception as e:  # pragma: no cover
                self._log("autopilot_exception", {"error": str(e)})
            await asyncio.sleep(self.tick_sec)
            # periodic adaptive signal re-weighting
            try:
                import time as _time
                now = _time.time()
                if self._retune_sec > 0 and (now - self._last_retune) >= self._retune_sec:
                    await self._adaptive_reweight()
                    self._last_retune = now
            except Exception:
                pass

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
                # best-effort account snapshot
                info = c.get_account_assets()  # type: ignore[attr-defined]
                account = {
                    "equity": float(info.get("equity") or 0.0),
                    "bp": float(info.get("bp") or info.get("buying_power") or 0.0),
                    "pnl_today": float(info.get("pnl_day") or info.get("pnl_today") or 0.0),
                }
            except Exception:
                account = {"equity": 0.0, "bp": 0.0, "pnl_today": 0.0}
            try:
                broker_positions = c.get_positions() or []
                if broker_positions:
                    positions_raw = broker_positions
            except Exception:
                pass

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

        # Data settings
        try:
            ktype_val = str(get_setting("autopilot.ktype") or "") if _HAS_STORAGE else ""
        except Exception:
            ktype_val = ""
        if not ktype_val:
            ktype_val = os.getenv("AUTOPILOT_KTYPE", "K_DAY")
        try:
            bars_ttl = int(get_setting("autopilot.bars_ttl_sec") or 0) if _HAS_STORAGE else 0
        except Exception:
            bars_ttl = 0
        if bars_ttl <= 0:
            bars_ttl = int(os.getenv("AUTOPILOT_BARS_TTL_SEC", "60") or "60")

        # Universe selection: discovery (preferred) or watchlist fallback
        # Discovery can be toggled via settings 'autopilot.discovery_enabled' or env AUTOPILOT_DISCOVERY=1
        discovery_enabled = False
        if _HAS_STORAGE:
            try:
                raw = get_setting("autopilot.discovery_enabled")  # type: ignore[name-defined]
                if raw:
                    discovery_enabled = str(raw).strip().lower() not in ("0","false","no")
            except Exception:
                pass
        if not discovery_enabled:
            discovery_enabled = os.getenv("AUTOPILOT_DISCOVERY", "1").strip() not in ("0","false","no")

        watchlist: List[str] = []
        discovery_only = False
        if _HAS_STORAGE:
            try:
                raw = get_setting("autopilot.discovery_only")  # type: ignore[name-defined]
                if raw is not None:
                    discovery_only = str(raw).strip().lower() not in ("0","false","no")
            except Exception:
                pass
        if os.getenv("AUTOPILOT_DISCOVERY_ONLY", None) is not None:
            discovery_only = os.getenv("AUTOPILOT_DISCOVERY_ONLY", "0").strip().lower() not in ("0","false","no")
        if discovery_enabled:
            try:
                from autopilot.discovery import discover_symbols  # type: ignore
                discovered = discover_symbols(c, limit=int(os.getenv("AUTOPILOT_TOP_N", "8") or "8"), ktype=ktype_val) if c else []
                if discovered:
                    watchlist = discovered
            except Exception:
                watchlist = []
        # If discovery-only is ON but we have no broker client or we discovered nothing,
        # allow fallback to a static watchlist so Autopilot can still run in SIM/offline.
        try:
            if discovery_only and (c is None or not getattr(c, "connected", False)):
                discovery_only = False
            if discovery_only and not watchlist:
                discovery_only = False
        except Exception:
            pass

        # Style allowlist (Natural Language) filter
        allowlist: List[str] = []
        allow_enabled = False
        if _HAS_STORAGE:
            try:
                raw = get_setting("autopilot.style_symbols_enabled")  # type: ignore[name-defined]
                if raw is not None:
                    allow_enabled = str(raw).strip().lower() not in ("0","false","no")
            except Exception:
                allow_enabled = False
            try:
                if allow_enabled:
                    import json as _json
                    raw = get_setting("autopilot.style_symbols")  # type: ignore[name-defined]
                    if raw:
                        v = _json.loads(raw)
                        if isinstance(v, list):
                            allowlist = [str(s).strip() for s in v if s]
            except Exception:
                allowlist = []
        if allow_enabled and allowlist:
            wl0 = list(watchlist)
            watchlist = [s for s in watchlist if s in set(allowlist)]
            if wl0 and not watchlist:
                self._log("style_allowlist_filtered_all", {"allow": allowlist[:10]})

        if not watchlist and not discovery_only:
            # Fallback to settings/env watchlist
            watchlist_setting: List[str] = []
            if _HAS_STORAGE:
                try:
                    raw = get_setting("autopilot.watchlist")  # type: ignore[name-defined]
                    if raw:
                        import json as _json
                        v = _json.loads(raw)
                        if isinstance(v, list):
                            watchlist_setting = [str(s) for s in v]
                except Exception:
                    pass
            watchlist_env = os.getenv("AUTOPILOT_WATCHLIST", "US.AAPL,US.MSFT,US.TSLA").split(",")
            watchlist = watchlist_setting or watchlist_env
        # final guard
        if not watchlist and discovery_only:
            # If completely empty in discovery-only mode, log and continue safely (no universe)
            self._log("discovery_empty", {"mode": "discovery_only"})

        # Universe with indicators (prefer unified market data when available)
        universe: List[Dict[str, Any]] = []
        # feature cache per symbol to avoid thrashing bars fetches
        import time as _time
        now_ts = float(_time.time())
        if not hasattr(self, "_feat_cache"):
            self._feat_cache = {}
            self._feat_cache_ts = {}
        # Build indicators per symbol
        for sym in [s.strip() for s in watchlist if s.strip()]:
            highs: List[float] = []
            lows: List[float] = []
            closes: List[float] = []
            volumes: List[float] = []
            reason = ""  # reason for missing bars
            # cache by sym and ttl
            if sym in getattr(self, "_feat_cache_ts", {}) and (now_ts - self._feat_cache_ts.get(sym, 0.0) < bars_ttl):
                feat = self._feat_cache.get(sym, {})
                if feat:
                    universe.append(dict(feat))
                    continue
            source = ""
            try:
                from core.market_data import get_bars_safely, _data_source  # type: ignore
                source = _data_source()
                bars, source = get_bars_safely(c, sym, ktype_val, 220)
                for b in bars:
                    h = b.get("high", b.get("High", 0.0))
                    l = b.get("low", b.get("Low", 0.0))
                    cl = b.get("close", b.get("Close", 0.0))
                    vv = b.get("volume", b.get("Volume", 0.0))
                    try:
                        highs.append(float(h or 0.0))
                        lows.append(float(l or 0.0))
                        closes.append(float(cl or 0.0))
                        volumes.append(float(vv or 0.0))
                    except Exception:
                        continue
                if not closes:
                    reason = f"{source} returned no data"
            except Exception as e:
                # include original error for clarity
                reason = f"{source or 'data source'} fetch failed: {e}"

            if not closes:
                entry = {
                    "sym": sym, "px": 0.0, "atr": 0.0, "rsi": 50, "ma50": 0.0, "ma200": 0.0, "trend": "flat",
                }
                if reason:
                    entry["bars_unavailable"] = reason
                universe.append(entry)
                continue

            px = float(closes[-1])
            ma50 = ind.sma(closes, 50)
            ma200 = ind.sma(closes, 200)
            rsi_val = int(round(ind.rsi(closes, 14)))
            atr_val = ind.atr(highs, lows, closes, 14)
            trend = ind.trend_from_mas(ma50, ma200)
            # extra features for ranking
            prev_close = float(closes[-2]) if len(closes) >= 2 else px
            change_1d_pct = ((px - prev_close) / prev_close * 100.0) if prev_close > 0 else 0.0
            atr_pct = (atr_val / px * 100.0) if px > 0 else 0.0
            dist_ma50_pct = ((px - ma50) / ma50 * 100.0) if ma50 > 0 else 0.0
            dist_ma200_pct = ((px - ma200) / ma200 * 100.0) if ma200 > 0 else 0.0
            # simple percentile over available window
            hi = max(closes) if closes else px
            lo = min(closes) if closes else px
            pct_rank_52w = ((px - lo) / (hi - lo) * 100.0) if hi > lo else 50.0
            # returns & liquidity proxies
            ret_20d_pct = 0.0
            try:
                if len(closes) >= 21 and closes[-21] > 0:
                    ret_20d_pct = (closes[-1] / closes[-21] - 1.0) * 100.0
            except Exception:
                ret_20d_pct = 0.0
            adv_usd_20 = None
            try:
                if len(volumes) >= 20:
                    c20 = sum(closes[-20:]) / 20.0
                    v20 = sum(volumes[-20:]) / 20.0
                    adv_usd_20 = c20 * v20
            except Exception:
                adv_usd_20 = None

            # label volatility regime from ATR%
            vol_regime = "low"
            try:
                if atr_pct >= 5:
                    vol_regime = "high"
                elif atr_pct >= 2:
                    vol_regime = "med"
            except Exception:
                vol_regime = "low"

            # liquidity/marketability: median intraday range % as spread proxy (20 bars)
            hl_spread_pct20 = None
            try:
                import statistics as _stat
                if len(highs) >= 20 and len(closes) >= 20:
                    vals = []
                    for i in range(-20, 0):
                        cl = float(closes[i] or 0.0)
                        if cl <= 0: continue
                        vals.append(max(0.0, (float(highs[i]) - float(lows[i])) / cl * 100.0))
                    hl_spread_pct20 = _stat.median(vals) if vals else None
            except Exception:
                hl_spread_pct20 = None

            # basic volume profile features
            vwap_20 = None
            try:
                if len(volumes) >= 20:
                    num = sum(float(closes[i]) * float(volumes[i]) for i in range(-20, 0))
                    den = sum(float(volumes[i]) for i in range(-20, 0))
                    vwap_20 = (num / den) if den > 0 else None
            except Exception:
                vwap_20 = None
            poc_price_100 = None
            va_low_100 = None
            va_high_100 = None
            poc_proximity_pct = None
            try:
                if len(closes) >= 100 and len(volumes) >= 100:
                    lo_p = min(closes[-100:]); hi_p = max(closes[-100:])
                    bins = max(5, min(20, int(len(closes[-100:]) / 5)))
                    width = (hi_p - lo_p) / bins if hi_p > lo_p else 0
                    if width > 0:
                        buckets = [0.0] * bins
                        for i in range(-100, 0):
                            p = float(closes[i]); v = float(volumes[i])
                            idx = int(min(bins-1, max(0, int((p - lo_p) / width))))
                            buckets[idx] += v
                        idx_max = int(max(range(bins), key=lambda i: buckets[i]))
                        poc_price_100 = lo_p + (idx_max + 0.5) * width
                        # Value Area (approx 70% of volume) around POC
                        total_vol = sum(buckets)
                        target = total_vol * 0.7 if total_vol > 0 else 0.0
                        acc = buckets[idx_max]
                        L = idx_max; R = idx_max
                        while acc < target and (L > 0 or R < bins - 1):
                            left_val = buckets[L-1] if L > 0 else -1.0
                            right_val = buckets[R+1] if R < bins - 1 else -1.0
                            if right_val >= left_val:
                                R = min(bins - 1, R + 1)
                                acc += max(0.0, right_val)
                            else:
                                L = max(0, L - 1)
                                acc += max(0.0, left_val)
                        va_low_100 = lo_p + (L + 0.0) * width
                        va_high_100 = lo_p + (R + 1.0) * width
                        # POC proximity (% distance from last price)
                        if poc_price_100 and px > 0:
                            poc_proximity_pct = abs(px - poc_price_100) / poc_price_100 * 100.0
            except Exception:
                poc_price_100 = None

            feat = {
                "sym": sym, "px": px, "atr": atr_val, "rsi": rsi_val,
                "ma50": ma50, "ma200": ma200, "trend": trend,
                "atr_pct": atr_pct, "dist_ma50_pct": dist_ma50_pct, "dist_ma200_pct": dist_ma200_pct,
                "change_1d_pct": change_1d_pct, "pct_rank_52w": pct_rank_52w,
                "ret_20d_pct": ret_20d_pct, "adv_usd_20": adv_usd_20,
                "vol_regime": vol_regime,
                "vwap_20": vwap_20,
                "poc_price_100": poc_price_100,
                "value_area_low_100": va_low_100,
                "value_area_high_100": va_high_100,
                "poc_proximity_pct": poc_proximity_pct,
                "hl_spread_pct20": hl_spread_pct20,
                # carry series for downstream signal generators (kept small ~220)
                "_highs": list(highs), "_lows": list(lows), "_closes": list(closes),
                "_vols": list(volumes),
            }
            universe.append(feat)
            # update cache
            try:
                self._feat_cache[sym] = feat
                self._feat_cache_ts[sym] = now_ts
            except Exception:
                pass

        # Build simple strategy signals (compact, short TTL)
        signals: List[Dict[str, Any]] = []
        for u in universe:
            s = u["sym"]
            ma50 = float(u.get("ma50") or 0.0)
            ma200 = float(u.get("ma200") or 0.0)
            rsi_val = int(u.get("rsi") or 50)
            if ma50 > 0 and ma200 > 0:
                skew = (ma50 / ma200) - 1.0
                if skew > 0.002:
                    signals.append({
                        "strategy": "ma_trend",
                        "sym": s,
                        "signal": "long",
                        "strength": min(1.0, max(0.1, abs(skew) * 50)),
                        "ttl_sec": 180,
                        "metadata": {"ma_skew": skew},
                    })
                elif skew < -0.002:
                    signals.append({
                        "strategy": "ma_trend",
                        "sym": s,
                        "signal": "short",
                        "strength": min(1.0, max(0.1, abs(skew) * 50)),
                        "ttl_sec": 180,
                        "metadata": {"ma_skew": skew},
                    })
            # RSI extremes
            if rsi_val <= 30:
                signals.append({
                    "strategy": "rsi_extreme",
                    "sym": s,
                    "signal": "long",
                    "strength": min(1.0, max(0.2, (30 - rsi_val) / 20.0)),
                    "ttl_sec": 180,
                    "metadata": {"rsi": rsi_val},
                })
            elif rsi_val >= 70:
                signals.append({
                    "strategy": "rsi_extreme",
                    "sym": s,
                    "signal": "short",
                    "strength": min(1.0, max(0.2, (rsi_val - 70) / 20.0)),
                    "ttl_sec": 180,
                    "metadata": {"rsi": rsi_val},
                })

        # News (cached via settings); can be disabled via settings/env
        news_enabled = True
        if _HAS_STORAGE:
            try:
                raw = get_setting("autopilot.use_news")  # type: ignore[name-defined]
                if raw is not None:
                    news_enabled = str(raw).strip().lower() not in ("0","false","no")
            except Exception:
                pass
        if os.getenv("AUTOPILOT_USE_NEWS", None) is not None:
            news_enabled = os.getenv("AUTOPILOT_USE_NEWS", "1").strip().lower() not in ("0","false","no")

        news_items: List[Dict[str, Any]] = []
        if news_enabled:
            try:
                from autopilot.news import get_news_bulk  # type: ignore
                ttl_sec = int(os.getenv("AUTOPILOT_NEWS_TTL_SEC", "1800") or "1800")
                news_items = get_news_bulk([u["sym"] for u in universe], ttl_sec=ttl_sec, max_items=2, cap=6)
            except Exception:
                news_items = []

        # Load style summary and preferences from settings (optional)
        style_summary: str = ""
        prefs: Dict[str, Any] = {}
        if _HAS_STORAGE:
            try:
                raw = get_setting("autopilot.style_summary")  # type: ignore[name-defined]
                if raw:
                    style_summary = str(raw)
            except Exception:
                pass
            try:
                raw = get_setting("autopilot.prefs")  # type: ignore[name-defined]
                if raw:
                    import json as _json
                    v = _json.loads(raw)
                    if isinstance(v, dict):
                        prefs = v
            except Exception:
                pass

        # Signals settings (enabled + weights)
        signals_enabled = True
        signals_enabled_map: Dict[str, bool] = {}
        signals_weights: Dict[str, float] = {}
        if _HAS_STORAGE:
            try:
                raw = get_setting("autopilot.signals.enabled")  # type: ignore[name-defined]
                if raw is not None:
                    signals_enabled = str(raw).strip().lower() not in ("0","false","no")
            except Exception:
                pass
            try:
                import json as _json
                raw = get_setting("autopilot.signals.strategies")  # type: ignore[name-defined]
                if raw:
                    m = _json.loads(raw)
                    if isinstance(m, dict):
                        signals_enabled_map = {str(k): bool(v) for k, v in m.items()}
            except Exception:
                pass
            try:
                import json as _json
                raw = get_setting("autopilot.signals.weights")  # type: ignore[name-defined]
                if raw:
                    m = _json.loads(raw)
                    if isinstance(m, dict):
                        signals_weights = {str(k): float(v) for k, v in m.items()}
            except Exception:
                pass

        # Rank symbols to trim universe for GPT (token budget)
        # Build per-symbol signal strength and news tone maps
        sig_strength: Dict[str, float] = {}
        for s in signals:
            sym = str(s.get("sym") or "")
            if not sym:
                continue
            try:
                sig_strength[sym] = sig_strength.get(sym, 0.0) + float(s.get("strength") or 0.0)
            except Exception:
                pass

        news_tone: Dict[str, str] = {str(n.get("sym")): str(n.get("tone")) for n in news_items if n.get("sym")}

        def _score(u: Dict[str, Any]) -> float:
            s = 0.0
            try:
                s += min(10.0, abs(float(u.get("dist_ma50_pct") or 0.0))) * 0.6
                s += min(10.0, abs(float(u.get("dist_ma200_pct") or 0.0))) * 0.4
                s += min(8.0, abs(float(u.get("atr_pct") or 0.0))) * 0.4
                s += min(10.0, abs((float(u.get("rsi") or 50) - 50.0) / 5.0)) * 0.5
                s += min(10.0, abs(float(u.get("change_1d_pct") or 0.0))) * 0.2
            except Exception:
                pass
            sym = str(u.get("sym") or "")
            if sym:
                s += (sig_strength.get(sym, 0.0) or 0.0) * 5.0
                tn = news_tone.get(sym, "neutral")
                if tn == "bullish" and u.get("trend") == "up":
                    s += 2.0
                if tn == "bearish" and u.get("trend") == "down":
                    s += 2.0
            return s

        for u in universe:
            try:
                u["interest"] = round(_score(u), 3)
            except Exception:
                u["interest"] = 0.0

        # Planner configuration (min_confidence, top_n) from settings/env
        min_conf: float = 0.6
        try:
            if _HAS_STORAGE:
                raw = get_setting("autopilot.min_confidence")  # type: ignore[name-defined]
                if raw is not None:
                    min_conf = float(raw)
        except Exception:
            pass
        strict_prefs = False
        try:
            if _HAS_STORAGE:
                raw = get_setting("autopilot.strict_prefs")  # type: ignore[name-defined]
                if raw is not None:
                    strict_prefs = str(raw).strip().lower() not in ("0","false","no")
        except Exception:
            strict_prefs = False
        try:
            top_n_setting = None
            if _HAS_STORAGE:
                top_n_setting = get_setting("autopilot.top_n")  # type: ignore[name-defined]
            top_n = int(top_n_setting) if top_n_setting is not None else int(os.getenv("AUTOPILOT_TOP_N", "8") or "8")
        except Exception:
            top_n = int(os.getenv("AUTOPILOT_TOP_N", "8") or "8")
        universe_sorted = sorted(universe, key=lambda x: float(x.get("interest") or 0.0), reverse=True)
        for idx, u in enumerate(universe_sorted):
            u["rank"] = idx + 1
            # Suggested stop/take based on prefs (if set)
            try:
                sug: Dict[str, Any] = {}
                if isinstance(prefs, dict):
                    if float(prefs.get("stop_loss_pct") or 0) > 0:
                        sug["stop_pct"] = float(prefs.get("stop_loss_pct")) * 100.0
                    if float(prefs.get("take_profit_pct") or 0) > 0:
                        sug["take_pct"] = float(prefs.get("take_profit_pct")) * 100.0
                    mm = float(prefs.get("measured_move_atr_mult") or 0)
                    if mm > 0:
                        sug["take_atr_mult"] = mm
                if u.get("atr") and u.get("px"):
                    if "take_atr_mult" in sug:
                        pass
                    elif float(prefs.get("measured_move_atr_mult") or 0) > 0:
                        sug["take_atr_mult"] = float(prefs.get("measured_move_atr_mult"))
                u["suggested"] = sug
            except Exception:
                u["suggested"] = {}

        # --- augment signals from shared module (advice only) ---
        if signals_enabled:
            for u in universe:
                try:
                    sym = str(u.get("sym") or "")
                    if not sym:
                        continue
                    # obtain series if available
                    highs: List[float] = u.get("_highs") if isinstance(u.get("_highs"), list) else []  # type: ignore
                    lows: List[float] = u.get("_lows") if isinstance(u.get("_lows"), list) else []   # type: ignore
                    closes: List[float] = u.get("_closes") if isinstance(u.get("_closes"), list) else []  # type: ignore
                    # Skip if series missing
                    if not closes:
                        continue
                    extra = signals_for_series(sym, highs, lows, closes) or []
                    # filter by per-strategy enable flags
                    if signals_enabled_map:
                        extra = [e for e in extra if signals_enabled_map.get(str(e.get("strategy")), True)]
                    # apply weights
                    for e in extra:
                        strat = str(e.get("strategy") or "")
                        w = float(signals_weights.get(strat, 1.0))
                        try:
                            e["strength"] = max(0.0, min(1.0, float(e.get("strength") or 0.0) * w))
                        except Exception:
                            pass
                    signals.extend(extra)
                except Exception:
                    continue

        # recompute aggregate strengths and net directional strength after augmentation
        sig_strength: Dict[str, float] = {}
        sig_dir: Dict[str, float] = {}
        for s in signals:
            sym = str(s.get("sym") or "")
            if not sym:
                continue
            try:
                val = float(s.get("strength") or 0.0)
                sig_strength[sym] = sig_strength.get(sym, 0.0) + val
                direction = 1.0 if str(s.get("signal") or "long").startswith("long") else -1.0
                sig_dir[sym] = sig_dir.get(sym, 0.0) + direction * val
            except Exception:
                pass

        # Fallback tiebreaker: if all interest == 0 or all px == 0, rotate order across ticks
        try:
            all_zero_interest = all((float(u.get("interest") or 0.0) == 0.0) for u in universe_sorted) if universe_sorted else True
            all_zero_px = all((float(u.get("px") or 0.0) == 0.0) for u in universe_sorted) if universe_sorted else True
            if (all_zero_interest or all_zero_px) and len(universe_sorted) > 1:
                if not hasattr(self, "_rr_ptr"):
                    self._rr_ptr = 0
                self._rr_ptr = (self._rr_ptr + 1) % len(universe_sorted)
                universe_sorted = universe_sorted[self._rr_ptr:] + universe_sorted[:self._rr_ptr]
                # re-rank after rotation
                for idx, u in enumerate(universe_sorted):
                    u["rank"] = idx + 1
        except Exception:
            pass

        universe_trimmed = universe_sorted[:top_n]

        # ---------- Stage‑1 ranker (deterministic) ----------
        def _near_earn(sym: str) -> bool:
            try:
                from datetime import datetime
                ed = (events.get(sym) or {}).get("earnings")
                if not ed:
                    return False
                d = datetime.fromisoformat(str(ed).split()[0])
                return abs((d - datetime.now()).days) <= 3
            except Exception:
                return False

        def _valuation_ok(sym: str) -> bool:
            try:
                pe = float((fundamentals.get(sym) or {}).get("pe") or 0.0)
                return not (pe and pe >= 80.0)
            except Exception:
                return True

        def _s1_score(u: Dict[str, Any]) -> float:
            s = 0.0
            try:
                sym = str(u.get("sym") or "")
                s += float(u.get("interest") or 0.0) * 0.5
                s += (2.0 if str(u.get("trend") or "") == "up" else 0.0)
                rsi = float(u.get("rsi") or 50.0)
                s += max(0.0, 20.0 - abs(rsi - 50.0)) / 20.0
                s += min(2.0, float(sig_strength.get(sym) or 0.0))
                if _near_earn(sym):
                    s -= 1.0
                if not _valuation_ok(sym):
                    s -= 1.0
            except Exception:
                pass
            return s

        # Optional liquidity floor: drop illiquid names before GPT (adv_usd_20 < threshold)
        try:
            min_adv = float(os.getenv("AUTOPILOT_MIN_ADV_USD", "0") or 0.0)
        except Exception:
            min_adv = 0.0
        if min_adv > 0:
            try:
                universe_trimmed = [u for u in universe_trimmed if float(u.get("adv_usd_20") or 0.0) >= min_adv]
            except Exception:
                pass

        for u in universe_trimmed:
            sym = str(u.get("sym") or "")
            try:
                u["_s1_score"] = _s1_score(u)
                u["_near_earnings"] = _near_earn(sym)
                u["_valuation_ok"] = _valuation_ok(sym)
            except Exception:
                pass
        try:
            universe_trimmed.sort(key=lambda x: float(x.get("_s1_score") or 0.0), reverse=True)
        except Exception:
            pass

        # NBBO snapshot via moomoo (best-effort)
        try:
            c = self.get_client()
            qc = getattr(c, 'quote_ctx', None)
            if qc is not None and hasattr(qc, 'get_stock_quote'):
                codes = [str(u.get('sym') or '') for u in universe_trimmed if u.get('sym')]
                if codes:
                    try:
                        ret, df = qc.get_stock_quote(codes)
                        if ret == 0 and df is not None:
                            try:
                                import pandas as _pd
                                if hasattr(df, 'to_dict'):
                                    recs = df.to_dict(orient='records')
                                else:
                                    recs = []
                            except Exception:
                                recs = []
                            mp = {}
                            # optional persistence for medians
                            try:
                                from core.storage import get_setting, set_setting  # type: ignore
                                import json as _json
                            except Exception:
                                get_setting = None  # type: ignore
                                set_setting = None  # type: ignore
                            for r in recs or []:
                                code = str(r.get('code') or r.get('stock_code') or r.get('symbol') or '')
                                bid = float(r.get('bid_price') or r.get('bid') or 0.0)
                                ask = float(r.get('ask_price') or r.get('ask') or 0.0)
                                mid = (bid+ask)/2.0 if (bid>0 and ask>0) else 0.0
                                spread_pct = ((ask - bid)/mid*100.0) if mid>0 else None
                                halted = False
                                try:
                                    halted = bool(r.get('suspension') or r.get('halt') or False)
                                except Exception:
                                    halted = False
                                if code:
                                    nbbo_med = None; nbbo_n = 0
                                    if get_setting and set_setting and spread_pct is not None:
                                        try:
                                            key = f"nbbo_hist:{code}"
                                            raw = get_setting(key)
                                            hist = []
                                            try:
                                                hist = _json.loads(raw) if raw else []
                                            except Exception:
                                                hist = []
                                            import time as _t, statistics as _stat
                                            hist.insert(0, [int(_t.time()), float(spread_pct)])
                                            hist = hist[:60]
                                            set_setting(key, hist)
                                            vals = [float(x[1]) for x in hist if isinstance(x, (list, tuple)) and len(x)>=2]
                                            if vals:
                                                nbbo_med = float(_stat.median(vals))
                                                nbbo_n = len(vals)
                                        except Exception:
                                            pass
                                    mp[code] = {'nbbo_spread_pct': spread_pct, 'halted': halted, 'nbbo_spread_med': nbbo_med, 'nbbo_samples': nbbo_n}
                            for u in universe_trimmed:
                                sym = str(u.get('sym') or '')
                                if sym in mp:
                                    try:
                                        u['nbbo_spread_pct'] = mp[sym]['nbbo_spread_pct']
                                        u['nbbo_spread_med'] = mp[sym]['nbbo_spread_med']
                                        u['nbbo_samples'] = mp[sym]['nbbo_samples']
                                        u['halted'] = mp[sym]['halted']
                                    except Exception:
                                        pass
                    except Exception:
                        pass
        except Exception:
            pass

        # Fundamentals + events for trimmed universe (best-effort via yfinance)
        fundamentals: Dict[str, Dict[str, float | str]] = {}
        events: Dict[str, Dict[str, str]] = {}
        try:
            import yfinance as _yf  # type: ignore
            for u in universe_trimmed:
                try:
                    sym = str(u.get("sym") or ""); tid = sym.split(".",1)[-1] if "." in sym else sym
                    tk = _yf.Ticker(tid)
                    info = getattr(tk, "fast_info", None)
                    pe = None; mcap = None
                    try:
                        pe = float(getattr(info, "pe", None) or 0.0) or None
                        mcap = float(getattr(info, "market_cap", None) or 0.0) or None
                    except Exception:
                        pass
                    # extend fundamentals with growth/margins/leverage/quality (best-effort)
                    rev_g = None; gp_margin = None; op_margin = None; dte = None; fcf_margin = None; sector = None
                    # ownership/float/short interest (best-effort via get_info)
                    float_shares = None; shares_out = None; inst_own = None; insider_own = None; short_pct_float = None
                    # analyst/estimates (best-effort)
                    eps_next = None; eps_surprise_avg = None; analyst_cov = None; analyst_rec = None; pt_mean = None
                    # options/iv proxy (best-effort)
                    iv_atm = None; iv_days = None; iv_skew = None
                    try:
                        # sector and ownership via get_info when available
                        try:
                            info2 = tk.get_info()
                            if isinstance(info2, dict):
                                sector = info2.get("sector")
                                try:
                                    float_shares = float(info2.get("floatShares") or 0) or None
                                except Exception:
                                    pass
                                try:
                                    shares_out = float(info2.get("sharesOutstanding") or 0) or None
                                except Exception:
                                    pass
                                try:
                                    inst_own = float(info2.get("heldPercentInstitutions") or 0.0) or None
                                except Exception:
                                    pass
                                try:
                                    insider_own = float(info2.get("heldPercentInsiders") or 0.0) or None
                                except Exception:
                                    pass
                                try:
                                    short_pct_float = float(info2.get("shortPercentOfFloat") or 0.0) or None
                                except Exception:
                                    pass
                                # analyst coverage and price target (when present)
                                try:
                                    analyst_cov = int(info2.get("numberOfAnalystOpinions") or 0) or None
                                except Exception:
                                    pass
                                try:
                                    analyst_rec = str(info2.get("recommendationKey") or "") or None
                                except Exception:
                                    pass
                                try:
                                    pt_mean = float(info2.get("targetMeanPrice") or 0.0) or None
                                except Exception:
                                    pass
                                # valuation bands (best-effort)
                                try:
                                    ev = float(info2.get("enterpriseValue") or 0.0) or None
                                    ebitda = float(info2.get("ebitda") or 0.0) or None
                                    if ev and ebitda and ebitda != 0:
                                        fundamentals.setdefault(sym, {})["ev_ebitda"] = ev / ebitda
                                except Exception:
                                    pass
                                try:
                                    ttm_rev = float(info2.get("totalRevenue") or 0.0) or None
                                    if mcap and ttm_rev and ttm_rev != 0:
                                        fundamentals.setdefault(sym, {})["ps_ttm"] = mcap / ttm_rev
                                except Exception:
                                    pass
                                try:
                                    roic = float(info2.get("returnOnCapital") or 0.0) or None
                                    if roic is not None:
                                        fundamentals.setdefault(sym, {})["roic"] = roic
                                except Exception:
                                    pass
                        except Exception:
                            sector = None
                        import pandas as _pd
                        fin = getattr(tk, 'financials', None)
                        bs = getattr(tk, 'balance_sheet', None)
                        cfs = getattr(tk, 'cashflow', None)
                        def _val(df, row, idx=0):
                            try:
                                return float(df.loc[row].iloc[idx])
                            except Exception:
                                return None
                        if isinstance(fin, _pd.DataFrame) and fin.shape[1] >= 2:
                            rev0 = _val(fin, 'Total Revenue', 0); rev1 = _val(fin, 'Total Revenue', 1)
                            gp = _val(fin, 'Gross Profit', 0); opi = _val(fin, 'Operating Income', 0)
                            if rev0 and rev1 and rev1 != 0:
                                rev_g = (rev0 - rev1) / abs(rev1)
                            if rev0 and gp:
                                gp_margin = gp / rev0
                            if rev0 and opi:
                                op_margin = opi / rev0
                        if isinstance(bs, _pd.DataFrame):
                            debt = _val(bs, 'Total Debt', 0); equity = _val(bs, "Total Stockholder Equity", 0)
                            if debt is not None and equity:
                                dte = (debt / equity) if equity else None
                        if isinstance(cfs, _pd.DataFrame) and isinstance(fin, _pd.DataFrame):
                            fcf = _val(cfs, 'Free Cash Flow', 0); rev0b = _val(fin, 'Total Revenue', 0)
                            if fcf and rev0b:
                                fcf_margin = fcf / rev0b
                        # analyst: earnings dates with estimates → surprise history; revisions (best-effort)
                        try:
                            edf = tk.get_earnings_dates(limit=8)
                            if edf is not None and hasattr(edf, 'shape') and edf.shape[0] > 0:
                                try:
                                    # pandas import local to avoid hard dep if yfinance older
                                    import pandas as _pd
                                    df_ed = edf if isinstance(edf, _pd.DataFrame) else None
                                except Exception:
                                    df_ed = None
                                if df_ed is not None:
                                    # last row surprise mean
                                    try:
                                        col = 'Surprise(%)' if 'Surprise(%)' in df_ed.columns else 'Surprise %'
                                        sv = [float(x) for x in (df_ed[col].dropna().tolist() or []) if x is not None]
                                        if sv:
                                            eps_surprise_avg = sum(sv) / len(sv)
                                    except Exception:
                                        pass
                                    # next EPS estimate from first upcoming row
                                    try:
                                        col_e = 'EPS Estimate' if 'EPS Estimate' in df_ed.columns else None
                                        if col_e:
                                            eps_vals = [float(x) for x in (df_ed[col_e].dropna().tolist() or []) if x is not None]
                                            if eps_vals:
                                                eps_next = eps_vals[0]
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                        try:
                            et = getattr(tk, 'earnings_trend', None)
                            if et is not None:
                                import pandas as _pd
                                df = et if isinstance(et, _pd.DataFrame) else None
                                if df is not None and not df.empty:
                                    # Use first row as current horizon
                                    row = df.iloc[0]
                                    # epsRevisions may be a dict-like or nested mapping; try a few shapes
                                    try:
                                        revs = row.get('epsRevisions')
                                        if isinstance(revs, dict):
                                            up90 = float(revs.get('upLast90days') or revs.get('upLast60days') or 0)
                                            down90 = float(revs.get('downLast90days') or revs.get('downLast60days') or 0)
                                            fundamentals.setdefault(sym, {})['eps_rev_up_90d'] = up90
                                            fundamentals.setdefault(sym, {})['eps_rev_down_90d'] = down90
                                    except Exception:
                                        pass
                                    # revenueEstimate nested
                                    try:
                                        revEst = row.get('revenueEstimate')
                                        if isinstance(revEst, dict):
                                            rev_next = float(revEst.get('avg') or 0.0) or None
                                            if rev_next is not None:
                                                fundamentals.setdefault(sym, {})['rev_next_est'] = rev_next
                                            # revisions
                                            try:
                                                rrevs = revEst.get('revisions') if isinstance(revEst.get('revisions'), dict) else None
                                                if isinstance(rrevs, dict):
                                                    up90 = float(rrevs.get('upLast90days') or rrevs.get('upLast60days') or 0)
                                                    down90 = float(rrevs.get('downLast90days') or rrevs.get('downLast60days') or 0)
                                                    fundamentals.setdefault(sym, {})['rev_est_rev_up_90d'] = up90
                                                    fundamentals.setdefault(sym, {})['rev_est_rev_down_90d'] = down90
                                            except Exception:
                                                pass
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                        # options chain: multi-delta skew + term structure (best-effort)
                        try:
                            opts = getattr(tk, 'options', []) or []
                            if isinstance(opts, (list, tuple)) and opts:
                                # choose short (~30D) and long (>=60D) expiries for term structure
                                import datetime as _dt
                                def _days(ex: str) -> int:
                                    try:
                                        d = _dt.datetime.fromisoformat(str(ex))
                                        return int((d - _dt.datetime.now()).days)
                                    except Exception:
                                        return 9999
                                expiries_sorted = sorted(list(opts), key=lambda x: _days(x))
                                expiry_short = sorted(expiries_sorted, key=lambda x: abs(_days(x) - 30))[0]
                                long_candidates = [e for e in expiries_sorted if _days(e) >= 60]
                                expiry_long = long_candidates[0] if long_candidates else expiries_sorted[-1]
                                px_last = float(u.get('px') or 0.0)
                                def _chain_features(exp: str):
                                    out = {"atm": None, "rr25": None, "rr10": None}
                                    try:
                                        ch = tk.option_chain(exp)
                                        import pandas as _pd
                                        calls = ch.calls if hasattr(ch, 'calls') else None
                                        puts = ch.puts if hasattr(ch, 'puts') else None
                                        if not (isinstance(calls, _pd.DataFrame) and isinstance(puts, _pd.DataFrame) and px_last>0):
                                            return out
                                        # ATM IV
                                        calls['dist_abs'] = (calls['strike'] - px_last).abs()
                                        row = calls.sort_values('dist_abs').head(1)
                                        if len(row)>0:
                                            out['atm'] = float(row['impliedVolatility'].values[0])
                                        # 25% moneyness proxy
                                        def _iv_at(df, target):
                                            df['km'] = (df['strike'] - target).abs()
                                            r = df.sort_values('km').head(1)
                                            return float(r['impliedVolatility'].values[0]) if len(r)>0 else None
                                        c25 = _iv_at(calls, px_last*1.25)
                                        p25 = _iv_at(puts, px_last*0.75)
                                        if c25 is not None and p25 is not None:
                                            out['rr25'] = float(p25 - c25)
                                        c10 = _iv_at(calls, px_last*1.10)
                                        p10 = _iv_at(puts, px_last*0.90)
                                        if c10 is not None and p10 is not None:
                                            out['rr10'] = float(p10 - c10)
                                        return out
                                    except Exception:
                                        return out
                                f_short = _chain_features(expiry_short)
                                f_long = _chain_features(expiry_long)
                                if f_short.get('atm'):
                                    iv_atm = float(f_short['atm'])
                                    iv_days = _days(expiry_short)
                                if f_short.get('rr25') is not None:
                                    fundamentals.setdefault(sym, {})['iv_rr25_short'] = float(f_short['rr25'])
                                if f_short.get('rr10') is not None:
                                    fundamentals.setdefault(sym, {})['iv_rr10_short'] = float(f_short['rr10'])
                                if f_long.get('rr25') is not None:
                                    fundamentals.setdefault(sym, {})['iv_rr25_long'] = float(f_long['rr25'])
                                if f_long.get('atm') and f_short.get('atm'):
                                    fundamentals.setdefault(sym, {})['iv_term_slope'] = float(f_long['atm'] - f_short['atm'])
                        except Exception:
                            pass
                        # insider transactions (best-effort)
                        try:
                            trans = getattr(tk, 'insider_transactions', None)
                            if trans is not None:
                                import pandas as _pd
                                df_it = trans if isinstance(trans, _pd.DataFrame) else None
                                if df_it is not None and {'Type','Value','Shares'} <= set(df_it.columns):
                                    # net shares over ~90d
                                    df_recent = df_it.head(50)  # yfinance returns newest first
                                    net_shares = 0.0
                                    for _, r in df_recent.iterrows():
                                        t = str(r.get('Type') or '').lower()
                                        sh = float(r.get('Shares') or 0.0)
                                        if 'buy' in t:
                                            net_shares += sh
                                        elif 'sell' in t:
                                            net_shares -= sh
                                    fundamentals.setdefault(sym, {})['insider_net_shares_90d'] = net_shares
                        except Exception:
                            pass
                    # IV rank proxy (ATR% percentile over last 90 bars)
                    try:
                        highs = u.get('_highs') or []
                        lows = u.get('_lows') or []
                        closes = u.get('_closes') or []
                        ivr = None
                        if isinstance(highs, list) and len(highs) >= 90 and isinstance(closes, list):
                            # simple ATR(14) EMA series and percentile rank of last vs 90
                            import math
                            tr = []
                            for i in range(len(closes)):
                                if i == 0:
                                    tr.append(float(highs[i]) - float(lows[i]))
                                else:
                                    h = float(highs[i]); l = float(lows[i]); pc = float(closes[i-1])
                                    tr.append(max(h - l, abs(h - pc), abs(l - pc)))
                            p = 14
                            atr = []
                            alpha = 2.0 / (p + 1.0)
                            a = None
                            for i, v in enumerate(tr):
                                a = v if a is None else (1-alpha)*a + alpha*v
                                atr.append(a)
                            atr_pct_series = [(atr[i] / float(closes[i]) * 100.0) if float(closes[i])>0 else 0.0 for i in range(len(atr))]
                            window = atr_pct_series[-90:]
                            last = window[-1]
                            less = sum(1 for x in window if x <= last)
                            ivr = (less / float(len(window))) * 100.0 if window else None
                        if ivr is not None:
                            fundamentals.setdefault(sym, {})['ivr_proxy_90'] = ivr
                    except Exception:
                        pass

                    fundamentals[sym] = {k: v for k, v in {
                        "pe": pe, "market_cap": mcap,
                        "rev_g_yoy": rev_g, "gross_margin": gp_margin, "op_margin": op_margin,
                        "debt_to_equity": dte, "fcf_margin": fcf_margin, "sector": sector,
                        # ownership & short/float
                        "float_shares": float_shares, "shares_out": shares_out,
                        "inst_own_pct": inst_own, "insider_own_pct": insider_own,
                        "short_pct_float": short_pct_float,
                        # analysts
                        "eps_next": eps_next, "eps_surprise_avg_pct": eps_surprise_avg,
                        "analyst_cov": analyst_cov, "analyst_rec": analyst_rec, "pt_mean": pt_mean,
                        # options/volatility snapshot
                        "iv_atm_approx": iv_atm, "iv_days": iv_days, "iv_skew": iv_skew,
                        # volatility proxy from price (fallback)
                        "vol_proxy_atr_pct": float(u.get("atr_pct") or 0.0),
                        # valuation extras inlined earlier (ev_ebitda, ps_ttm, roic) and ivr_proxy_90/insider_net_shares_90d may be preset in dict
                    }.items() if v is not None}
                    # earnings & ex-div dates
                    ed = None; exd = None
                    try:
                        cal = tk.calendar
                        if hasattr(cal, 'index') and 'Earnings Date' in set(getattr(cal,'index',[])):
                            ed = str(cal.loc['Earnings Date'][0])
                        if hasattr(cal, 'index') and 'Ex-Dividend Date' in set(getattr(cal,'index',[])):
                            exd = str(cal.loc['Ex-Dividend Date'][0])
                    except Exception:
                        pass
                    events[sym] = {k: v for k, v in {"earnings": ed, "ex_div": exd}.items() if v}
                except Exception:
                    continue
        # Sector/peer RS-comp (rank 20d return within sector across trimmed set)
        try:
            # build sector mapping
            sector_map: Dict[str, str] = {}
            for u in universe_trimmed:
                sym = str(u.get("sym") or "")
                sec = str((fundamentals.get(sym) or {}).get("sector") or "")
                if sym:
                    sector_map[sym] = sec
            # returns
            r20: Dict[str, float] = {str(u.get("sym")): float(u.get("ret_20d_pct") or 0.0) for u in universe_trimmed if u.get("sym")}
            # compute percentile within sector
            rs_comp: Dict[str, float] = {}
            sector_avg_ret: Dict[str, float] = {}
            for sec in set(sector_map.values()):
                bucket = [r20[s] for s in r20 if sector_map.get(s,"")==sec]
                if not bucket:
                    continue
                lo = min(bucket); hi = max(bucket)
                # simple sector trend proxy
                sector_avg_ret[sec] = sum(bucket) / float(len(bucket))
                for s, v in r20.items():
                    if sector_map.get(s,"")!=sec: continue
                    rs_comp[s] = ((v - lo) / (hi - lo) * 100.0) if hi>lo else 50.0
            # attach into fundamentals
            for sym, pct in rs_comp.items():
                fundamentals.setdefault(sym, {})["rs_sector_pct"] = pct
            for sec, avgv in sector_avg_ret.items():
                # attach sector trend to all members in that sector
                for sym, ssec in sector_map.items():
                    if ssec == sec:
                        fundamentals.setdefault(sym, {})["sector_trend_20d_pct"] = avgv
        except Exception:
            pass

        # Update IV history for IVR true percentile (cached in settings, per tenor)
        ivr_map: Dict[str, float] = {}
        if _HAS_STORAGE:
            try:
                from core.storage import get_setting, set_setting  # type: ignore
                import json as _json
                import time as _t, statistics as _stat
                for u in universe_trimmed:
                    sym = str(u.get('sym') or '')
                    if not sym:
                        continue
                    iv = None
                    try:
                        iv = float((fundamentals.get(sym) or {}).get('iv_atm_approx') or 0.0) or None
                    except Exception:
                        iv = None
                    if iv is None or iv <= 0:
                        continue
                    # bucket by tenor
                    days = None
                    try:
                        days = int((fundamentals.get(sym) or {}).get('iv_days') or 0)
                    except Exception:
                        days = 0
                    label = '30D'
                    if days >= 76 and days <= 120:
                        label = '90D'
                    elif days >= 46 and days <= 75:
                        label = '60D'
                    elif days >= 121:
                        label = '180D'
                    key = f"iv_hist:{sym}:{label}"
                    raw = get_setting(key)
                    try:
                        hist = _json.loads(raw) if raw else []
                    except Exception:
                        hist = []
                    # Append sample
                    try:
                        hist.insert(0, [int(_t.time()), float(iv)])
                        hist = hist[:240]
                        set_setting(key, hist)
                    except Exception:
                        pass
                    try:
                        vals = [float(x[1]) for x in hist if isinstance(x, (list, tuple)) and len(x)>=2]
                        if len(vals) >= 10:
                            cur = float(iv)
                            less = sum(1 for v in vals if v <= cur)
                            ivr_map[sym] = round(less / float(len(vals)) * 100.0, 2)
                    except Exception:
                        continue
            except Exception:
                ivr_map = {}

        # --- Macro snapshot (best-effort; cached) ---
        macro: Dict[str, float | str] = {}
        try:
            ttl = int(os.getenv("AUTOPILOT_MACRO_TTL_SEC", "300") or "300")
        except Exception:
            ttl = 300
        try:
            import time as _time
            now = _time.time()
            if not hasattr(self, "_macro_cache"):
                self._macro_cache = {"ts": 0.0, "data": {}}
            if float(self._macro_cache.get("ts") or 0.0) + ttl < now:
                try:
                    import yfinance as _yf  # type: ignore
                    def last_close(sym: str) -> float:
                        try:
                            df = _yf.download(sym, period="5d", interval="1d", progress=False, threads=False)
                            if df is None or df.empty:
                                return 0.0
                            import pandas as _pd
                            if isinstance(df.columns, _pd.MultiIndex):
                                df.columns = [c[0] for c in df.columns]
                            return float(df['Close'].iloc[-1])
                        except Exception:
                            return 0.0
                    macro = {
                        "vix_close": last_close("^VIX"),
                        "dxy_close": last_close("DX-Y.NYB"),  # DXY proxy on Yahoo
                        "us10y_yield": last_close("^TNX") / 10.0 if last_close("^TNX")>0 else 0.0,
                        "spy_close": last_close("SPY"),
                    }
                except Exception:
                    macro = {}
                self._macro_cache = {"ts": now, "data": macro}
            else:
                macro = dict(self._macro_cache.get("data") or {})
        except Exception:
            macro = {}

        # Build simple portfolio snapshot (exposure & sector concentration)
        try:
            px_map: Dict[str, float] = {str(u.get("sym")): float(u.get("px") or 0.0) for u in universe if u.get("sym")}
            total_mv = 0.0
            sector_mv: Dict[str, float] = {}
            # Build returns series for correlation (last 60 closes)
            ret_series: Dict[str, List[float]] = {}
            try:
                for u in universe:
                    symu = str(u.get('sym') or '')
                    closes = u.get('_closes') or []
                    if symu and isinstance(closes, list) and len(closes) >= 61:
                        rs60: List[float] = []
                        for i in range(-60, 0):
                            try:
                                prev = float(closes[i-1]); cur = float(closes[i])
                                rs60.append((cur/prev - 1.0) if prev>0 else 0.0)
                            except Exception:
                                rs60.append(0.0)
                        # keep also 20-bar
                        rs20 = rs60[-20:]
                        ret_series[symu] = [*rs20, *rs60]  # store both windows concatenated
            except Exception:
                ret_series = {}
            for p in pos_norm:
                sym = str(p.get("sym") or ""); qty = float(p.get("qty") or 0.0)
                if not sym or qty == 0:
                    continue
                px = float(px_map.get(sym) or p.get("avg") or 0.0)
                mv = abs(qty * px)
                total_mv += mv
                sec = str((fundamentals.get(sym) or {}).get("sector") or "Unknown")
                sector_mv[sec] = sector_mv.get(sec, 0.0) + mv
            sector_exposure = {k: (v / total_mv * 100.0 if total_mv>0 else 0.0) for k, v in sector_mv.items()}
            max_pos = int(risk.get("max_positions") or 0)
            cur_pos = sum(1 for p in pos_norm if abs(float(p.get("qty") or 0.0)) > 0.0)
            open_slots = max(0, max_pos - cur_pos) if max_pos>0 else None
            concentration_top = None
            if sector_exposure:
                sec_top = max(sector_exposure.items(), key=lambda x: x[1])
                concentration_top = [sec_top[0], round(sec_top[1],2)]
            portfolio = {
                "total_positions": cur_pos,
                "open_slots": open_slots,
                "exposure_est": total_mv,
                "sector_exposure": sector_exposure,
                "concentration_top": concentration_top,
            }
        except Exception:
            portfolio = {"total_positions": 0, "open_slots": None, "exposure_est": 0.0, "sector_exposure": {}, "concentration_top": None}

        # Correlation of each trimmed symbol vs portfolio synthetic return (MV-weighted)
        corr_portfolio: Dict[str, float] = {}
        corr_portfolio_w20: Dict[str, float] = {}
        try:
            # Build portfolio returns as equal-weight of holdings that have series
            holds = [(str(p.get('sym')), abs(float(p.get('qty') or 0.0)) * float(px_map.get(str(p.get('sym')), 0.0) or 0.0)) for p in pos_norm if abs(float(p.get('qty') or 0.0))>0.0]
            holds = [(s, w) for (s,w) in holds if s in ret_series and w>0]
            if len(holds) >= 1:
                series_w = [(ret_series[s], w) for (s,w) in holds]
                # derive MV weights
                wsum = sum(w for (_,w) in series_w) or 1.0
                weights = [(s, w/wsum) for (s,w) in holds]
                # build weighted portfolio returns for 60 and 20 windows
                L60 = min(len(ret_series[s]) for (s,_) in holds)
                def _port_ret(window: int):
                    # ret_series stored [last20, last60], re-slice
                    pr = []
                    for i in range(window):
                        idx = -window + i
                        val = 0.0
                        for (s, w) in weights:
                            try:
                                seq = ret_series[s]
                                val += w * float(seq[idx])
                            except Exception:
                                pass
                        pr.append(val)
                    return pr
                prt20 = _port_ret(20)
                prt60 = _port_ret(60)
                import math
                def corr(a: List[float], b: List[float]) -> float:
                    n = min(len(a), len(b));
                    if n <= 1:
                        return 0.0
                    ma = sum(a[-n:])/n; mb = sum(b[-n:])/n
                    cov = sum((a[-n:][i]-ma)*(b[-n:][i]-mb) for i in range(n))
                    va = sum((a[-n:][i]-ma)**2 for i in range(n))
                    vb = sum((b[-n:][i]-mb)**2 for i in range(n))
                    if va<=0 or vb<=0:
                        return 0.0
                    return max(-1.0, min(1.0, cov / ( (va**0.5)*(vb**0.5) )))
                for u in universe_trimmed:
                    sym = str(u.get('sym') or '')
                    rs = ret_series.get(sym)
                    if rs and len(rs) >= 60:
                        c60 = corr(rs[-60:], prt60)
                        c20 = corr(rs[-20:], prt20)
                        corr_portfolio[sym] = round(float(c60), 3)
                        corr_portfolio_w20[sym] = round(float(c20), 3)
        except Exception:
            corr_portfolio = {}
            corr_portfolio_w20 = {}

        # Lightweight per-symbol conflict index (0..1): combine signal-news disagreement and event proximity
        conflict_index: Dict[str, float] = {}
        corr_proxy: Dict[str, float] = {}
        try:
            tone_map = {str(n.get("sym")): str(n.get("tone")) for n in (news_items or []) if n.get("sym")}
            top_sec = (portfolio.get("concentration_top") or [None, None])[0]
            for u in universe_trimmed:
                sym = str(u.get("sym") or "");
                if not sym:
                    continue
                net = float(sig_dir.get(sym) or 0.0)
                tone = tone_map.get(sym, "neutral")
                c = 0.0
                if (net > 0 and tone == "bearish") or (net < 0 and tone == "bullish"):
                    c += 0.6
                if _near_earn(sym):
                    c += 0.3
                if not _valuation_ok(sym) and net > 0:
                    c += 0.2
                conflict_index[sym] = round(min(1.0, c), 3)
                # simple correlation proxy to portfolio: same sector as top exposure → high
                try:
                    ssec = str((fundamentals.get(sym) or {}).get("sector") or "")
                except Exception:
                    ssec = ""
                corr_proxy[sym] = 0.8 if top_sec and ssec == top_sec else (0.4 if ssec else 0.2)
        except Exception:
            conflict_index = {}
            corr_proxy = {}

        # Minimal per-symbol history (last actions) for GPT memory (best-effort)
        history: Dict[str, list] = {}
        if _HAS_STORAGE:
            try:
                from core.storage import list_action_logs  # type: ignore
                rows = list_action_logs(limit=200, symbol=None, since_hours=168)  # last 7 days
                for r in rows:
                    try:
                        sym = str(r.get("symbol") or "")
                        if not sym:
                            continue
                        if str(r.get("action") or "").startswith("autopilot"):
                            extra = {}
                            try:
                                import json as _json
                                extra = _json.loads(r.get("extra_json") or "{}")
                            except Exception:
                                extra = {}
                            history.setdefault(sym, []).append({
                                "ts": r.get("ts"),
                                "reason": r.get("reason"),
                                "status": r.get("status"),
                                "extra": {k: extra.get(k) for k in ("conf", "min_conf", "rationale", "rule_checks") if k in extra},
                            })
                    except Exception:
                        continue
                # trim per-symbol length
                for k in list(history.keys()):
                    history[k] = history[k][:8]
            except Exception:
                history = {}

        # Market breadth (adv/decl ratio) across current universe (not trimmed)
        breadth: Dict[str, Any] = {}
        try:
            adv = sum(1 for u in universe if float(u.get("change_1d_pct") or 0.0) > 0)
            dec = sum(1 for u in universe if float(u.get("change_1d_pct") or 0.0) < 0)
            tot = max(1, adv + dec)
            # update cumulative AD-line
            try:
                self._ad_line += float(adv - dec)
            except Exception:
                pass
            breadth = {"adv": adv, "dec": dec, "adv_decl_ratio": round(adv/float(tot), 3), "ad_line": round(float(getattr(self, "_ad_line", 0.0)), 2)}
        except Exception:
            breadth = {}

        # Derive policy from NL prefs/style for planner awareness


        ctx: Dict[str, Any] = {
            "timestamp": _utcnow_iso(),
            "mode": "auto",
            "account": account,
            "risk": risk,
            "positions": pos_norm,
            "universe": universe_trimmed,
            "universe_total": len(universe),
            "style_summary": style_summary,
            "prefs": prefs,
            "planner": {"min_confidence": min_conf, "top_n": top_n, "strict_prefs": strict_prefs},
            "strategy_signals": signals[:24],  # cap list length
            "news": news_items,
            "fundamentals": fundamentals,
            "events": events,
            "macro": macro,
            "breadth": breadth,
            "policy": policy,
            "sig_strength_map": sig_strength,
            "sig_dir_map": sig_dir,
            "conflict_index": conflict_index,
            "corr_proxy_map": corr_proxy,
            "ivr_map": ivr_map,
            "corr_portfolio_map": corr_portfolio,
            "corr_portfolio_w20": corr_portfolio_w20,
            "portfolio": portfolio,
            "history": history,
            # expose signal weights for explainability
            "signal_weights": signals_weights,
        }
        return ctx

    def _think(self, ctx: Dict[str, Any]) -> Dict[str, Any]:
        out_model = self._planner.plan(ctx)
        return out_model.dict() if hasattr(out_model, "dict") else out_model  # type: ignore

    # --- policy derivation from NL prefs/style_summary ---
    @staticmethod
    def _derive_policy(style_summary: str, prefs: Dict[str, Any]) -> Dict[str, Any]:
        txt = (style_summary or "").lower()
        def has(*phrases: str) -> bool:
            return any(p in txt for p in phrases)
        reduce_only = has("reduce only", "close only", "only close", "flatten only", "only sell", "no new")
        long_only = has("long only", "no shorts", "avoid shorts")
        short_only = has("short only", "no longs", "sell only")
        forbid_new = reduce_only or has("no new entries", "block opens")
        # resolve conflicts conservatively
        if long_only and short_only:
            long_only = False; short_only = False
        return {
            "reduce_only": bool(reduce_only),
            "long_only": bool(long_only),
            "short_only": bool(short_only),
            "forbid_new": bool(forbid_new),
        }

    # --- validator: enforce policy; transform/drop with audit ---
    @staticmethod
    def _validate_and_transform(decisions: List[Dict[str, Any]], policy: Dict[str, Any], pos_map: Dict[str, float]) -> Dict[str, Any]:
        out: List[Dict[str, Any]] = []
        transformed = 0; dropped = 0
        for d in decisions:
            try:
                sym = str(d.get("sym") or d.get("symbol") or "").strip()
                action = str(d.get("action") or "open")
                side = str(d.get("side") or ("buy" if action!="close" else "sell"))
                entry = str(d.get("entry") or "market")
                # Policy: reduce-only/forbid-new
                if policy.get("reduce_only") or policy.get("forbid_new"):
                    if action in ("open","add"):
                        d2 = dict(d); d2.update({"action": "hold", "rationale": (d.get("rationale") or "") + " | policy_reduce_only"})
                        out.append(d2); transformed += 1; continue
                # Policy: long-only / short-only for opens
                if action in ("open","add"):
                    if policy.get("long_only") and side == "sell":
                        d2 = dict(d); d2.update({"action": "hold", "rationale": (d.get("rationale") or "") + " | policy_long_only"})
                        out.append(d2); transformed += 1; continue
                    if policy.get("short_only") and side == "buy":
                        d2 = dict(d); d2.update({"action": "hold", "rationale": (d.get("rationale") or "") + " | policy_short_only"})
                        out.append(d2); transformed += 1; continue
                # Close with no position -> drop
                if action == "close" and abs(float(pos_map.get(sym) or 0.0)) <= 0.0:
                    dropped += 1; continue
                # Otherwise accept
                out.append(d)
            except Exception:
                out.append(d)
        return {"decisions": out, "transformed": transformed, "dropped": dropped}


    @staticmethod
    def _evaluate(decisions: List[Dict[str, Any]], ctx: Dict[str, Any], threshold: float = -1.0) -> Dict[str, Any]:
        try:
            thr_env = os.getenv("AUTOPILOT_EVAL_THRESHOLD")
            if threshold < 0 and thr_env is not None:
                threshold = float(thr_env)
        except Exception:
            pass
        if threshold < 0:
            threshold = 0.25
        kept: List[Dict[str, Any]] = []
        dropped = 0
        details: List[Dict[str, Any]] = []
        sig_map = ctx.get("sig_strength_map") or {}
        sig_dir = ctx.get("sig_dir_map") or {}
        news_items = ctx.get("news") or []
        news_tone = {str(n.get("sym")): str(n.get("tone")) for n in news_items if n.get("sym")}
        fundamentals = ctx.get("fundamentals") or {}
        events = ctx.get("events") or {}
        conflict_map = ctx.get("conflict_index") or {}
        portfolio = ctx.get("portfolio") or {}
        concentration_top = (portfolio.get("concentration_top") or [None, None])[0]
        concentration_pct = float((portfolio.get("concentration_top") or [None, 0])[1] or 0.0)
        open_slots = portfolio.get("open_slots")
        ivr_map = ctx.get("ivr_map") or {}
        corrp_map = ctx.get("corr_portfolio_map") or {}
        corrp_w20 = ctx.get("corr_portfolio_w20") or {}
        try:
            conc_cap = float(os.getenv("AUTOPILOT_SECTOR_CONC_CAP_PCT", "45") or 45.0)
        except Exception:
            conc_cap = 45.0
        # Liquidity thresholds
        try:
            min_adv_env = float(os.getenv("AUTOPILOT_MIN_ADV_USD", "0") or 0.0)
        except Exception:
            min_adv_env = 0.0
        try:
            max_spread_env = float(os.getenv("AUTOPILOT_MAX_SPREAD_PCT", "5") or 5.0)
        except Exception:
            max_spread_env = 5.0
        # Position map for press-winner heuristic
        pos_map: Dict[str, Dict[str, float]] = {}
        try:
            for p in ctx.get("positions", []) or []:
                pos_map[str(p.get("sym"))] = {"qty": float(p.get("qty") or 0.0), "avg": float(p.get("avg") or 0.0)}
        except Exception:
            pos_map = {}

        def near_earn(sym: str) -> bool:
            try:
                from datetime import datetime
                ed = (events.get(sym) or {}).get("earnings")
                if not ed:
                    return False
                d = datetime.fromisoformat(str(ed).split()[0])
                return abs((d - datetime.now()).days) <= 3
            except Exception:
                return False

        for d in decisions:
            try:
                sym = str(d.get("sym") or "")
                side = str(d.get("side") or ("buy" if d.get("action") != "close" else "sell"))
                sig = float(sig_map.get(sym) or 0.0)
                net = float(sig_dir.get(sym) or 0.0)
                pe = float((fundamentals.get(sym) or {}).get("pe") or 0.0)
                rs = float((fundamentals.get(sym) or {}).get("rs_sector_pct") or 50.0)
                tone = news_tone.get(sym)
                adv = 0.0
                try:
                    adv = float(next((u.get("adv_usd_20") for u in (ctx.get("universe") or []) if u.get("sym")==sym), 0.0) or 0.0)
                except Exception:
                    adv = 0.0
                spread = None
                try:
                    # prefer NBBO median spread when available; fallback to NBBO single or HL proxy
                    node = next((u for u in (ctx.get("universe") or []) if u.get("sym")==sym), None)
                    if node is not None:
                        if node.get('nbbo_spread_med') is not None:
                            spread = float(node.get('nbbo_spread_med') or 0.0)
                        elif node.get('nbbo_spread_pct') is not None:
                            spread = float(node.get('nbbo_spread_pct') or 0.0)
                        else:
                            spread = float(node.get("hl_spread_pct20") or 0.0)
                except Exception:
                    spread = None
                last_px = 0.0
                try:
                    last_px = float(next((u.get("px") for u in (ctx.get("universe") or []) if u.get("sym")==sym), 0.0) or 0.0)
                except Exception:
                    last_px = 0.0
                sec = str((fundamentals.get(sym) or {}).get("sector") or "")
                score = 0.0
                score += min(1.0, sig / 2.0)
                if (net > 0 and tone == "bearish") or (net < 0 and tone == "bullish"):
                    score -= 0.2
                if tone == "bullish" and side == "buy":
                    score += 0.2
                if tone == "bearish" and side == "sell":
                    score += 0.2
                if tone == "bearish" and side == "buy":
                    score -= 0.2
                if tone == "bullish" and side == "sell":
                    score -= 0.2
                if pe and pe >= 80.0 and side == "buy":
                    score -= 0.2
                if near_earn(sym) and d.get("action") in ("open","add"):
                    score -= 0.25
                if side == "buy" and rs >= 70:
                    score += 0.1
                # IV rank: penalize new opens in very high IV environments
                try:
                    ivr = float(ivr_map.get(sym) or 0.0)
                    if d.get("action") in ("open","add") and ivr >= 90.0:
                        score -= 0.1
                except Exception:
                    pass
                # liquidity guardrails
                # hard gate: halted
                halted = False
                try:
                    halted = bool(next((u.get('halted') for u in (ctx.get('universe') or []) if u.get('sym')==sym), False))
                except Exception:
                    halted = False
                if halted:
                    keep = False
                    details.append({"sym": sym, "score": -1.0, "keep": False})
                    dropped += 1
                    continue
                if min_adv_env > 0 and adv > 0 and adv < min_adv_env:
                    score -= 0.25
                if spread is not None and spread > max_spread_env:
                    score -= 0.2
                # portfolio concentration: penalize adds to top sector when above cap
                if sec and concentration_top and sec == concentration_top and float(concentration_pct) >= conc_cap and d.get("action") in ("open","add"):
                    score -= 0.25
                # correlation penalty: avoid adding highly correlated names
                try:
                    cp = float(corrp_map.get(sym) or 0.0)
                    cp20 = float(corrp_w20.get(sym) or 0.0)
                    if d.get("action") in ("open","add"):
                        if cp >= 0.8:
                            score -= 0.15
                        if cp20 >= 0.9:
                            score -= 0.1
                except Exception:
                    pass
                # conflict index penalty
                cidx = float(conflict_map.get(sym) or 0.0)
                if cidx > 0:
                    score -= min(0.35, cidx * 0.35)
                # no open slots -> penalize new opens
                if (open_slots is not None) and int(open_slots) <= 0 and d.get("action") == "open":
                    score -= 0.25
                # memory: if recent attempts repeatedly failed on this symbol, down-weight opens
                try:
                    hist = (ctx.get("history") or {}).get(sym) or []
                    fails = sum(1 for h in hist if str(h.get("status") or "").lower() in ("blocked","rejected"))
                    if d.get("action") == "open" and fails >= 3:
                        score -= 0.15
                except Exception:
                    pass
                # press-winner heuristic for ADD
                try:
                    if d.get("action") == "add" and sym in pos_map and last_px>0:
                        q = float(pos_map[sym].get("qty") or 0.0)
                        avg = float(pos_map[sym].get("avg") or 0.0)
                        if q != 0 and avg>0:
                            pnl_pct = (last_px/avg - 1.0) * 100.0 * (1.0 if q>0 else -1.0)
                            if (side == "buy" and q>0) or (side == "sell" and q<0):
                                score += 0.1 if pnl_pct > 0 else -0.1
                except Exception:
                    pass
                keep = score >= threshold
                details.append({"sym": sym, "score": round(score,2), "keep": keep})
                if keep:
                    d2 = dict(d)
                    d2.setdefault("rule_checks", {})
                    try:
                        # policy/strict prefs checks
                        pol = ctx.get("policy") or {}
                        policy_ok = True
                        if d.get("action") in ("open","add"):
                            if pol.get("reduce_only") or pol.get("forbid_new"):
                                policy_ok = False
                            if pol.get("long_only") and side == "sell":
                                policy_ok = False
                            if pol.get("short_only") and side == "buy":
                                policy_ok = False
                        strict = bool((ctx.get("planner") or {}).get("strict_prefs") or False)
                        if strict and d.get("action") in ("open","add"):
                            has_stop = bool(d.get("stop"))
                            has_take = bool(d.get("take_profit"))
                            strict_ok = bool(has_stop and has_take)
                        else:
                            strict_ok = True
                        d2["rule_checks"]["strict_prefs_ok"] = strict_ok
                        d2["rule_checks"]["policy_ok"] = policy_ok
                        d2["rule_checks"]["valuation_ok"] = not (pe and pe >= 80.0 and side == "buy")
                        d2["rule_checks"]["near_earnings"] = bool(near_earn(sym))
                        d2["rule_checks"]["conflict_index"] = float(cidx)
                        d2["rule_checks"]["conflict"] = bool(cidx >= 0.5)
                        # liquidity checks summary
                        liq_ok = True
                        if min_adv_env > 0 and adv > 0 and adv < min_adv_env:
                            liq_ok = False
                        if spread is not None and spread > max_spread_env:
                            liq_ok = False
                        d2["rule_checks"]["liquidity_ok"] = liq_ok
                        d2["rule_checks"]["halted"] = bool(halted)
                        # options analytics
                        d2["rule_checks"]["iv_rank_pct"] = float(ivr_map.get(sym) or 0.0)
                        try:
                            skew = float((fundamentals.get(sym) or {}).get("iv_skew") or 0.0)
                            d2["rule_checks"]["iv_skew"] = skew
                        except Exception:
                            pass
                        # portfolio correlation
                        try:
                            d2["rule_checks"]["corr_portfolio"] = float(corrp_map.get(sym) or 0.0)
                            d2["rule_checks"]["corr_portfolio_20"] = float(corrp_w20.get(sym) or 0.0)
                        except Exception:
                            pass
                    except Exception:
                        pass
                    kept.append(d2)
                else:
                    dropped += 1
            except Exception:
                kept.append(d)
        return {"decisions": kept, "dropped": dropped, "scores": details, "threshold": threshold}

    @staticmethod
    def _apply_eval_feedback(ctx: Dict[str, Any], kept: List[Dict[str, Any]], scores: List[Dict[str, Any]]) -> None:
        """Lightly nudge per-strategy weights based on kept decisions' symbols and their scores.
        Best-effort; safe when storage is unavailable. Keeps changes small to avoid oscillation.
        """
        if not _HAS_STORAGE:
            return
        try:
            from core.storage import get_setting, set_setting  # type: ignore
        except Exception:
            return
        try:
            sym_scores = {str(s['sym']): float(s.get('score') or 0.0) for s in (scores or []) if s.get('sym')}
        except Exception:
            sym_scores = {}
        kept_syms = [str(d.get('sym')) for d in kept if d.get('sym')]
        if not kept_syms:
            return
        # Gather signals per kept symbol
        sigs = ctx.get('strategy_signals') or []
        agg: dict[str, list[float]] = {}
        for s in sigs:
            try:
                if str(s.get('sym')) in kept_syms:
                    strat = str(s.get('strategy') or '')
                    sc = sym_scores.get(str(s.get('sym')), 0.0)
                    if strat:
                        agg.setdefault(strat, []).append(sc)
            except Exception:
                continue
        if not agg:
            return
        # Current weights
        import json as _json
        try:
            raw = get_setting("autopilot.signals.weights")
            W = _json.loads(raw) if raw else {}
        except Exception:
            W = {}
        changed = False
        for strat, vals in agg.items():
            if not vals:
                continue
            avg = sum(vals) / float(len(vals))
            base = float(W.get(strat, 1.0))
            # Nudge by small factor around 1.0; clamp
            delta = max(-0.05, min(0.05, (avg - 0.25) * 0.1))  # centered around threshold 0.25
            new_w = max(0.25, min(2.5, round(base * (1.0 + delta), 2)))
            if abs(new_w - base) >= 0.01:
                W[strat] = new_w
                changed = True
        if changed:
            try:
                set_setting("autopilot.signals.weights", W)
            except Exception:
                pass
    # --- adaptive signal weights ---
    async def _adaptive_reweight(self) -> None:
        if not _HAS_STORAGE:
            return
        try:
            from core.storage import performance_stats, get_setting, set_setting, list_action_logs  # type: ignore
        except Exception:
            return
        # respect auto_weight toggle
        try:
            aw = get_setting("autopilot.signals.auto_weight")
            if not aw:
                return
        except Exception:
            return
        try:
            prefs_raw = get_setting("autopilot.prefs")
            import json as _json
            prefs = _json.loads(prefs_raw) if prefs_raw else {}
        except Exception:
            prefs = {}
        target_wr = float(prefs.get("target_winrate_pct") or 55.0)
        target_rr = float(prefs.get("target_rr") or 1.5)
        # overall stats
        try:
            stats = performance_stats(days=90)  # type: ignore
        except Exception:
            stats = {"win_rate_pct": 0.0, "avg_rr": 0.0}
        wr = float(stats.get("win_rate_pct") or 0.0)
        rr = float(stats.get("avg_rr") or 0.0)
        # usage shares from last 24h autopilot decisions
        try:
            rows = list_action_logs(limit=500, symbol=None, since_hours=24)  # type: ignore
        except Exception:
            rows = []
        import json as _json
        use: dict[str, float] = {}
        total = 0.0
        for r in rows:
            if (r.get("action") != "autopilot_act"):
                continue
            try:
                extra = _json.loads(r.get("extra_json") or "{}")
                for s in extra.get("signals_used", []) or []:
                    key = str(s.get("strategy") or "")
                    if not key:
                        continue
                    use[key] = use.get(key, 0.0) + float(s.get("strength") or 0.0)
                    total += float(s.get("strength") or 0.0)
            except Exception:
                continue
        shares = {k: (v / total) for k, v in use.items()} if total > 0 else {}
        # current weights and enabled strategies
        try:
            raw_w = get_setting("autopilot.signals.weights")
            W = _json.loads(raw_w) if raw_w else {}
        except Exception:
            W = {}
        try:
            raw_s = get_setting("autopilot.signals.strategies")
            S = _json.loads(raw_s) if raw_s else {}
        except Exception:
            S = {}
        enabled = {k for k, v in (S or {}).items() if v}
        for k in list(enabled):
            if k not in W:
                W[k] = 1.0
        # compute global factor from target deltas
        def clamp(x: float, lo: float, hi: float) -> float:
            return lo if x < lo else hi if x > hi else x
        s_wr = clamp((wr - target_wr) / 100.0, -0.2, 0.2)
        s_rr = clamp((rr - target_rr) / max(1.0, target_rr*2.0), -0.2, 0.2)
        global_adj = clamp((s_wr + s_rr) / 2.0, -0.2, 0.2)
        if abs(global_adj) < 0.02:
            return  # too small
        changed = False
        for k in list(W.keys()):
            if enabled and k not in enabled:
                continue
            share = shares.get(k, 0.0)
            factor = 1.0 + global_adj * (0.5 + 0.5 * share)
            new_w = clamp(round(W[k] * factor, 2), 0.25, 2.5)
            if abs(new_w - float(W[k])) >= 0.05:
                W[k] = new_w
                changed = True
        if changed:
            try:
                set_setting("autopilot.signals.weights", W)
                self._log("signals_reweighted", {"global_adj": round(global_adj,3), "weights": W})
            except Exception:
                pass

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
        # Shares sizing does not depend on last price
        if size_type == "shares":
            return max(0, int(size_value))
        # Notional and risk-based sizing require a price; fall back to 0 if missing
        if last_px <= 0:
            return 0
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

        # Read min_confidence from ctx and refresh from settings (latest wins)
        try:
            min_conf = float(((ctx.get("planner") or {}).get("min_confidence")) or 0.6)
        except Exception:
            min_conf = 0.6
        # Pull live value from storage to avoid stale ctx
        if _HAS_STORAGE:
            try:
                raw_mc = get_setting("autopilot.min_confidence")  # type: ignore[name-defined]
                if raw_mc is not None:
                    min_conf = float(raw_mc)
            except Exception:
                pass

        # purge expired idempotent entries
        try:
            import time as _time
            now_idem = _time.time()
            for k, exp in list(self._live_decisions.items()):
                if exp <= now_idem:
                    del self._live_decisions[k]
        except Exception:
            pass

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

            # Skip duplicate OPEN when already in that direction (avoid rebuying same symbol)
            try:
                cur_qty = float(pos.get(sym) or 0.0)
                if action == "open":
                    if side == "buy" and cur_qty > 0:
                        self._logs.append({"ts": _utcnow_iso(), "mode": "auto", "action": action,
                                           "symbol": sym, "side": side, "reason": "skip_existing_long", "status": "skipped"})
                        if _HAS_STORAGE:
                            try:
                                insert_action_log("autopilot_act", mode="auto", symbol=sym, side="BUY", reason="skip_existing_long", status="skipped")
                            except Exception:
                                pass
                        continue
                    if side == "sell" and cur_qty < 0:
                        self._logs.append({"ts": _utcnow_iso(), "mode": "auto", "action": action,
                                           "symbol": sym, "side": side, "reason": "skip_existing_short", "status": "skipped"})
                        if _HAS_STORAGE:
                            try:
                                insert_action_log("autopilot_act", mode="auto", symbol=sym, side="SELL", reason="skip_existing_short", status="skipped")
                            except Exception:
                                pass
                        continue
            except Exception:
                pass

            # Idempotence: keep decisions alive until expiry; do not re-place while alive
            def _idem_key() -> str:
                try:
                    entry = "market" if (getattr(d, "entry", None) or (d.get("entry") if isinstance(d, dict) else "market")) == "market" else "limit"
                except Exception:
                    entry = "market"
                lim = getattr(d, "limit_price", None) or (d.get("limit_price") if isinstance(d, dict) else None)
                st = getattr(d, "size_type", None) or (d.get("size_type") if isinstance(d, dict) else "shares")
                sv = getattr(d, "size_value", None) or (d.get("size_value") if isinstance(d, dict) else 0)
                tif_val = getattr(d, "time_in_force", None) or (d.get("time_in_force") if isinstance(d, dict) else "day")
                return f"{sym}|{action}|{side}|{entry}|{lim}|{st}|{sv}|{tif_val}"

            try:
                import time as _time
                idem_key = _idem_key()
                exp_sec = 0
                try:
                    exp_sec = int(getattr(d, "expires_sec", None) or (d.get("expires_sec") if isinstance(d, dict) else 120) or 120)
                except Exception:
                    exp_sec = 120
                exp_ts = _time.time() + max(30, exp_sec)  # minimum 30s
                alive_ts = self._live_decisions.get(idem_key)
                if alive_ts and alive_ts > _time.time():
                    self._logs.append({"ts": _utcnow_iso(), "mode": "auto", "action": action,
                                       "symbol": sym, "side": side, "reason": "idempotent_suppress", "status": "skipped"})
                    if _HAS_STORAGE:
                        try:
                            insert_action_log("autopilot_act", mode="auto", symbol=sym, side=side.upper(), reason="idempotent_suppress", status="skipped")
                        except Exception:
                            pass
                    continue
            except Exception:
                pass

            # Confidence gating: only apply when min_conf > 0 and a confidence is provided
            try:
                raw_conf = getattr(d, "confidence", None) if not isinstance(d, dict) else d.get("confidence")
                conf = (None if raw_conf is None else float(raw_conf))
            except Exception:
                conf = None
            if (float(min_conf) > 0.0) and (conf is not None) and (float(conf) < float(min_conf)):
                # throttle logs per symbol to avoid spam
                try:
                    import time as _t
                    now_ts = float(_t.time())
                    last = float(self._low_conf_log_ts.get(sym) or 0.0)
                    if (now_ts - last) >= 120.0:  # 2 minutes
                        self._logs.append({"ts": _utcnow_iso(), "mode": "auto", "action": action,
                                           "symbol": sym, "side": side,
                                           "qty": f"{getattr(d,'size_type','shares') if not isinstance(d, dict) else d.get('size_type','shares')}:{getattr(d,'size_value',0) if not isinstance(d, dict) else d.get('size_value',0)}",
                                           "price": getattr(d, "limit_price", None) or (d.get("limit_price") if isinstance(d, dict) else None) or "",
                                           "reason": f"low_confidence:{float(conf):.2f}<{float(min_conf):.2f}", "status": "planned"})
                        self._low_conf_log_ts[sym] = now_ts
                        if _HAS_STORAGE:
                            try:
                                insert_action_log("autopilot_act", mode="auto",
                                                  symbol=sym, side=side.upper(), qty=0, price=None,
                                                  reason="low_confidence", status="planned",
                                                  extra={"conf": float(conf), "min_conf": float(min_conf)})
                            except Exception:
                                pass
                except Exception:
                    pass
                continue

            # Strict prefs enforcement: require stop/take when prefs specify
            try:
                planner_cfg = ctx.get("planner") or {}
                strict_flag = bool(planner_cfg.get("strict_prefs") or False)
            except Exception:
                strict_flag = False
            if strict_flag and action == "open":
                want_stop = bool(((ctx.get("prefs") or {}).get("stop_loss_pct") or 0) > 0)
                want_take = bool(((ctx.get("prefs") or {}).get("take_profit_pct") or 0) > 0 or ((ctx.get("prefs") or {}).get("measured_move_atr_mult") or 0) > 0)
                has_stop = bool(getattr(d, "stop", None) or (d.get("stop") if isinstance(d, dict) else None))
                has_take = bool(getattr(d, "take_profit", None) or (d.get("take_profit") if isinstance(d, dict) else None))
                missing = (want_stop and not has_stop) or (want_take and not has_take)
                if missing:
                    self._logs.append({"ts": _utcnow_iso(), "mode": "auto", "action": action,
                                       "symbol": sym, "side": side,
                                       "qty": f"{getattr(d,'size_type','shares') if not isinstance(d, dict) else d.get('size_type','shares')}:{getattr(d,'size_value',0) if not isinstance(d, dict) else d.get('size_value',0)}",
                                       "price": getattr(d, "limit_price", None) or (d.get("limit_price") if isinstance(d, dict) else None) or "",
                                       "reason": "strict_prefs_missing_stop_or_take", "status": "planned"})
                    if _HAS_STORAGE:
                        try:
                            insert_action_log("autopilot_act", mode="auto",
                                              symbol=sym, side=side.upper(), qty=0, price=None,
                                              reason="strict_prefs", status="planned",
                                              extra={"want_stop": want_stop, "has_stop": has_stop, "want_take": want_take, "has_take": has_take})
                        except Exception:
                            pass
                    continue

            # Optional auto-augmentation: if strict_prefs is OFF but prefs specify
            # stop or take and the decision lacks them, annotate the action log to
            # reflect what would be applied. (Execution service doesn't yet place
            # OCOs; this is planning-time guidance + accountability.)
            try:
                planner_cfg = ctx.get("planner") or {}
                strict_flag = bool(planner_cfg.get("strict_prefs") or False)
            except Exception:
                strict_flag = False

            auto_augmented = False
            aug_stop = None
            aug_take = None
            if not strict_flag and action == "open":
                pr = (ctx.get("prefs") or {})
                try:
                    want_stop_val = float(pr.get("stop_loss_pct") or 0.0)
                    want_take_pct = float(pr.get("take_profit_pct") or 0.0)
                    want_take_atr = float(pr.get("measured_move_atr_mult") or 0.0)
                except Exception:
                    want_stop_val = 0.0; want_take_pct = 0.0; want_take_atr = 0.0

                has_stop = bool(getattr(d, "stop", None) or (d.get("stop") if isinstance(d, dict) else None))
                has_take = bool(getattr(d, "take_profit", None) or (d.get("take_profit") if isinstance(d, dict) else None))
                if want_stop_val > 0 and not has_stop:
                    aug_stop = {"type": "percent", "value": want_stop_val}
                    auto_augmented = True
                if (want_take_pct > 0 or want_take_atr > 0) and not has_take:
                    if want_take_pct > 0:
                        aug_take = {"type": "percent", "value": want_take_pct}
                    else:
                        aug_take = {"type": "atr", "mult": want_take_atr}
                    auto_augmented = True

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
            try:
                self._live_decisions[idem_key] = exp_ts
            except Exception:
                pass

            # Build explainability: signals used for this symbol, news tone, weights
            sig_used = []
            try:
                for s in (ctx.get("strategy_signals") or []):
                    if str(s.get("sym")) == str(sym):
                        try:
                            sig_used.append({
                                "strategy": s.get("strategy"),
                                "signal": s.get("signal"),
                                "strength": float(s.get("strength") or 0.0),
                            })
                        except Exception:
                            continue
                sig_used.sort(key=lambda x: float(x.get("strength") or 0.0), reverse=True)
                sig_used = sig_used[:6]
            except Exception:
                sig_used = []  # type: ignore

            tone = None
            try:
                for n in (ctx.get("news") or []):
                    if str(n.get("sym")) == str(sym):
                        tone = n.get("tone")
                        break
            except Exception:
                tone = None

            weights_map = {}
            try:
                wm = ctx.get("signal_weights") or {}
                if isinstance(wm, dict):
                    weights_map = {str(k): float(v) for k, v in wm.items()}
            except Exception:
                weights_map = {}

            # Log requested quantity in shares when available for clarity
            log_qty = f"{spec.size_type}:{spec.size_value}"
            try:
                if spec.size_type == "shares":
                    log_qty = int(spec.size_value)
            except Exception:
                pass

            self._logs.append({"ts": _utcnow_iso(), "mode": "auto", "action": action,
                               "symbol": sym, "side": side,
                               "qty": log_qty,
                               "price": limit_price or "", "reason": f"order:{order.order_id}",
                               "status": str(order.status.value),
                               "rationale": (getattr(d, 'rationale', None) or (d.get('rationale') if isinstance(d, dict) else None))})
            if _HAS_STORAGE:
                try:
                    insert_action_log("autopilot_act", mode="auto",
                                      symbol=sym, side=side.upper(), qty=(int(spec.size_value) if spec.size_type=="shares" else est_qty), price=limit_price,
                                      reason=("order_augmented" if auto_augmented else "order"), status=str(order.status.value),
                                      extra={
                                          "order_id": order.order_id,
                                          "rationale": (getattr(d, 'rationale', None) or (d.get('rationale') if isinstance(d, dict) else None)),
                                          "aug_stop": aug_stop,
                                          "aug_take": aug_take,
                                          "has_stop": bool(getattr(d, "stop", None) or (d.get("stop") if isinstance(d, dict) else None)),
                                          "has_take": bool(getattr(d, "take_profit", None) or (d.get("take_profit") if isinstance(d, dict) else None)),
                                          "conf": conf,
                                          "min_conf": min_conf,
                                          "signals_used": sig_used,
                                          "news_tone": tone,
                                          "signal_weights": weights_map,
                                      })
                except Exception:
                    pass

            # If entry filled immediately and we have augmented/declared stops/takes,
            # place resting protective orders in SIM using stop/limit types.
            try:
                entry_filled = str(order.status.value) == "filled"
            except Exception:
                entry_filled = False
            if entry_filled and (aug_stop or aug_take or getattr(d, "stop", None) or (d.get("stop") if isinstance(d, dict) else None) or getattr(d, "take_profit", None) or (d.get("take_profit") if isinstance(d, dict) else None)):
                entry_px = order.avg_fill_price or last_px
                stop_obj = getattr(d, "stop", None) or (d.get("stop") if isinstance(d, dict) else None) or aug_stop
                take_obj = getattr(d, "take_profit", None) or (d.get("take_profit") if isinstance(d, dict) else None) or aug_take

                def _tp_from(obj):
                    if not obj:
                        return None
                    t = (obj.get("type") if isinstance(obj, dict) else getattr(obj, "type", None))
                    if t == "percent":
                        val = float((obj.get("value") if isinstance(obj, dict) else getattr(obj, "value", 0.0)) or 0.0)
                        return entry_px * (1.0 + (val/100.0) if side=="buy" else 1.0 - (val/100.0))
                    if t == "atr":
                        atr = 0.0
                        for u in ctx.get("universe", []):
                            if u.get("sym") == sym:
                                atr = float(u.get("atr") or 0.0)
                                break
                        mult = float((obj.get("mult") if isinstance(obj, dict) else getattr(obj, "mult", 0.0)) or 0.0)
                        return entry_px + (atr*mult if side=="buy" else -atr*mult)
                    if t == "price":
                        return float((obj.get("value") if isinstance(obj, dict) else getattr(obj, "value", 0.0)) or 0.0)
                    return None

                def _sp_from(obj):
                    if not obj:
                        return None
                    t = (obj.get("type") if isinstance(obj, dict) else getattr(obj, "type", None))
                    if t == "percent":
                        val = float((obj.get("value") if isinstance(obj, dict) else getattr(obj, "value", 0.0)) or 0.0)
                        return entry_px * (1.0 - (val/100.0) if side=="buy" else 1.0 + (val/100.0))
                    if t == "atr":
                        atr = 0.0
                        for u in ctx.get("universe", []):
                            if u.get("sym") == sym:
                                atr = float(u.get("atr") or 0.0)
                                break
                        mult = float((obj.get("mult") if isinstance(obj, dict) else getattr(obj, "mult", 0.0)) or 0.0)
                        return entry_px - (atr*mult if side=="buy" else -atr*mult)
                    if t == "price":
                        return float((obj.get("value") if isinstance(obj, dict) else getattr(obj, "value", 0.0)) or 0.0)
                    return None

                tp_px = _tp_from(take_obj)
                sp_px = _sp_from(stop_obj)

                # Place take-profit as LIMIT and stop as STOP
                try:
                    if tp_px:
                        tp_spec = OrderSpec(
                            symbol=sym,
                            side=OrderSide.sell if side=="buy" else OrderSide.buy,
                            order_type=OrderType.limit,
                            limit_price=float(tp_px),
                            size_type="shares",
                            size_value=float(est_qty),
                            tif=TimeInForce.day,
                            decision_id=idx,
                        )
                        tp_order = exec_service.place_order(tp_spec, ctx_exec)
                        if _HAS_STORAGE:
                            try:
                                insert_action_log("autopilot_act", mode="auto", symbol=sym, side=("SELL" if side=="buy" else "BUY"),
                                                  qty=est_qty, price=float(tp_px), reason="protective_tp", status=str(tp_order.status.value),
                                                  extra={"order_id": tp_order.order_id})
                            except Exception:
                                pass
                except Exception:
                    pass
                try:
                    if sp_px:
                        sp_spec = OrderSpec(
                            symbol=sym,
                            side=OrderSide.sell if side=="buy" else OrderSide.buy,
                            order_type=OrderType.stop,
                            limit_price=float(sp_px),
                            size_type="shares",
                            size_value=float(est_qty),
                            tif=TimeInForce.day,
                            decision_id=idx,
                        )
                        sp_order = exec_service.place_order(sp_spec, ctx_exec)
                        if _HAS_STORAGE:
                            try:
                                insert_action_log("autopilot_act", mode="auto", symbol=sym, side=("SELL" if side=="buy" else "BUY"),
                                                  qty=est_qty, price=float(sp_px), reason="protective_stop", status=str(sp_order.status.value),
                                                  extra={"order_id": sp_order.order_id})
                            except Exception:
                                pass
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

    async def _maybe_sync_deals(self) -> None:
        # refresh interval from settings (optional)
        try:
            if _HAS_STORAGE:
                raw = get_setting("autopilot.deals_sync_sec")  # type: ignore[name-defined]
                if raw is not None:
                    self.deal_sync_sec = int(raw)
        except Exception:
            pass
        # throttle
        try:
            import time as _time
            now = float(_time.time())
            if self.deal_sync_sec <= 0:
                return
            if (now - self._last_deal_sync_ts) < self.deal_sync_sec:
                return
            self._last_deal_sync_ts = now
        except Exception:
            return

        c = self.get_client()
        if c is None or not getattr(c, "connected", False):
            return
        # Try real fills first
        inserted = 0
        try:
            recs = c.get_deals()
            for r in recs or []:
                oid = r.get("order_id") or r.get("orderId") or ""
                code = r.get("code") or r.get("stock_code") or ""
                side = str(r.get("trd_side") or r.get("side") or "").upper()
                qty = float(r.get("deal_qty") or r.get("qty") or r.get("fill_qty") or 0)
                price = float(r.get("deal_price") or r.get("price") or r.get("fill_price") or 0)
                ts = str(r.get("create_time") or r.get("time") or r.get("ts") or "")
                if not code or not side or qty <= 0 or price <= 0 or not ts:
                    continue
                try:
                    if _HAS_STORAGE:
                        record_fill(str(oid), str(code), "BUY" if "BUY" in side else "SELL", qty, price, ts)  # type: ignore[name-defined]
                        try:
                            insert_action_log("fill_detected", mode="auto",  # type: ignore[name-defined]
                                              symbol=str(code), side=("BUY" if "BUY" in side else "SELL"),
                                              qty=qty, price=price, reason="broker_fill", status="ok",
                                              extra={"order_id": str(oid), "ts": ts})
                            try:
                                from core.storage import update_action_status_for_order  # type: ignore
                                update_action_status_for_order(str(oid), "filled")
                            except Exception:
                                pass
                        except Exception:
                            pass
                        inserted += 1
                except Exception:
                    continue
        except Exception:
            inserted = 0

        if inserted > 0:
            self._log("deals_sync", {"inserted": inserted})
