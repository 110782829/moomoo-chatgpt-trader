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


def _fetch_bars(symbol: str, period: str = "6mo", interval: str = "1d") -> tuple[list[float], list[float], list[float]]:
    if yf is None:
        return [], [], []
    try:
        import contextlib, io as _io
        yf_sym = symbol.replace("US.", "")
        # Suppress noisy stderr from yfinance (e.g., delisted tickers)
        with contextlib.redirect_stderr(_io.StringIO()):
            try:
                df = yf.download(yf_sym, period=period, interval=interval, auto_adjust=True, progress=False, raise_errors=False)  # type: ignore[call-arg]
            except TypeError:
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

        # Periodic broker deal sync (to keep local mirror authoritative)
        self.deal_sync_sec: int = int(os.getenv("AUTOPILOT_DEALS_SYNC_SEC", "180") or "180")
        self._last_deal_sync_ts: float = 0.0

        # Throttle low-confidence planned logs per symbol
        self._low_conf_log_ts: Dict[str, float] = {}

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
            used_fallback = False
            # cache by sym and ttl
            if sym in getattr(self, "_feat_cache_ts", {}) and (now_ts - self._feat_cache_ts.get(sym, 0.0) < bars_ttl):
                feat = self._feat_cache.get(sym, {})
                if feat:
                    universe.append(dict(feat))
                    continue
            try:
                from core.market_data import get_bars_safely  # type: ignore
                bars, _source = get_bars_safely(c, sym, ktype_val, 220)
                for b in bars:
                    h = b.get("high", b.get("High", 0.0))
                    l = b.get("low", b.get("Low", 0.0))
                    cl = b.get("close", b.get("Close", 0.0))
                    try:
                        highs.append(float(h or 0.0))
                        lows.append(float(l or 0.0))
                        closes.append(float(cl or 0.0))
                    except Exception:
                        continue
            except Exception:
                used_fallback = True
                h2, l2, c2 = _fetch_bars(sym, period="6mo", interval="1d")
                highs, lows, closes = h2 or [], l2 or [], c2 or []

            if not closes:
                universe.append({
                    "sym": sym, "px": 0.0, "atr": 0.0, "rsi": 50, "ma50": 0.0, "ma200": 0.0, "trend": "flat",
                })
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
            feat = {
                "sym": sym, "px": px, "atr": atr_val, "rsi": rsi_val,
                "ma50": ma50, "ma200": ma200, "trend": trend,
                "atr_pct": atr_pct, "dist_ma50_pct": dist_ma50_pct, "dist_ma200_pct": dist_ma200_pct,
                "change_1d_pct": change_1d_pct, "pct_rank_52w": pct_rank_52w,
                # carry series for downstream signal generators (kept small ~220)
                "_highs": list(highs), "_lows": list(lows), "_closes": list(closes),
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
                    # obtain series (prefer yfinance-derived earlier)
                    highs: List[float] = u.get("_highs") if isinstance(u.get("_highs"), list) else []  # type: ignore
                    lows: List[float] = u.get("_lows") if isinstance(u.get("_lows"), list) else []   # type: ignore
                    closes: List[float] = u.get("_closes") if isinstance(u.get("_closes"), list) else []  # type: ignore
                    # When _fetch_bars failed, universe may not carry series; skip
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

        # recompute aggregate strengths after augmentation
        sig_strength = {}
        for s in signals:
            sym = str(s.get("sym") or "")
            if not sym:
                continue
            try:
                sig_strength[sym] = sig_strength.get(sym, 0.0) + float(s.get("strength") or 0.0)
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
            # expose signal weights for explainability
            "signal_weights": signals_weights,
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
                               "status": str(order.status.value)})
            if _HAS_STORAGE:
                try:
                    insert_action_log("autopilot_act", mode="auto",
                                      symbol=sym, side=side.upper(), qty=(int(spec.size_value) if spec.size_type=="shares" else est_qty), price=limit_price,
                                      reason=("order_augmented" if auto_augmented else "order"), status=str(order.status.value),
                                      extra={
                                          "order_id": order.order_id,
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
                        exec_service.place_order(tp_spec, ctx_exec)
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
                        exec_service.place_order(sp_spec, ctx_exec)
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
                        inserted += 1
                except Exception:
                    continue
        except Exception:
            inserted = 0

        if inserted > 0:
            self._log("deals_sync", {"inserted": inserted})
