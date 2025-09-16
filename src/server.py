'''
Start command: uvicorn --app-dir src server:app --reload --port 8000
'''
import re
from fastapi import FastAPI, HTTPException, APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Dict, Any 
import os
import json
from datetime import datetime
from pathlib import Path

from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf

try:
    from dotenv import load_dotenv
    # Load default .env from current working directory
    load_dotenv()
    # Also try project-root .env relative to this file (src/.. /.env)
    try:
        ROOT_ENV = Path(__file__).resolve().parent.parent / ".env"
        if ROOT_ENV.exists():
            load_dotenv(dotenv_path=str(ROOT_ENV), override=False)
    except Exception:
        pass
except Exception:
    pass

try:
    from execution.container import init_execution, get_execution, set_mode
except Exception:
    init_execution = lambda *a, **k: None  # type: ignore
    def get_execution():
        return None
    def set_mode(_: str) -> None:
        pass
try:
    from routers import exec_orders as exec_orders_router
except Exception:
    exec_orders_router = None  # type: ignore


# --- Internal modules ---
from core.market_data import get_bars_safely
from core.moomoo_client import MoomooClient
from core.deals import fetch_deals
from moomoo import TrdEnv
from core.session import load_session, save_session, clear_session, reconnect_from_session
from risk.limits import enforce_order_limits

# Automation (scheduler + storage + strategy step)
try:
    from core.storage import (
        init_db,
        insert_strategy,
        set_strategy_active,
        get_strategy,
        list_strategies,
        list_runs,
        update_strategy,
        record_fill,
        pnl_today,
        pnl_history,
        insert_action_log,
        list_action_logs,
        get_setting,
        set_setting,
    )
    from core.scheduler import TraderScheduler
    from strategies.ma_crossover import step as ma_crossover_step
    _AUTOMATION_AVAILABLE = True
except Exception as _e:
    _AUTOMATION_AVAILABLE = False
    _AUTOMATION_IMPORT_ERR = _e
    TraderScheduler = None  # type: ignore[misc]

# Backtest modules
try:
    from backtest.engine import load_bars_csv, run_ma_crossover
    _BACKTEST_AVAILABLE = True
    _BACKTEST_IMPORT_ERR = None
except Exception as _be:
    _BACKTEST_AVAILABLE = False
    _BACKTEST_IMPORT_ERR = _be

try:
    from backtest.grid import run_ma_grid
    _GRID_AVAILABLE = True
    _GRID_IMPORT_ERR = None
except Exception as _ge:
    _GRID_AVAILABLE = False
    _GRID_IMPORT_ERR = _ge


# ---------- App + CORS ----------

app = FastAPI(title="Moomoo ChatGPT Trader API")
init_execution(app)  # initialize execution container (broker-backed)
if exec_orders_router is not None:
    app.include_router(exec_orders_router.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Assistant Chat (OpenAI-backed) ----------
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    include_context: Optional[bool] = True

@app.post("/assistant/chat")
def assistant_chat(body: ChatRequest):
    # Build a concise context block for the assistant
    ctx_lines: List[str] = []
    if body.include_context:
        try:
            mgr = _get_autopilot()
            st = mgr.status()
            last_in = mgr.last_input or {}
            acct = (last_in.get("account") or {}) if isinstance(last_in, dict) else {}
            pos = (last_in.get("positions") or []) if isinstance(last_in, dict) else []
            orders = (last_in.get("orders") or []) if isinstance(last_in, dict) else []
            # Account snapshot
            eq = float(acct.get("equity") or 0.0); bp = float(acct.get("bp") or 0.0)
            cash = float(acct.get("cash") or 0.0); uc = float(acct.get("unsettled_cash") or 0.0)
            pnl = float(acct.get("pnl_today") or 0.0)
            ctx_lines.append(f"account: equity=${eq:,.0f} bp=${bp:,.0f} cash=${cash:,.0f} unsettled=${uc:,.0f} pnl_today=${pnl:,.0f}")
            # Top positions by abs MV if we have prices
            mv_map = {u.get('sym'): float(u.get('px') or 0.0) for u in (last_in.get('universe') or []) if isinstance(u, dict) and u.get('sym')}
            try:
                top = sorted([
                    (str(p.get('sym')), abs(float(p.get('qty') or 0.0)) * float(mv_map.get(str(p.get('sym')), 0.0)))
                    for p in pos if isinstance(p, dict) and p.get('sym')
                ], key=lambda x: x[1], reverse=True)[:8]
            except Exception:
                top = []
            if top:
                ctx_lines.append("positions: " + ", ".join([f"{s}:{w:.0f}" for s,w in top]))
            # Open orders summary
            try:
                oo = [o for o in orders if isinstance(o, dict) and str(o.get('status','')).lower() not in ('filled','done','cancelled','canceled','rejected','expired','failed')]
                if oo:
                    ctx_lines.append("open_orders: " + ", ".join([f"{o.get('sym')} {o.get('side')} {o.get('qty')} @ {o.get('price')} ({o.get('status')})" for o in oo[:8]]))
            except Exception:
                pass
            # Settings snapshot (planner prefs)
            try:
                prefs = (last_in.get("prefs") or {}) if isinstance(last_in, dict) else {}
                planner = (last_in.get("planner") or {}) if isinstance(last_in, dict) else {}
                mc = planner.get("min_confidence"); tn = planner.get("top_n"); sp = planner.get("strict_prefs")
                if prefs:
                    bits = []
                    if prefs.get("stop_loss_pct"): bits.append(f"stop {prefs.get('stop_loss_pct')}%")
                    if prefs.get("take_profit_pct"): bits.append(f"tp {prefs.get('take_profit_pct')}%")
                    if prefs.get("measured_move_atr_mult"): bits.append(f"mm {prefs.get('measured_move_atr_mult')}x ATR")
                    if bits:
                        ctx_lines.append("prefs: " + ", ".join(bits))
                ctx_lines.append("planner: " + ", ".join([
                    f"min_conf {mc}" if mc is not None else None,
                    f"top_n {tn}" if tn is not None else None,
                    "strict_prefs" if sp else None,
                ]).replace("None, ", "").strip(" ,"))
            except Exception:
                pass
            # Planner notes, if any
            if getattr(mgr, 'last_notes', None):
                ctx_lines.append("notes: " + str(getattr(mgr, 'last_notes'))[:240])
        except Exception:
            pass
        # Fallback: fetch directly from broker + settings if manager context is missing
        try:
            if not ctx_lines or (not pos and not orders):
                c = get_client()
                if c is not None and getattr(c, "connected", False):
                    try:
                        ai = c.get_account_assets()
                        ctx_lines.append(f"account: equity=${float(ai.get('equity') or 0):,.0f} bp=${float(ai.get('bp') or 0):,.0f} cash=${float(ai.get('cash') or 0):,.0f}")
                    except Exception:
                        pass
                    try:
                        P = c.get_positions() or []
                        # rough top 5 by mv using quote-less avg*qty if price not present
                        top_syms = []
                        for r in P[:8]:
                            sym = str(r.get('code') or r.get('stock_code') or r.get('symbol') or '')
                            qty = float(r.get('qty') or r.get('qty_total') or r.get('qty_today') or 0.0)
                            top_syms.append((sym, abs(qty)))
                        if top_syms:
                            ctx_lines.append("positions: " + ", ".join([f"{s}:{int(q)}" for s,q in top_syms if s][:8]))
                    except Exception:
                        pass
                    try:
                        O = c.get_orders() or []
                        oo = []
                        for r in O:
                            stat = str(r.get('order_status') or r.get('status') or '').lower()
                            if stat in ('filled','done','cancelled','canceled','rejected','expired','failed'):
                                continue
                            sym = str(r.get('code') or r.get('stock_code') or r.get('symbol') or '')
                            side = str(r.get('trd_side') or r.get('side') or '').upper()
                            qty = float(r.get('qty') or r.get('initial_qty') or 0.0)
                            price = float(r.get('price') or r.get('order_price') or 0.0)
                            if sym:
                                oo.append(f"{sym} {'BUY' if 'BUY' in side else 'SELL'} {int(qty)} @ {price or '-'}")
                        if oo:
                            ctx_lines.append("open_orders: " + ", ".join(oo[:8]))
                    except Exception:
                        pass
                # Execution container (SIM) fallback for positions/orders
                try:
                    exec_service = get_execution()
                except Exception:
                    exec_service = None
                if exec_service is not None:
                    try:
                        P2 = exec_service.list_positions() or []
                        top2 = []
                        for r in P2:
                            sym = str(r.get('symbol') or r.get('sym') or '')
                            qty = float(r.get('qty') or 0.0)
                            if sym:
                                top2.append((sym, abs(qty)))
                        if top2:
                            ctx_lines.append("positions(sim): " + ", ".join([f"{s}:{int(q)}" for s,q in top2][:8]))
                    except Exception:
                        pass
                    try:
                        O2 = exec_service.list_orders(limit=50) or []
                        oo2 = []
                        for o in O2:
                            st = str(o.get('status') or '').lower()
                            if st in ('filled','done','cancelled','canceled','rejected','expired','failed'):
                                continue
                            sym = str(o.get('symbol') or '')
                            side = str(o.get('side') or '')
                            qty = float(o.get('requested_qty') or o.get('qty') or 0.0)
                            px = o.get('limit_price') or o.get('avg_fill_price') or ''
                            if sym:
                                oo2.append(f"{sym} {side.upper()} {int(qty)} @ {px or '-'}")
                        if oo2:
                            ctx_lines.append("open_orders(sim): " + ", ".join(oo2[:8]))
                    except Exception:
                        pass
            # Settings snapshot (DB) if planner missing
            try:
                prefs_db = _get_json_setting("autopilot.prefs", {}) or {}
                mc_db = _get_json_setting("autopilot.min_confidence", None)
                tn_db = _get_json_setting("autopilot.top_n", None)
                sp_db = _get_json_setting("autopilot.strict_prefs", None)
                bits = []
                if prefs_db.get('stop_loss_pct'): bits.append(f"stop {prefs_db.get('stop_loss_pct')}%")
                if prefs_db.get('take_profit_pct'): bits.append(f"tp {prefs_db.get('take_profit_pct')}%")
                if prefs_db.get('measured_move_atr_mult'): bits.append(f"mm {prefs_db.get('measured_move_atr_mult')}x ATR")
                if bits:
                    ctx_lines.append("prefs(db): " + ", ".join(bits))
                planner_bits = []
                if mc_db is not None: planner_bits.append(f"min_conf {mc_db}")
                if tn_db is not None: planner_bits.append(f"top_n {tn_db}")
                if sp_db: planner_bits.append("strict_prefs")
                if planner_bits:
                    ctx_lines.append("planner(db): " + ", ".join(planner_bits))
            except Exception:
                pass
        except Exception:
            pass

    # Memory: load conversation + persistent memory
    chat_log: list[dict] = []
    memory_text: str = ""
    try:
        chat_log = _get_json_setting("assistant.chat", []) or []
        mem = _get_json_setting("assistant.memory", "") or ""
        memory_text = str(mem)
    except Exception:
        chat_log = []
        memory_text = ""

    system = (
        "You are the trading assistant for the Moomoo ChatGPT Trading Bot in this app.\n"
        "- Be concise and clear (2–6 sentences).\n"
        "- You can read the bot's settings and state from the provided context;\n"
        "  when the user asks to change settings, the backend applies them.\n"
        "  Acknowledge changes instead of saying you cannot modify settings.\n"
        "- Use the context to answer concretely (e.g., show weights, prefs, toggles).\n"
        "- Do not place orders here; focus on explanations, risk and next steps.\n"
        "- Prefer concrete steps (levels, stops/takes, what to monitor)."
    )
    if memory_text:
        system += "\nPersistent user memory (instructions/preferences):\n" + memory_text
    if ctx_lines:
        system += "\nContext:\n" + "\n".join(ctx_lines)

    # Build chat call
    try:
        # Apply simple commands (live settings changes)
        _actions: list[str] = []
        try:
            joined = "\n".join([m.content for m in body.messages if m.role == 'user'])
            _actions = _apply_simple_commands(joined)
        except Exception:
            _actions = []

        # Persist this turn in chat log
        now = datetime.utcnow().isoformat()
        for m in body.messages[-3:]:  # store last 3 inputs each call to reduce bloat
            chat_log.append({"ts": now, "role": m.role, "content": m.content})
        # Keep last 80 messages total
        chat_log = chat_log[-200:]
        _set_json_setting("assistant.chat", chat_log)

        # If commands applied, append operator notes to system so model acknowledges
        if _actions:
            try:
                system += "\n(Operator notes: " + ", ".join(_actions) + ")\n"
            except Exception:
                pass

        # Build ChatGPT-like memory by including tail of conversation
        tail = _conversation_tail(16)
        new_msgs = [{"role": m.role, "content": m.content} for m in body.messages]
        messages = [{"role": "system", "content": system}] + tail + new_msgs
        out = _openai_chat_msgs(messages)
        if not out:
            raise RuntimeError("assistant unavailable")
        reply = out.strip()

        # Update memory by extracting trading directives from recent turns (skip chit-chat)
        mem_changed = False
        try:
            recent_user = "\n".join([str(m.get("content")) for m in chat_log[-40:] if m.get("role") == "user"])[:4000]
            if recent_user:
                summary = _extract_style_directives(recent_user)
                if summary:
                    _set_json_setting("assistant.memory", summary)
                    old_style = _get_json_setting("autopilot.style_summary", "") or ""
                    merged = _merge_lines(old_style, summary)
                    cleaned = _clean_style_summary(merged)
                    mem_changed = (cleaned != old_style)
                    _set_json_setting("autopilot.style_summary", cleaned)
        except Exception:
            pass

        # Persist assistant reply to chat log so history survives reloads
        try:
            log2 = _get_json_setting("assistant.chat", []) or []
            log2.append({"ts": datetime.utcnow().isoformat(), "role": "assistant", "content": reply, "saved": bool(mem_changed), "settingsApplied": bool(_actions and len(_actions)>0)})
            log2 = log2[-200:]
            _set_json_setting("assistant.chat", log2)
        except Exception:
            pass

        if _actions:
            reply = "Applied: " + ", ".join(_actions) + "\n\n" + reply
        return {"reply": reply, "memory": memory_text, "actions": _actions}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/assistant/chat_stream")
def assistant_chat_stream(q: str, include_context: bool = True):
    # Build the same system prompt & context
    body = ChatRequest(messages=[ChatMessage(role="user", content=q)], include_context=include_context)
    # Reuse logic from non-stream for context + memory + commands
    ctx_lines: List[str] = []
    try:
        mgr = _get_autopilot()
        st = mgr.status()
        last_in = mgr.last_input or {}
        acct = (last_in.get("account") or {}) if isinstance(last_in, dict) else {}
        pos = (last_in.get("positions") or []) if isinstance(last_in, dict) else []
        orders = (last_in.get("orders") or []) if isinstance(last_in, dict) else []
        eq = float(acct.get("equity") or 0.0); bp = float(acct.get("bp") or 0.0)
        cash = float(acct.get("cash") or 0.0); uc = float(acct.get("unsettled_cash") or 0.0)
        pnl = float(acct.get("pnl_today") or 0.0)
        ctx_lines.append(f"account: equity=${eq:,.0f} bp=${bp:,.0f} cash=${cash:,.0f} unsettled=${uc:,.0f} pnl_today=${pnl:,.0f}")
        mv_map = {u.get('sym'): float(u.get('px') or 0.0) for u in (last_in.get('universe') or []) if isinstance(u, dict) and u.get('sym')}
        try:
            top = sorted([(str(p.get('sym')), abs(float(p.get('qty') or 0.0)) * float(mv_map.get(str(p.get('sym')), 0.0))) for p in pos if isinstance(p, dict) and p.get('sym')], key=lambda x: x[1], reverse=True)[:8]
        except Exception:
            top = []
        if top: ctx_lines.append("positions: " + ", ".join([f"{s}:{w:.0f}" for s,w in top]))
        try:
            oo = [o for o in orders if isinstance(o, dict) and str(o.get('status','')).lower() not in ('filled','done','cancelled','canceled','rejected','expired','failed')]
            if oo:
                ctx_lines.append("open_orders: " + ", ".join([f"{o.get('sym')} {o.get('side')} {o.get('qty')} @ {o.get('price')} ({o.get('status')})" for o in oo[:8]]))
        except Exception:
            pass
        if getattr(mgr, 'last_notes', None):
            ctx_lines.append("notes: " + str(getattr(mgr, 'last_notes'))[:240])
    except Exception:
        pass
    # Fallbacks if manager context is light or lacks assets and activity
    try:
        needs_more = False
        try:
            needs_more = (eq <= 0 and bp <= 0 and cash <= 0 and uc <= 0 and not pos and not orders)
        except Exception:
            needs_more = not ctx_lines
        if not ctx_lines or needs_more:
            c = get_client()
            if c is not None and getattr(c, "connected", False):
                try:
                    ai = c.get_account_assets()
                    ctx_lines.append(f"account: equity=${float(ai.get('equity') or 0):,.0f} bp=${float(ai.get('bp') or 0):,.0f} cash=${float(ai.get('cash') or 0):,.0f}")
                except Exception:
                    pass
                try:
                    P = c.get_positions() or []
                    top_syms = []
                    for r in P[:8]:
                        sym = str(r.get('code') or r.get('stock_code') or r.get('symbol') or '')
                        qty = float(r.get('qty') or r.get('qty_total') or r.get('qty_today') or 0.0)
                        top_syms.append((sym, abs(qty)))
                    if top_syms:
                        ctx_lines.append("positions: " + ", ".join([f"{s}:{int(q)}" for s,q in top_syms if s][:8]))
                except Exception:
                    pass
                try:
                    O = c.get_orders() or []
                    oo = []
                    for r in O:
                        stat = str(r.get('order_status') or r.get('status') or '').lower()
                        if stat in ('filled','done','cancelled','canceled','rejected','expired','failed'):
                            continue
                        sym = str(r.get('code') or r.get('stock_code') or r.get('symbol') or '')
                        side = str(r.get('trd_side') or r.get('side') or '').upper()
                        qty = float(r.get('qty') or r.get('initial_qty') or 0.0)
                        price = float(r.get('price') or r.get('order_price') or 0.0)
                        if sym:
                            oo.append(f"{sym} {'BUY' if 'BUY' in side else 'SELL'} {int(qty)} @ {price or '-'}")
                    if oo:
                        ctx_lines.append("open_orders: " + ", ".join(oo[:8]))
                except Exception:
                    pass
            # Execution container (SIM) fallback
            try:
                exec_service = get_execution()
            except Exception:
                exec_service = None
            if exec_service is not None:
                try:
                    P2 = exec_service.list_positions() or []
                    top2 = []
                    for r in P2:
                        sym = str(r.get('symbol') or r.get('sym') or '')
                        qty = float(r.get('qty') or 0.0)
                        if sym:
                            top2.append((sym, abs(qty)))
                    if top2:
                        ctx_lines.append("positions(sim): " + ", ".join([f"{s}:{int(q)}" for s,q in top2][:8]))
                except Exception:
                    pass
                try:
                    O2 = exec_service.list_orders(limit=50) or []
                    oo2 = []
                    for o in O2:
                        st = str(o.get('status') or '').lower()
                        if st in ('filled','done','cancelled','canceled','rejected','expired','failed'):
                            continue
                        sym = str(o.get('symbol') or '')
                        side = str(o.get('side') or '')
                        qty = float(o.get('requested_qty') or o.get('qty') or 0.0)
                        px = o.get('limit_price') or o.get('avg_fill_price') or ''
                        if sym:
                            oo2.append(f"{sym} {side.upper()} {int(qty)} @ {px or '-'}")
                    if oo2:
                        ctx_lines.append("open_orders(sim): " + ", ".join(oo2[:8]))
                except Exception:
                    pass
        # Settings from DB
        try:
            prefs_db = _get_json_setting("autopilot.prefs", {}) or {}
            mc_db = _get_json_setting("autopilot.min_confidence", None)
            tn_db = _get_json_setting("autopilot.top_n", None)
            sp_db = _get_json_setting("autopilot.strict_prefs", None)
            bits = []
            if prefs_db.get('stop_loss_pct'): bits.append(f"stop {prefs_db.get('stop_loss_pct')}%")
            if prefs_db.get('take_profit_pct'): bits.append(f"tp {prefs_db.get('take_profit_pct')}%")
            if prefs_db.get('measured_move_atr_mult'): bits.append(f"mm {prefs_db.get('measured_move_atr_mult')}x ATR")
            if bits:
                ctx_lines.append("prefs(db): " + ", ".join(bits))
            planner_bits = []
            if mc_db is not None: planner_bits.append(f"min_conf {mc_db}")
            if tn_db is not None: planner_bits.append(f"top_n {tn_db}")
            if sp_db: planner_bits.append("strict_prefs")
            if planner_bits:
                ctx_lines.append("planner(db): " + ", ".join(planner_bits))
            # feature toggles summary
            try:
                news = _get_json_setting("autopilot.use_news", None)
                sigs = _get_json_setting("autopilot.signals.enabled", None)
                autow = _get_json_setting("autopilot.signals.auto_weight", None)
                disc = _get_json_setting("autopilot.discovery_enabled", None)
                diso = _get_json_setting("autopilot.discovery_only", None)
                weights_raw = _get_json_setting("autopilot.signals.weights", {}) or {}
                toggles = []
                if news is not None: toggles.append(f"news={'on' if news else 'off'}")
                if sigs is not None: toggles.append(f"signals={'on' if sigs else 'off'}")
                if autow is not None: toggles.append(f"auto_weight={'on' if autow else 'off'}")
                if disc is not None: toggles.append(f"discovery={'on' if disc else 'off'}")
                if diso is not None: toggles.append(f"discovery_only={'on' if diso else 'off'}")
                if toggles:
                    ctx_lines.append("toggles(db): " + ", ".join(toggles))
                # summarize top weights
                try:
                    if isinstance(weights_raw, dict) and weights_raw:
                        items = list(weights_raw.items())
                        items.sort(key=lambda kv: float(kv[1] or 0), reverse=True)
                        top = ", ".join([f"{k}={float(v):.2f}" for k,v in items[:6]])
                        if top:
                            ctx_lines.append("weights(db): " + top)
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            pass
    except Exception:
        pass

    chat_log = _get_json_setting("assistant.chat", []) or []
    memory_text = str(_get_json_setting("assistant.memory", "") or "")
    system = (
        "You are the trading assistant for the Moomoo ChatGPT Trading Bot in this app.\n"
        "- Be concise and clear (2–6 sentences).\n"
        "- You can read the bot's settings and state from the provided context;\n"
        "  when the user asks to change settings, the backend applies them.\n"
        "  Acknowledge changes instead of saying you cannot modify settings.\n"
        "- Use the context to answer concretely (e.g., show weights, prefs, toggles).\n"
        "- Do not place orders here; focus on explanations, risk and next steps.\n"
        "- Prefer concrete steps (levels, stops/takes, what to monitor)."
    )
    if memory_text:
        system += "\nPersistent user memory (instructions/preferences):\n" + memory_text
    if ctx_lines:
        system += "\nContext:\n" + "\n".join(ctx_lines)

    # Apply commands immediately
    actions = _apply_simple_commands(q or "")
    if actions:
        system += "\n(Operator notes: " + ", ".join(actions) + ")\n"

    # Persist turn
    try:
        now = datetime.utcnow().isoformat()
        chat_log.append({"ts": now, "role": "user", "content": q})
        chat_log = chat_log[-200:]
        _set_json_setting("assistant.chat", chat_log)
    except Exception:
        pass

    def _gen():
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        if not api_key:
            yield "data: assistant unavailable\n\n"
            yield "data: __END__\n\n"
            return
        import requests, json as _json
        import time as _t
        started = _t.time()
        tail = _conversation_tail(16)
        payload = {
            "model": model,
            "messages": [{"role": "system", "content": system}] + tail + [{"role": "user", "content": q}],
            "temperature": 0.2,
            "stream": True,
        }
        try:
            with requests.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json=payload, stream=True, timeout=float(os.getenv("OPENAI_TIMEOUT", "15"))) as r:
                r.raise_for_status()
                full = []
                for line in r.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data = line[len("data: "):]
                        if data.strip() == "[DONE]":
                            break
                        try:
                            obj = _json.loads(data)
                            delta = obj.get("choices", [{}])[0].get("delta", {}).get("content")
                            if delta:
                                full.append(delta)
                                yield f"data: {delta}\n\n"
                        except Exception:
                            continue
                # Summarize to memory after completion
                mem_changed = False
                try:
                    joined_user = "\n".join([str(m.get("content")) for m in chat_log[-40:] if m.get("role") == "user"])[:4000]
                    if joined_user:
                        summary = _extract_style_directives(joined_user)
                        if summary:
                            _set_json_setting("assistant.memory", summary)
                            old_style = _get_json_setting("autopilot.style_summary", "") or ""
                            merged = _merge_lines(old_style, summary)
                            cleaned = _clean_style_summary(merged)
                            _set_json_setting("autopilot.style_summary", cleaned)
                            mem_changed = (cleaned != old_style)
                    # Persist assistant reply to chat log
                    try:
                        text = "".join(full)
                        now = datetime.utcnow().isoformat()
                        log = _get_json_setting("assistant.chat", []) or []
                        log.append({"ts": now, "role": "assistant", "content": text, "saved": bool(mem_changed), "settingsApplied": bool(actions and len(actions)>0)})
                        log = log[-200:]
                        _set_json_setting("assistant.chat", log)
                    except Exception:
                        pass
                except Exception:
                    pass
                # Emit actions applied (for client-side label) if there were commands
                try:
                    if actions:
                        yield "data: __ACTIONS__|" + _json.dumps(actions) + "\n\n"
                except Exception:
                    pass
        except Exception:
            yield "data: (stream error)\n\n"
            yield "data: __END__\n\n"
            return
        yield "data: __END__\n\n"

    return StreamingResponse(_gen(), media_type="text/event-stream")

@app.get("/assistant/memory")
def assistant_memory_get():
    memory = _get_json_setting("assistant.memory", "") or ""
    chat = _get_json_setting("assistant.chat", []) or []
    style = _get_json_setting("autopilot.style_summary", "") or ""
    try:
        cleaned = _clean_style_summary(style)
        if cleaned != style:
            _set_json_setting("autopilot.style_summary", cleaned)
            style = cleaned
    except Exception:
        pass
    return {"memory": memory, "style_summary": style, "chat_len": len(chat)}

@app.delete("/assistant/memory")
def assistant_memory_delete():
    _set_json_setting("assistant.memory", "")
    _set_json_setting("assistant.chat", [])
    return assistant_memory_get()

@app.post("/assistant/preset")
def assistant_preset(body: dict):
    preset = str(body.get("preset") or "").lower().strip()
    presets = {
        "al_brooks": "- al brooks price action (focus micro-trend, second entries, avoid midday chop)",
        "trend_follow": "- trend follow (momentum bias; add on pullbacks; avoid counter-trend opens)",
        "mean_revert": "- mean reversion (fade extremes; smaller size in high IV)",
        "long_bias": "- long bias (prefer buys)",
        "short_bias": "- short bias (prefer sells)",
    }
    if preset not in presets:
        raise HTTPException(status_code=400, detail="unknown preset")
    memory = _get_json_setting("assistant.memory", "") or ""
    memory2 = _merge_lines(memory, presets[preset])
    _set_json_setting("assistant.memory", memory2)
    style = _get_json_setting("autopilot.style_summary", "") or ""
    _set_json_setting("autopilot.style_summary", _merge_lines(style, presets[preset]))
    return assistant_memory_get()

@app.get("/assistant/chat_log")
def assistant_chat_log(limit: int = 200):
    log = _get_json_setting("assistant.chat", []) or []
    try:
        if isinstance(log, list):
            return {"messages": log[-int(limit):]}
    except Exception:
        pass
    return {"messages": []}

# ---- Style summary quick edit endpoints ----
@app.get("/assistant/style_lines")
def assistant_style_lines():
    style = _get_json_setting("autopilot.style_summary", "") or ""
    return {"lines": _style_lines(style)}

@app.post("/assistant/style_lines")
def assistant_style_add(body: dict):
    add = body.get("add") or []
    cur = _get_json_setting("autopilot.style_summary", "") or ""
    new = _merge_lines(cur, "\n".join([str(x) for x in add if str(x).strip()]))
    _set_json_setting("autopilot.style_summary", _clean_style_summary(new))
    return assistant_style_lines()

@app.delete("/assistant/style_lines")
def assistant_style_delete(body: dict):
    idxs = body.get("indexes") or []
    texts = body.get("texts") or []
    style = _get_json_setting("autopilot.style_summary", "") or ""
    L = _style_lines(style)
    rm_idx = {int(i) for i in (idxs or []) if isinstance(i, int) or str(i).isdigit()}
    rm_text = {str(t).strip().lower() for t in (texts or []) if str(t).strip()}
    out = []
    for i, l in enumerate(L):
        if i in rm_idx: continue
        if l.strip().lower() in rm_text: continue
        out.append(l)
    _set_json_setting("autopilot.style_summary", _clean_style_summary("\n".join(out)))
    return assistant_style_lines()

@app.put("/assistant/style_summary")
def assistant_style_summary_put(body: dict):
    """Directly set the style summary text (with cleaning and dedupe)."""
    text = str(body.get("text") or "")
    cleaned = _clean_style_summary(text)
    _set_json_setting("autopilot.style_summary", cleaned)
    return {"style_summary": cleaned}


# ---------- Globals ----------

# Global broker client instance; created on /connect
client: Optional[MoomooClient] = None

# Global scheduler (if automation imports are available)
scheduler = None  # will hold TraderScheduler


# ---------- Risk config (local file) ----------

RISK_PATH = Path(os.getenv("RISK_FILE", "data/risk.json"))
_DEFAULT_RISK = {
    "enabled": True,
    "max_usd_per_trade": 1000.0,
    "max_open_positions": 5,
    "max_daily_loss_usd": 200.0,
    "symbol_whitelist": [],  # empty → allow all
    "trading_hours_pt": {"start": "06:30", "end": "13:00"},  # US market regular hours (PT)
    "flatten_before_close_min": 5,
}

def _risk_load() -> dict:
    try:
        if RISK_PATH.exists():
            return json.loads(RISK_PATH.read_text())
    except Exception:
        pass
    RISK_PATH.parent.mkdir(parents=True, exist_ok=True)
    RISK_PATH.write_text(json.dumps(_DEFAULT_RISK, indent=2))
    return dict(_DEFAULT_RISK)

def _risk_save(cfg: dict) -> None:
    RISK_PATH.parent.mkdir(parents=True, exist_ok=True)
    RISK_PATH.write_text(json.dumps(cfg, indent=2))


# yfinance fetch helper
def fetch_yf(symbol: str):
    attempts = [
        {"period": "5d", "interval": "1m"},
        {"period": "1mo", "interval": "5m"},
        {"period": "1mo", "interval": "1d"},
    ]
    for kw in attempts:
        df = yf.download(symbol, progress=False, repair=True, **kw)
        if not df.empty:
            return df
    df = yf.Ticker(symbol).history(period="1mo", interval="1d")
    if not df.empty:
        return df
    raise HTTPException(502, f"yfinance empty for '{symbol}' (check ticker, interval, or network)")


# ---------- Request Models ----------

class ConnectRequest(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    client_id: Optional[int] = None

class SelectAccountRequest(BaseModel):
    account_id: str

class PlaceOrderRequest(BaseModel):
    symbol: str                 # e.g., "AAPL" or "US.AAPL"
    qty: float
    side: str                   # "BUY" or "SELL"
    order_type: str = "MARKET"  # "MARKET" or "LIMIT"
    price: Optional[float] = None

class CancelOrderRequest(BaseModel):
    order_id: str

class SubscribeQuotesRequest(BaseModel):
    symbols: list[str]

class UnlockTradeRequest(BaseModel):
    passcode: str

class FlattenRequest(BaseModel):
    symbols: Optional[List[str]] = None  # optional subset; if omitted, flatten all

class StartMACrossoverRequest(BaseModel):
    # core
    symbol: str              # e.g., "US.AAPL"
    fast: int = 20
    slow: int = 50
    ktype: str = "K_1M"      # bar timeframe; entitlement-dependent

    # sizing
    qty: float = 1
    size_mode: Optional[str] = "shares"   # 'shares' | 'usd'
    dollar_size: Optional[float] = 0.0

    # risk per-trade
    stop_loss_pct: Optional[float] = 0.0  # e.g. 0.02 = 2%
    take_profit_pct: Optional[float] = 0.0

    # run cadence / execution
    interval_sec: int = 15
    allow_real: bool = False


class UpdateStrategyRequest(BaseModel):
    # params
    fast: Optional[int] = None
    slow: Optional[int] = None
    ktype: Optional[str] = None
    qty: Optional[float] = None
    size_mode: Optional[str] = None          # 'shares' | 'usd'
    dollar_size: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    allow_real: Optional[bool] = None
    # meta
    interval_sec: Optional[int] = None
    active: Optional[bool] = None

class BacktestMARequest(BaseModel):
    symbol: str
    fast: int = 20
    slow: int = 50
    ktype: str = "K_1M"
    qty: float = 1.0
    size_mode: Optional[str] = "shares"   # 'shares' | 'usd'
    dollar_size: Optional[float] = 0.0
    stop_loss_pct: Optional[float] = 0.0
    take_profit_pct: Optional[float] = 0.0
    commission_per_share: Optional[float] = 0.0
    slippage_bps: Optional[float] = 0.0

class BacktestMAGridRequest(BaseModel):
    symbol: str
    ktype: str = "K_1M"
    fast_min: int = 5
    fast_max: int = 30
    fast_step: int = 5
    slow_min: int = 40
    slow_max: int = 200
    slow_step: int = 10
    qty: float = 1.0
    size_mode: Optional[str] = "shares"
    dollar_size: Optional[float] = 0.0
    stop_loss_pct: Optional[float] = 0.0
    take_profit_pct: Optional[float] = 0.0
    commission_per_share: Optional[float] = 0.0
    slippage_bps: Optional[float] = 0.0
    top_n: int = 10

class RiskConfig(BaseModel):
    enabled: Optional[bool] = None
    max_usd_per_trade: Optional[float] = None
    max_open_positions: Optional[int] = None
    max_daily_loss_usd: Optional[float] = None
    symbol_whitelist: Optional[list[str]] = None
    trading_hours_pt: Optional[dict] = None  # {"start":"06:30","end":"13:00"}
    flatten_before_close_min: Optional[int] = None

# ---: simple models for bot mode & flatten ---
class BotModeRequest(BaseModel):
    mode: str  # 'automatic' | 'manual'

class FlattenAllRequest(BaseModel):
    symbols: Optional[list[str]] = None  # if provided, only flatten these symbols


# ---------- Helpers ----------

def _two_mode() -> str:
    """
    Returns 'automatic' if Autopilot is ON, else 'manual'.
    Falls back to persisted bot_mode only to disambiguate when manager is unavailable.
    """
    try:
        mgr = _get_autopilot()
        st = mgr.status()
        if bool(st.get("on")):
            return "automatic"
        return "manual"
    except Exception:
        val = get_setting("bot_mode") or "manual"
        return "automatic" if str(val).lower().strip() == "automatic" else "manual"


def _env_from_str(name: str):
    return TrdEnv.SIMULATE if name.upper() == "SIMULATE" else TrdEnv.REAL

def set_client(c: Optional[MoomooClient]) -> None:
    """Set the singleton broker client."""
    global client
    client = c

def get_client() -> Optional[MoomooClient]:
    """Return the singleton broker client."""
    return client

# Wire execution container with client accessor and mode on import
try:
    from execution import container as exec_container  # type: ignore
    exec_container.set_client_accessor(get_client)  # type: ignore[attr-defined]
except Exception:
    pass


# ---------- App lifecycle (automation) ----------

@app.on_event("startup")
async def _on_startup():
    global scheduler
    try:
        c = reconnect_from_session()
        if c:
            set_client(c)
            try:
                set_mode("moomoo")
            except Exception:
                pass
    except Exception:
        pass
    if _AUTOMATION_AVAILABLE:
        init_db()
        scheduler = TraderScheduler(get_client)
        scheduler.register("ma_crossover", ma_crossover_step)
        scheduler.start()

@app.on_event("shutdown")
async def _on_shutdown():
    # Stop scheduler gracefully
    global scheduler
    if scheduler:
        await scheduler.stop()
        scheduler = None


# ---------- Routes ----------

@app.get("/")
def health_check():
    return {"status": "ok"}


@app.get("/debug/bars")
def debug_bars(symbol: str, ktype: str = "K_DAY", n: int = 120):
    """
    Fetch recent bars via unified provider to help diagnose planner idling.
    Returns source ('futu' or 'yfinance'), count, and last 3 rows.
    """
    try:
        c = get_client()
    except Exception:
        c = None
    try:
        bars, source = get_bars_safely(c, symbol, ktype, n)
        sample = bars[-3:] if isinstance(bars, list) else []
        return {
            "symbol": symbol,
            "ktype": ktype,
            "source": source,
            "count": (len(bars) if isinstance(bars, list) else 0),
            "last": sample,
        }
    except Exception as e:
        # expose error to help diagnose fetch issues
        return {"symbol": symbol, "ktype": ktype, "error": str(e)}


# --- Connection & accounts ---

@app.post("/connect")
def connect(req: ConnectRequest):
    """
    Connect to the OpenD gateway using host/port from request JSON
    or .env (MOOMOO_HOST/MOOMOO_PORT). Keeps a singleton client.
    """
    host = req.host or os.getenv("MOOMOO_HOST") or "127.0.0.1"
    port_raw = req.port or os.getenv("MOOMOO_PORT") or "11111"
    client_id = req.client_id or int(os.getenv("MOOMOO_CLIENT_ID", "1"))

    if not (host and host.strip()):
        raise HTTPException(status_code=400, detail="host empty")
    try:
        port = int(port_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="port not numeric")

    try:
        c = MoomooClient(host=host, port=port, client_id=client_id)
        c.connect()
        set_client(c)
        try:
            set_mode("moomoo")
        except Exception:
            pass
        # persist partial session (account may be None here)
        try:
            save_session(
                host,
                port,
                getattr(c, "account_id", None),
                getattr(c, "env", None).name if getattr(c, "env", None) else None,
                client_id,
            )
        except Exception:
            pass
        return {"status": "connected", "host": host, "port": port, "client_id": client_id}
    except (RuntimeError, TypeError) as e:
        set_client(None)
        raise HTTPException(status_code=400, detail=f"Failed to connect: {e}")
    except Exception as e:
        set_client(None)
        raise HTTPException(status_code=500, detail=f"Failed to connect: {e}")

@app.get("/accounts")
def list_accounts():
    """
    Return account IDs with trading env and type. Requires active connection.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return c.list_accounts()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list accounts: {e}")

@app.post("/accounts/select")
def select_account(req: SelectAccountRequest):
    """
    Select the active account. Env inferred from account list.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        info = next((a for a in c.list_accounts() if a.get("account_id") == req.account_id), None)
        if not info:
            raise RuntimeError("account not found")
        env = _env_from_str(info.get("trd_env", "SIMULATE"))
        c.set_account(req.account_id, env)
        try:
            save_session(
                c.host,
                c.port,
                c.account_id,
                c.env.name if c.env else None,
                getattr(c, "client_id", None),
            )
        except Exception:
            pass
        return {
            "status": "ok",
            "account_id": req.account_id,
            "trd_env": info.get("trd_env", "SIMULATE"),
            "account_type": info.get("account_type"),
        }
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to select account: {e}")

@app.get("/accounts/active")
def accounts_active():
    """
    Inspect currently selected account/env.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    info = None
    try:
        for a in c.list_accounts():
            if a.get("account_id") == str(c.account_id):
                info = a
                break
    except Exception:
        pass
    return {
        "account_id": c.account_id,
        "trd_env": "SIMULATE" if getattr(c, "env", None) == TrdEnv.SIMULATE else "REAL",
        "account_type": info.get("account_type") if info else None,
    }

@app.get("/accounts/info")
def account_info(account_id: str):
    """Get details for account_id."""
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return c.get_account_info(account_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get account info: {e}")

@app.get("/accounts/assets")
def accounts_assets():
    """
    Best-effort account assets snapshot to help verify the selected account.
    Queries broker via accinfo_query when available; falls back to estimating from
    broker positions if necessary.
    """
    # Prefer execution mode; if unavailable, infer from client
    try:
        from execution.container import get_mode, get_execution  # type: ignore
        mode = get_mode()
    except Exception:
        get_execution = lambda: None  # type: ignore
        c_try = None
        try:
            c_try = get_client()
        except Exception:
            pass
        mode = "moomoo" if c_try is not None and getattr(c_try, "connected", False) else "sim"

    if mode == "moomoo":
        c = get_client()
        if c is None or not getattr(c, "connected", False):
            raise HTTPException(status_code=400, detail="Not connected")
        try:
            info = c.get_account_assets()  # type: ignore[attr-defined]
            return {"mode": "moomoo", **info}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch broker assets: {e}")

    # Fallback: sum MV across broker-reported positions when asset API not available
    try:
        exec_service = get_execution()
    except Exception:
        exec_service = None
    equity = None
    if exec_service is not None and hasattr(exec_service, "list_positions"):
        try:
            poss = exec_service.list_positions() or []
            equity = sum(float(p.get("mv") or 0.0) for p in poss)
        except Exception:
            equity = None
    return {"mode": "sim", "equity": equity, "bp": None, "cash": None}

@app.get("/debug/accounts_raw")
def accounts_raw():
    """
    Raw passthrough of get_acc_list to help debug schema/signature differences.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        ret, df = c.trading_ctx.get_acc_list(trd_env=c.env)  # type: ignore[attr-defined]
    except TypeError:
        ret, df = c.trading_ctx.get_acc_list()  # type: ignore[attr-defined]
    if ret != 0:
        raise HTTPException(status_code=500, detail=f"get_acc_list failed: {df}")
    try:
        import pandas as pd
        if isinstance(df, pd.DataFrame):
            return df.to_dict(orient="records")
    except Exception:
        pass
    return df


# --- Trade unlock ---

@app.post("/trade/unlock")
def trade_unlock(req: UnlockTradeRequest):
    """Unlock trading with passcode."""
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return c.unlock_trade(req.passcode)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unlock: {e}")


# --- Positions & orders ---

@app.get("/positions")
def get_positions():
    """
    Return current positions for the active account.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return c.get_positions()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get positions: {e}")

@app.get("/orders")
def get_orders():
    """
    Return orders for the active account.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return c.get_orders()
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get orders: {e}")

@app.get("/orders/{order_id}")
def get_order(order_id: str):
    """
    Return a single order by ID.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return c.get_order(order_id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get order: {e}")

@app.post("/orders/place")
def place_order(req: PlaceOrderRequest):
    """
    Place a market or limit order for the active account (with risk checks).
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    if not c.account_id:
        raise HTTPException(status_code=400, detail="No account selected")

    side = (req.side or "").upper()
    if side not in {"BUY", "SELL"}:
        raise HTTPException(status_code=400, detail=f"Invalid side: {req.side}")

    order_type = (req.order_type or "MARKET").upper()
    if order_type not in {"MARKET", "LIMIT"}:
        raise HTTPException(status_code=400, detail=f"Invalid order_type: {req.order_type}")

    if order_type == "LIMIT" and (req.price is None or float(req.price) <= 0):
        raise HTTPException(status_code=400, detail="Limit order requires positive 'price'")

    qty = float(req.qty)
    if qty <= 0:
        raise HTTPException(status_code=400, detail="qty must be > 0")

    # Risk guardrails (raises ValueError when blocked)
    try:
        enforce_order_limits(
            client=c,
            symbol=req.symbol,
            qty=qty,
            side=side,
            order_type=order_type,
            price=req.price,
        )
    except ValueError as e:
        insert_action_log(
            "place", mode=_two_mode(),
            symbol=req.symbol, side=side, qty=qty, price=req.price,
            reason="risk_block", status="blocked", extra={"msg": str(e)}
        )
        raise HTTPException(status_code=400, detail=f"Blocked by risk: {e}")

    try:
        result = c.place_order(
            symbol=req.symbol,
            qty=qty,
            side=side,
            order_type=order_type,
            price=req.price,
        )
        insert_action_log(
            "place", mode=_two_mode(),
            symbol=req.symbol, side=side, qty=qty, price=req.price,
            reason="manual/place_order", status="ok", extra={"result": result}
        )
        return {"status": "ok", "result": result}
    except Exception as e:
        insert_action_log(
            "place", mode=_two_mode(),
            symbol=req.symbol, side=side, qty=qty, price=req.price,
            reason="exception", status="error", extra={"msg": str(e)}
        )
        raise HTTPException(status_code=500, detail=f"place_order failed: {e}")

@app.post("/orders/cancel")
def cancel_order(req: CancelOrderRequest):
    """
    Cancel an order by ID.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        res = c.cancel_order(req.order_id)
        insert_action_log("cancel", mode=_two_mode(),
                          symbol=None, side=None, qty=None, price=None,
                          reason=f"cancel {req.order_id}", status="ok", extra={"result": res})
        return res
    except RuntimeError as e:
        insert_action_log("cancel", mode=_two_mode(),
                          reason=f"runtime_error {req.order_id}", status="error", extra={"msg": str(e)})
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        insert_action_log("cancel", mode=_two_mode(),
                          reason=f"exception {req.order_id}", status="error", extra={"msg": str(e)})
        raise HTTPException(status_code=500, detail=f"Failed to cancel order: {e}")


# --- Quotes ---

@app.post("/quotes/subscribe")
def quotes_subscribe(req: SubscribeQuotesRequest):
    """
    Subscribe to basic quotes for one or more symbols.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return c.subscribe_quotes(req.symbols)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to subscribe quotes: {e}")

@app.get("/quotes/{symbol}")
def quotes_latest(symbol: str):
    """
    Get the latest quote for a symbol.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        return c.get_quote_latest(symbol)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get quote: {e}")


# ---- Execution mode (SIM | Moomoo) ----
class ExecMode(BaseModel):
    mode: str  # 'sim' | 'moomoo'


@app.get("/execution/mode")
def exec_mode_get():
    try:
        from execution.container import get_mode  # type: ignore
        mode = get_mode()
    except Exception:
        mode = "sim"
    return {"mode": mode}


@app.put("/execution/mode")
def exec_mode_put(body: ExecMode):
    mode = (body.mode or "sim").strip().lower()
    if mode not in {"sim","moomoo"}:
        raise HTTPException(status_code=400, detail="mode must be 'sim' or 'moomoo'")
    try:
        from execution.container import set_mode  # type: ignore
        set_mode(mode)
        insert_action_log("execution_mode", mode=_two_mode(), reason="user_update", status="ok", extra={"mode": mode})
    except Exception:
        pass
    return {"mode": mode}


# --- Sync deals + PnL ---

@app.post("/sync/deals")
def sync_deals(simulate_if_absent: bool = True):
    """Pull recent fills from broker and store them locally."""
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    try:
        recs, source = fetch_deals(c, simulate_if_absent)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    exec_service = get_execution()
    inserted = 0
    if exec_service and hasattr(exec_service, "sync_deals"):
        try:
            inserted = exec_service.sync_deals(recs)  # type: ignore[attr-defined]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"deal sync failed: {e}")
    else:
        for r in recs:
            record_fill(r["order_id"], r["symbol"], r["side"], r["qty"], r["price"], r["ts"])
            inserted += 1
    return {"status": "ok", "inserted": inserted, "source": source}

@app.get("/pnl/today")
def pnl_today_endpoint():
    """Realized PnL for today (computed from fills)."""
    try:
        return pnl_today()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute PnL: {e}")

@app.get("/pnl/history")
def pnl_history_endpoint(days: int = 7):
    """Realized PnL by day for the last N days."""
    try:
        return pnl_history(days=days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compute PnL history: {e}")


# --- Bot Mode (persisted in settings) ---

@app.get("/bot/mode")
def bot_mode_get():
    """
    Two-mode model: 'automatic' when Autopilot is ON, else 'manual'.
    Strict two-mode only: 'automatic' or 'manual'.
    """
    try:
        mgr = _get_autopilot()
        st = mgr.status()
        if bool(st.get("on")):
            return {"mode": "automatic"}
    except Exception:
        pass
    return {"mode": "manual"}

@app.put("/bot/mode")
async def bot_mode_put(req: BotModeRequest):
    """
    Set mode to 'automatic' or 'manual' and sync Autopilot accordingly.
    """
    mode_in = (req.mode or "").lower().strip()
    if mode_in not in {"automatic", "manual"}:
        raise HTTPException(status_code=400, detail="mode must be 'automatic' or 'manual'")

    # Persist the exact value (for transparency), though GET derives mode from Autopilot status.
    set_setting("bot_mode", mode_in)
    insert_action_log("mode_change", mode=mode_in, reason="user_update", status="ok")

    try:
        mgr = _get_autopilot()
        if mode_in == "automatic":
            await mgr.start()
        else:
            await mgr.stop()
    except Exception:
        # If Autopilot manager isn't available yet, GET will report 'manual' until running.
        pass

    return {"mode": mode_in}

@app.get("/logs/actions")
def action_logs(limit: int = 100, symbol: Optional[str] = None, since_hours: Optional[int] = None):
    """
    List recent action log entries for explainability/chronology.
    """
    try:
        return list_action_logs(limit=limit, symbol=symbol, since_hours=since_hours)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch action logs: {e}")


# --- Flatten All ---

@app.post("/positions/flatten")
def positions_flatten(body: FlattenAllRequest = FlattenAllRequest()):
    """
    Close all open positions by placing opposite MARKET orders.
    - Disallowed when account env is REAL (safety). Revisit with explicit flag later.
    """
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    if not c.account_id:
        raise HTTPException(status_code=400, detail="No account selected")
    if getattr(c, "env", None) == TrdEnv.REAL:
        insert_action_log("flatten", mode=_two_mode(),
                          reason="blocked_real_env", status="blocked")
        raise HTTPException(status_code=400, detail="Flatten disabled in REAL environment")

    try:
        pos = c.get_positions()
        if not isinstance(pos, list):
            pos = []
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch positions: {e}")

    target_symbols = set([s.strip() for s in (body.symbols or []) if s and s.strip()]) if body.symbols else None

    attempts = []
    for p in pos:
        code = p.get("code") or p.get("stock_code") or p.get("symbol")
        if not code:
            continue
        if target_symbols and code not in target_symbols:
            continue

        # best-effort qty detection across schemas
        qty = float(
            p.get("qty")
            or p.get("qty_today")
            or p.get("qty_total", 0)
            or 0
        )
        if qty == 0:
            continue

        side = "SELL" if qty > 0 else "BUY"
        try:
            res = c.place_order(symbol=code, qty=abs(qty), side=side, order_type="MARKET", price=None)
            attempts.append({"symbol": code, "qty": abs(qty), "side": side, "status": "ok", "result": res})
            insert_action_log("flatten", mode=_two_mode(),
                              symbol=code, side=side, qty=abs(qty),
                              reason="flatten_all", status="ok", extra={"result": res})
        except Exception as e:
            attempts.append({"symbol": code, "qty": abs(qty), "side": side, "status": "error", "error": str(e)})
            insert_action_log("flatten", mode=_two_mode(),
                              symbol=code, side=side, qty=abs(qty),
                              reason="exception", status="error", extra={"msg": str(e)})

    return {"status": "ok", "attempts": attempts}


# --- Automation: Strategies ---

@app.post("/automation/start/ma-crossover")
def automation_start_ma(req: StartMACrossoverRequest):
    """
    Start an MA crossover strategy instance (persisted in SQLite; picked up by scheduler).
    """
    if not _AUTOMATION_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail=f"Automation modules not available: {_AUTOMATION_IMPORT_ERR}",
        )
    c = get_client()
    if c is None or not c.connected:
        raise HTTPException(status_code=400, detail="Not connected")
    if scheduler is None:
        raise HTTPException(status_code=500, detail="Scheduler not available")
    if req.slow <= req.fast:
        raise HTTPException(status_code=400, detail="slow must be > fast")

    params = {
        "fast": int(req.fast),
        "slow": int(req.slow),
        "ktype": req.ktype,
        # sizing
        "qty": float(req.qty),
        "size_mode": (req.size_mode or "shares"),
        "dollar_size": float(req.dollar_size or 0),
        # risk
        "stop_loss_pct": float(req.stop_loss_pct or 0),
        "take_profit_pct": float(req.take_profit_pct or 0),
        # execution
        "allow_real": bool(req.allow_real),
    }
    
    sid = insert_strategy("ma_crossover", req.symbol.strip(), params, int(req.interval_sec))
    insert_action_log("start_strategy", mode=_two_mode(),
                      symbol=req.symbol.strip(), reason="ma_crossover", status="ok",
                      extra={"strategy_id": sid, "params": params})
    return {"status": "ok", "strategy_id": sid, "name": "ma_crossover", "symbol": req.symbol, "params": params}

@app.get("/automation/strategies")
def automation_list():
    """
    List all stored strategies with params and active flags.
    """
    if not _AUTOMATION_AVAILABLE:
        raise HTTPException(status_code=500, detail="Automation modules not available")
    return list_strategies()

@app.get("/automation/strategies/{strategy_id}")
def automation_get(strategy_id: int):
    """
    Get one strategy by id.
    """
    if not _AUTOMATION_AVAILABLE:
        raise HTTPException(status_code=500, detail="Automation modules not available")
    s = get_strategy(strategy_id)
    if not s:
        raise HTTPException(status_code=404, detail="strategy not found")
    return s

@app.patch("/automation/strategies/{strategy_id}")
def automation_update(strategy_id: int, req: UpdateStrategyRequest):
    """
    Update params/interval/active for a strategy.
    """
    if not _AUTOMATION_AVAILABLE:
        raise HTTPException(status_code=500, detail="Automation modules not available")

    p = {}
    for k in ["fast", "slow", "ktype", "qty", "size_mode", "dollar_size",
              "stop_loss_pct", "take_profit_pct", "allow_real"]:
        v = getattr(req, k)
        if v is not None:
            p[k] = v

    updated = update_strategy(
        strategy_id,
        params=p if p else None,
        interval_sec=req.interval_sec,
        active=req.active,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="strategy not found")
    insert_action_log("update_strategy", mode=_two_mode(),
                      reason=f"id={strategy_id}", status="ok", extra={"params": p, "interval_sec": req.interval_sec, "active": req.active})
    return updated

@app.get("/automation/strategies/{strategy_id}/runs")
def automation_runs(strategy_id: int, limit: int = 50):
    """
    Recent run records for a strategy.
    """
    if not _AUTOMATION_AVAILABLE:
        raise HTTPException(status_code=500, detail="Automation modules not available")
    if not get_strategy(strategy_id):
        raise HTTPException(status_code=404, detail="strategy not found")
    return list_runs(strategy_id, limit=limit)

@app.post("/automation/stop/{strategy_id}")
def automation_stop(strategy_id: int):
    """
    Stop a strategy (set active=0). The job remains stored; can re-activate later.
    """
    if not _AUTOMATION_AVAILABLE:
        raise HTTPException(status_code=500, detail="Automation modules not available")
    if not get_strategy(strategy_id):
        raise HTTPException(status_code=404, detail="strategy not found")
    set_strategy_active(strategy_id, False)
    insert_action_log("stop_strategy", mode=_two_mode(),
                      reason=f"id={strategy_id}", status="ok")
    return {"status": "ok", "strategy_id": strategy_id, "active": False}

@app.post("/automation/stop_all")
def automation_stop_all():
    """
    Stop all active strategies (set active=0 in SQLite).
    Works even if you are not connected to the broker.
    """
    if not _AUTOMATION_AVAILABLE:
        raise HTTPException(
            status_code=500,
            detail=f"Automation modules not available: {_AUTOMATION_IMPORT_ERR}",
        )

    rows = list_strategies()
    def _is_active(v):
        s = str(v).strip().lower()
        return v is True or s in {"1", "true", "yes"}

    stopped = 0
    for r in rows or []:
        if _is_active(r.get("active")):
            set_strategy_active(int(r["id"]), False)
            stopped += 1

    return {"status": "ok", "stopped": stopped}

@app.post("/automation/start/{strategy_id}")
def automation_reactivate(strategy_id: int):
    """
    Reactivate a previously stored strategy.
    """
    if not _AUTOMATION_AVAILABLE:
        raise HTTPException(status_code=500, detail="Automation modules not available")
    if not get_strategy(strategy_id):
        raise HTTPException(status_code=404, detail="strategy not found")
    set_strategy_active(strategy_id, True)
    insert_action_log("start_strategy", mode=_two_mode(),
                      reason=f"id={strategy_id}", status="ok")
    return {"status": "ok", "strategy_id": strategy_id, "active": True}


# --- Risk config & status ---

@app.get("/risk/config")
def risk_get():
    """
    Return current risk configuration (local file).
    """
    try:
        return _risk_load()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read risk config: {e}")

@app.put("/risk/config")
def risk_put(req: RiskConfig):
    """
    Update risk configuration (partial update).
    """
    try:
        cfg = _risk_load()
        for k, v in req.model_dump(exclude_none=True).items():
            cfg[k] = v
        _risk_save(cfg)
        return cfg
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save risk config: {e}")

@app.get("/risk/status")
def risk_status():
    """
    Basic runtime risk status: open positions count, config snapshot.
    """
    cfg = _risk_load()
    open_positions = None
    try:
        c = get_client()
        if c and c.connected:
            pos = c.get_positions()
            if isinstance(pos, list):
                open_positions = len(pos)
    except Exception:
        pass
    return {"ok": True, "config": cfg, "open_positions": open_positions}


# --- Session management ---

@app.get("/session/status")
def session_status():
    s = load_session()
    c = get_client()
    # env as string
    env_obj = getattr(c, "env", None)
    env_name = getattr(env_obj, "name", None)
    if env_name is None:
        if env_obj == TrdEnv.SIMULATE:
            env_name = "SIMULATE"
        elif env_obj == TrdEnv.REAL:
            env_name = "REAL"
    return {
        "saved": s or {},
        "connected": bool(c and getattr(c, "connected", False)),
        "active_account": {
            "account_id": getattr(c, "account_id", None),
            "trd_env": env_name,
        } if c else None,
    }

@app.post("/session/save")
def session_save_endpoint(body: dict):
    host = body.get("host")
    port = int(body.get("port", 0))
    client_id = body.get("client_id")
    account_id = body.get("account_id")
    trd_env = body.get("trd_env")
    if not host or not port:
        raise HTTPException(status_code=400, detail="host and port required")
    return {"ok": True, "saved": save_session(host, port, account_id, trd_env, client_id)}

@app.post("/session/clear")
def session_clear_endpoint():
    clear_session()
    return {"ok": True}


# --- Disconnect ---

@app.post("/disconnect")
def disconnect():
    """
    Disconnect and clear the global client.
    """
    c = get_client()
    if c is None:
        return {"status": "ok"}  # already clear
    try:
        c.disconnect()
    except Exception:
        pass  # ignore errors on shutdown
    set_client(None)
    try:
        set_mode("sim")
    except Exception:
        pass
    return {"status": "disconnected"}


# --- Backtest: single run ---

@app.post("/backtest/ma-crossover")
def backtest_ma(req: BacktestMARequest):
    """
    Run a local MA-crossover backtest using CSV bars in data/bars/{SYMBOL}_{KTYPE}.csv.
    Returns metrics and the first 20 trades.
    """
    if not _BACKTEST_AVAILABLE:
        raise HTTPException(status_code=500, detail=f"Backtest module not available: {_BACKTEST_IMPORT_ERR}")
    if req.slow <= req.fast:
        raise HTTPException(status_code=400, detail="slow must be > fast")
    try:
        bars = load_bars_csv(req.symbol, req.ktype)
        res = run_ma_crossover(
            bars=bars,
            fast=int(req.fast),
            slow=int(req.slow),
            qty=float(req.qty),
            size_mode=(req.size_mode or "shares"),
            dollar_size=float(req.dollar_size or 0),
            stop_loss_pct=float(req.stop_loss_pct or 0),
            take_profit_pct=float(req.take_profit_pct or 0),
            commission_per_share=float(req.commission_per_share or 0),
            slippage_bps=float(req.slippage_bps or 0),
        )
        trades = [{
            "entry_ts": t.entry_ts, "exit_ts": t.exit_ts, "side": t.side,
            "entry_px": t.entry_px, "exit_px": t.exit_px, "qty": t.qty, "pnl": t.pnl
        } for t in res.trades[:20]]
        return {"metrics": res.metrics, "trades_sample": trades}
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=400,
            detail=f"{e}. Put a CSV at data/bars/{req.symbol.split('.')[-1].upper()}_{req.ktype}.csv with columns time,open,high,low,close,volume"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest failed: {e}")


# --- Backtest: parameter grid ---

@app.post("/backtest/ma-grid")
def backtest_ma_grid(req: BacktestMAGridRequest):
    """
    Run an MA-crossover parameter sweep; returns top-N results by gross_pnl.
    """
    if not _BACKTEST_AVAILABLE:
        raise HTTPException(status_code=500, detail=f"Backtest module not available: {_BACKTEST_IMPORT_ERR}")
    if not _GRID_AVAILABLE:
        raise HTTPException(status_code=500, detail=f"Backtest grid not available: {_GRID_IMPORT_ERR}")
    try:
        bars = load_bars_csv(req.symbol, req.ktype)
        results = run_ma_grid(
            bars=bars,
            fast_min=req.fast_min, fast_max=req.fast_max, fast_step=req.fast_step,
            slow_min=req.slow_min, slow_max=req.slow_max, slow_step=req.slow_step,
            qty=float(req.qty),
            size_mode=(req.size_mode or "shares"),
            dollar_size=float(req.dollar_size or 0),
            stop_loss_pct=float(req.stop_loss_pct or 0),
            take_profit_pct=float(req.take_profit_pct or 0),
            commission_per_share=float(req.commission_per_share or 0),
            slippage_bps=float(req.slippage_bps or 0),
            top_n=int(req.top_n),
        )
        return {"count": len(results), "results": results}
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=400,
            detail=f"{e}. Put a CSV at data/bars/{req.symbol.split('.')[-1].upper()}_{req.ktype}.csv"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Backtest grid failed: {e}")


# --- Autopilot (planner/executor) scaffold ---
try:
    from autopilot.worker import AutopilotManager
    from autopilot import schemas as ap_schemas
    _AUTOPILOT_AVAILABLE = True
    _AUTOPILOT_IMPORT_ERR = None
except Exception as _ae:
    AutopilotManager = None  # type: ignore
    ap_schemas = None        # type: ignore
    _AUTOPILOT_AVAILABLE = False
    _AUTOPILOT_IMPORT_ERR = _ae

autopilot_router = APIRouter(prefix="/autopilot", tags=["autopilot"])

_autopilot_mgr = None  # lazy singleton

def _get_autopilot():
    global _autopilot_mgr
    if _autopilot_mgr is None:
        if not _AUTOPILOT_AVAILABLE:
            raise HTTPException(status_code=500, detail=f"Autopilot unavailable: {_AUTOPILOT_IMPORT_ERR}")
        # lazy-create manager; pass client accessor and risk-loader
        def _risk_loader():
            try:
                return _risk_load()
            except Exception:
                return {}
        _autopilot_mgr = AutopilotManager(get_client, _risk_loader, get_execution=get_execution)
    return _autopilot_mgr

@autopilot_router.post("/enable")
async def autopilot_enable(body: dict):
    """
    Enable/disable the Autopilot worker loop.
    Body: {"on": bool}
    """
    on = bool(body.get("on", False))
    mgr = _get_autopilot()
    if on:
        await mgr.start()
        return {"on": True, "status": "started"}
    else:
        await mgr.stop()
        return {"on": False, "status": "stopped"}

@autopilot_router.get("/status")
async def autopilot_status():
    try:
        mgr = _get_autopilot()
        st = mgr.status()
    except Exception as e:
        # Return a minimal status payload instead of 500 to aid debugging
        st = {"on": False, "last_tick": None, "last_decision": None, "stats": {}, "reject_streak": 0, "error": str(e)}
    # Enrich with performance stats and model info (best-effort)
    try:
        from core.storage import performance_stats, exits_coverage  # type: ignore
        perf = performance_stats(days=365)
        coverage = exits_coverage(since_hours=24)
        stats = dict(st.get("stats") or {})
        stats.update(perf)
        stats.update(coverage)
        # Surface model name for UI badge
        stats["model"] = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        st["stats"] = stats
    except Exception:
        pass
    # Planner meta for UI (provider + enabled)
    try:
        provider = (os.getenv("PLANNER_PROVIDER", "stub") or "stub").strip().lower()
        has_key = bool((os.getenv("OPENAI_API_KEY", "") or "").strip())
        effective = ("gpt" if (provider == "stub" and has_key) else provider)
        st["planner_info"] = {
            "provider": effective,
            "enabled": (effective == "gpt" and has_key),
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        }
    except Exception:
        pass
    return st

@autopilot_router.post("/preview")
async def autopilot_preview():
    """
    Run a single Sense→Think (no Act). Returns planner input, raw planner output, and validation details.
    """
    mgr = _get_autopilot()
    return await mgr.preview()

@autopilot_router.get("/context")
async def autopilot_context():
    mgr = _get_autopilot()
    return {"last_input": mgr.last_input or {}}

@autopilot_router.get("/last_output")
async def autopilot_last_output():
    mgr = _get_autopilot()
    return {"last_output": mgr.last_output or {}}

@autopilot_router.get("/last_diff")
async def autopilot_last_diff():
    try:
        mgr = _get_autopilot()
    except Exception:
        return {"proposed": [], "kept": [], "executed": []}
    try:
        proposed = getattr(mgr, "_last_proposed", []) or []
    except Exception:
        proposed = []
    try:
        kept = getattr(mgr, "_last_evaluated", []) or []
    except Exception:
        kept = []
    try:
        executed = getattr(mgr, "_last_executed", []) or []
    except Exception:
        executed = []
    try:
        note = getattr(mgr, "last_notes", None)
    except Exception:
        note = None
    return {"proposed": proposed[:12], "kept": kept[:12], "executed": executed[:12], "notes": note}

@autopilot_router.get("/env_debug")
def autopilot_env_debug():
    """Return minimal planner-related env info (sanitized) for troubleshooting."""
    provider = (os.getenv("PLANNER_PROVIDER", "stub") or "stub").strip().lower()
    has_key = bool((os.getenv("OPENAI_API_KEY", "") or "").strip())
    model = os.getenv("OPENAI_MODEL", None)
    effective = ("gpt" if (provider == "stub" and has_key) else provider)
    return {
        "provider_env": provider,
        "has_openai_key": has_key,
        "effective_provider": effective,
        "model": model,
        "json_mode": os.getenv("OPENAI_JSON_MODE", None),
        "fallback_stub": os.getenv("PLANNER_FALLBACK_STUB", None),
    }


@autopilot_router.get("/logs")
async def autopilot_logs(limit: int = 100, offset: int = 0, since_hours: int = 72):
    """
    Return Autopilot logs from persistent storage when available, with an in-memory fallback.
    We prefer rows written via core.storage.insert_action_log() by the worker, filtered to
    sources that start with 'autopilot' or mode == 'auto'.
    """
    # Try DB-backed logs first (core.storage.list_action_logs)
    try:
        rows = list_action_logs(limit=limit * 5, symbol=None, since_hours=since_hours)  # type: ignore[name-defined]
        def _is_auto(r: dict) -> bool:
            src = str(r.get("source", "")).lower()
            md = str(r.get("mode", "")).lower()
            return src.startswith("autopilot") or md in ("auto", "autopilot")
        out = [r for r in rows if isinstance(r, dict) and _is_auto(r)]
        out.sort(key=lambda x: str(x.get("ts", "")), reverse=True)
        return out[offset: offset + limit]
    except Exception:
        # fall back to manager in-memory logs
        mgr = _get_autopilot()
        return mgr.get_logs(limit=limit, offset=offset)

# stop Autopilot cleanly on shutdown (in addition to scheduler)
@app.on_event("shutdown")
async def _autopilot_shutdown():
    try:
        mgr = _get_autopilot()
        await mgr.stop()
    except Exception:
        pass

# ---------------- Autopilot: Preferences, Style, Watchlist ---------------- #

class AutopilotPrefs(BaseModel):
    target_winrate_pct: Optional[float] = None
    target_rr: Optional[float] = None
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    measured_move_atr_mult: Optional[float] = None
    max_dd_pct: Optional[float] = None
    per_trade_max_bps: Optional[int] = None


class StyleUpdate(BaseModel):
    text: str


def _get_json_setting(key: str, default):
    try:
        raw = get_setting(key)  # type: ignore[name-defined]
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except Exception:
            return raw
    except Exception:
        return default


def _set_json_setting(key: str, value) -> None:
    try:
        set_setting(key, value)  # type: ignore[name-defined]
    except Exception:
        pass


def _openai_chat(system: str, user: str) -> Optional[str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    if not api_key:
        return None
    try:
        import requests  # lazy import
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
        try:
            if os.getenv("OPENAI_JSON_MODE", "0") not in ("0", "false", "no"):
                payload["response_format"] = {"type": "json_object"}
        except Exception:
            pass
        r = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=float(os.getenv("OPENAI_TIMEOUT", "15")),
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception:
        return None

def _openai_chat_text(system: str, user: str) -> Optional[str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    if not api_key:
        return None
    try:
        import requests  # lazy import
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        r = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=float(os.getenv("OPENAI_TIMEOUT", "15")),
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception:
        return None

def _openai_chat_msgs(messages: list[dict]) -> Optional[str]:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
    if not api_key:
        return None
    try:
        import requests
        payload = {"model": model, "messages": messages, "temperature": 0.2}
        r = requests.post(
            f"{base}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=float(os.getenv("OPENAI_TIMEOUT", "15")),
        )
        r.raise_for_status()
        data = r.json()
        return data["choices"][0]["message"]["content"]
    except Exception:
        return None


def _summarize_style(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    system = (
        "You are a trading-style summarizer. Write a concise, actionable style note "
        "(<= 6 bullet lines or 400 chars) for a trading assistant. "
        "Prefer rules and thresholds (e.g., win rate target, RR, stop %, time windows)."
    )
    user = f"User preferences/notes to summarize:\n{text}"
    out = _openai_chat_text(system, user)
    if out and isinstance(out, str):
        return out.strip()[:600]
    # Fallback summary when model call fails
    try:
        import re
        sents = [s.strip() for s in re.split(r"[\n.;]+", text) if s.strip()]
        bullets = [f"- {s[:100].strip()}" for s in sents[:6]]
        if bullets:
            return "\n".join(bullets)[:600]
    except Exception:
        pass
    return text[:600]

def _extract_style_directives(text: str) -> str:
    """Extract only actionable trading directives from user text and recent turns.
    Ignore questions, small talk, or unrelated chatter. Return <= 12 bullet lines.
    Examples to extract: side bias, horizon, reduce-only/no-new-opens, stop/take %, measured move ATR, risk appetite,
    time windows (e.g., avoid lunch), specific approaches (e.g., Al Brooks price action), min confidence.
    """
    text = (text or "").strip()
    if not text:
        return ""
    system = (
        "Extract ONLY actionable trading directives from the user's notes.\n"
        "- Ignore chit-chat, questions, or unrelated conversation.\n"
        "- Use short bullet lines (<= 12).\n"
        "- Include items like: side bias (long/short), reduce-only/no new entries, trading horizon in minutes, target RR/win rate, stop/take %, measured_move_atr_mult, avoid windows (midday), and approaches (Al Brooks price action)."
    )
    user = f"User conversation notes to extract directives from:\n{text}"
    out = _openai_chat_text(system, user)
    if out and isinstance(out, str):
        # Filter questions and settings toggles
        try:
            lines = [l.strip() for l in out.strip().split("\n") if l.strip()]
            drop_cmd = re.compile(r"\b(turn|enable|disable)\b", re.I)
            drop_kw = re.compile(r"\b(news|signals|discovery|auto\s*weight|strict\s*prefs)\b", re.I)
            drop = re.compile(r"\?$|\b(what|what's|whats|how|why|should|could|would|tell|show|list|determine|find|review|pull|increase|decrease|up\b|down\b)\b", re.I)
            keep = []
            for l in lines:
                low = l.lower()
                if drop.search(low):
                    continue
                if drop_cmd.search(low) and drop_kw.search(low):
                    continue
                keep.append(l)
            return "\n".join(keep)[:800]
        except Exception:
            return out.strip()[:800]
    # Fallback: heuristics filter by directive keywords
    try:
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        keep = []
        kws = [
            r"short bias|prefer sells|long bias|prefer buys|reduce only|no new entries|pause opens",
            r"horizon|minutes|min\b|hrs|hours",
            r"stop|take profit|tp|rr\b|risk[- ]?reward|win rate|measured move|atr",
            r"avoid|do not trade|midday|lunch|market hours|pre[- ]?market|after[- ]?hours",
            r"al brooks|price action|trend follow|mean reversion|momentum",
        ]
        pat = re.compile("(" + ")|(".join(kws) + ")", re.I)
        qdrop = re.compile(r"\?|\b(what|what's|whats|how|why|should|could|would|tell|show|list|determine|find|review|pull|increase|decrease|up\b|down\b|turn|enable|disable)\b", re.I)
        setkw = re.compile(r"\b(news|signals|discovery|auto\s*weight|strict\s*prefs)\b", re.I)
        for l in lines:
            low = l.lower()
            if qdrop.search(low):
                continue
            if ("turn" in low or "enable" in low or "disable" in low) and setkw.search(low):
                continue
            if pat.search(low):
                keep.append(l)
            if len(keep) >= 12: break
        return "\n".join([("- " + l) for l in keep])[:800]
    except Exception:
        return text[:400]

def _merge_lines(a: str, b: str, limit: int = 1200) -> str:
    try:
        import re as _re
        def _norm(l: str) -> str:
            l2 = _re.sub(r"\s+", " ", l.strip().lower())
            l2 = _re.sub(r"[\.:;,]+$", "", l2)
            return l2
        def _lines(s: str):
            return [l for l in str(s or "").split("\n") if l and l.strip()]
        A = _lines(a); B = _lines(b)
        seen = set(); outl = []
        for l in A + B:
            key = _norm(l)
            if key and key not in seen:
                outl.append(l.strip()); seen.add(key)
        return "\n".join(outl)[:limit]
    except Exception:
        return (str(a or "") + ("\n" if a else "") + str(b or ""))[:limit]

def _conversation_tail(max_msgs: int = 16) -> list[dict]:
    try:
        log = _get_json_setting("assistant.chat", []) or []
        if not isinstance(log, list):
            return []
        tail = log[-max_msgs:]
        out = []
        for m in tail:
            role = str(m.get("role") or "user")
            content = str(m.get("content") or "")
            if content:
                out.append({"role": role, "content": content})
        return out
    except Exception:
        return []

def _style_lines(text: str) -> list[str]:
    return [l.strip() for l in str(text or "").split("\n") if l and l.strip()]

def _clean_style_summary(summary: str) -> str:
    try:
        prefs = _get_json_setting("autopilot.prefs", {}) or {}
    except Exception:
        prefs = {}
    lines = _style_lines(summary)
    out: list[str] = []
    seen: set[str] = set()
    stop = None; take = None; mm = None; horizon = None; bias = None; avoid_midday = False
    for l in lines:
        s = l.strip(); low = s.lower()
        if not s or len(s) <= 2:
            continue
        if any(x in low for x in ["no actionable", "determine ", "review ", "pull ", "increase ", "decrease ", " up ", " in "]):
            continue
        m = re.search(r"stop[^\d]*(\d+(?:\.\d+)?)\s*%", low)
        if m: stop = float(m.group(1)); continue
        m = re.search(r"take[^\d]*(\d+(?:\.\d+)?)\s*%", low)
        if m: take = float(m.group(1)); continue
        m = re.search(r"(horizon|mins|minutes|min)\D*(\d+(?:\.\d+)?)", low)
        if m: horizon = float(m.group(2)); continue
        m = re.search(r"(atr|measured.*move)\D*(\d+(?:\.\d+)?)", low)
        if m: mm = float(m.group(2)); continue
        if "short bias" in low or "prefer sells" in low: bias = "short"; continue
        if "long bias" in low or "prefer buys" in low: bias = "long"; continue
        if "midday" in low or ("avoid" in low and "lunch" in low): avoid_midday = True; continue
        # strategy/approach lines
        if any(k in low for k in ["al brooks", "price action", "trend follow", "mean reversion", "momentum"]):
            key = re.sub(r"\s+", " ", low)
            if key not in seen:
                seen.add(key); out.append(s)
    # prefer prefs for canonical numeric values
    try:
        if float(prefs.get("stop_loss_pct") or 0) > 0: stop = float(prefs.get("stop_loss_pct"))
        if float(prefs.get("take_profit_pct") or 0) > 0: take = float(prefs.get("take_profit_pct"))
        if float(prefs.get("measured_move_atr_mult") or 0) > 0: mm = float(prefs.get("measured_move_atr_mult"))
    except Exception:
        pass
    if bias == "short": out.insert(0, "Short bias (prefer sells)")
    if bias == "long": out.insert(0, "Long bias (prefer buys)")
    if stop is not None: out.append(f"Stop loss: {stop:g}%")
    if take is not None: out.append(f"Take profit: {take:g}%")
    if mm is not None: out.append(f"Measured move ATR: {mm:g}x")
    if horizon is not None: out.append(f"Horizon: {int(horizon)} min")
    if avoid_midday: out.append("Avoid trading midday")
    # final dedupe
    final = []
    seen2: set[str] = set()
    for s in out:
        key = re.sub(r"\s+", " ", s.strip().lower())
        if key not in seen2:
            seen2.add(key); final.append(s)
    return "\n".join(final[:24])

def _apply_simple_commands(text: str) -> list[str]:
    """Parse very simple natural commands and apply settings; return confirmations."""
    confirms: list[str] = []
    if not text:
        return confirms
    import re
    # normalize quotes/punctuation and whitespace to make matching robust
    t = str(text).lower()
    t = re.sub(r"[\u2018\u2019\u201C\u201D'\"]+", "", t)  # remove smart quotes and quotes
    t = re.sub(r"\s+", " ", t).strip()
    # Reduce-only / pause opens
    try:
        if any(p in t for p in ["reduce only", "close only", "flatten only", "pause new opens", "no new entries", "block opens"]):
            cur = _get_json_setting("autopilot.style_summary", "") or ""
            nxt = _merge_lines(cur, "- reduce only\n- no new entries")
            _set_json_setting("autopilot.style_summary", nxt)
            confirms.append("reduce_only + no_new_entries on")
        if any(p in t for p in ["resume opens", "allow new opens", "open entries ok"]):
            cur = str(_get_json_setting("autopilot.style_summary", "") or "")
            cur = cur.replace("- reduce only", "").replace("- no new entries", "")
            _set_json_setting("autopilot.style_summary", cur)
            confirms.append("allow_new_entries on")
    except Exception:
        pass
    # Min confidence
    m = re.search(r"min(?:imum)?\s*conf(?:idence)?\s*(?:to|=)?\s*(\d+(?:\.\d+)?)", t, re.I)
    if m:
        try:
            val = float(m.group(1))
            _set_json_setting("autopilot.min_confidence", val)
            confirms.append(f"min_confidence set to {val}")
        except Exception:
            pass
    # Numeric trading prefs
    try:
        prefs = _get_json_setting("autopilot.prefs", {}) or {}
        changed = False
        m = re.search(r"stop(?:\s*loss)?\s*(?:to|=)?\s*(\d+(?:\.\d+)?)\s*%", t)
        if m:
            prefs["stop_loss_pct"] = float(m.group(1)); changed = True; confirms.append(f"stop_loss_pct {prefs['stop_loss_pct']}%")
        m = re.search(r"take\s*profit\s*(?:to|=)?\s*(\d+(?:\.\d+)?)\s*%", t)
        if m:
            prefs["take_profit_pct"] = float(m.group(1)); changed = True; confirms.append(f"take_profit_pct {prefs['take_profit_pct']}%")
        m = re.search(r"measured\s*move\s*(?:atr)?\s*(?:x|mult|multiple)?\s*(\d+(?:\.\d+)?)", t)
        if m:
            prefs["measured_move_atr_mult"] = float(m.group(1)); changed = True; confirms.append(f"measured_move_atr_mult {prefs['measured_move_atr_mult']}x")
        m = re.search(r"win\s*rate\s*(?:target)?\s*(?:to|=)?\s*(\d+(?:\.\d+)?)\s*%", t)
        if m:
            prefs["target_winrate_pct"] = float(m.group(1)); changed = True; confirms.append(f"target_winrate_pct {prefs['target_winrate_pct']}%")
        m = re.search(r"(rr|risk[- ]?reward)\s*(?:to|=)?\s*(\d+(?:\.\d+)?)", t)
        if m:
            prefs["target_rr"] = float(m.group(2)); changed = True; confirms.append(f"target_rr {prefs['target_rr']}")
        if changed:
            _set_json_setting("autopilot.prefs", prefs)
    except Exception:
        pass
    # Bias
    if any(p in t for p in ["prefer sells", "short bias", "sell bias", "do more sells"]):
        cur = _get_json_setting("autopilot.style_summary", "") or ""
        nxt = _merge_lines(cur, "- short bias (prefer sells)")
        _set_json_setting("autopilot.style_summary", nxt)
        confirms.append("short_bias applied")
    if any(p in t for p in ["prefer buys", "long bias", "buy bias", "do more buys"]):
        cur = _get_json_setting("autopilot.style_summary", "") or ""
        nxt = _merge_lines(cur, "- long bias (prefer buys)")
        _set_json_setting("autopilot.style_summary", nxt)
        confirms.append("long_bias applied")
    # Feature toggles
    try:
        # News on/off (including "news momentum")
        if re.search(r"\b(news\s+momentum|news)\s+off\b|\bturn\s+(news\s+momentum|news)\s+off\b|\bdisable\s+(news\s+momentum|news)\b", t, re.I):
            _set_json_setting("autopilot.use_news", False); confirms.append("news disabled")
        if re.search(r"\b(news\s+momentum|news)\s+on\b|\bturn\s+(news\s+momentum|news)\s+on\b|\benable\s+(news\s+momentum|news)\b", t, re.I):
            _set_json_setting("autopilot.use_news", True); confirms.append("news enabled")
        # Signals on/off
        if re.search(r"\bsignals\s+off\b|\bdisable\s+signals\b", t, re.I):
            _set_json_setting("autopilot.signals.enabled", False); confirms.append("signals disabled")
        if re.search(r"\bsignals\s+on\b|\benable\s+signals\b", t, re.I):
            _set_json_setting("autopilot.signals.enabled", True); confirms.append("signals enabled")
        # Strict prefs
        if re.search(r"\bstrict\s*(prefs)?\s*on\b|\benable\s*strict\s*(prefs)?\b", t, re.I):
            _set_json_setting("autopilot.strict_prefs", True); confirms.append("strict_prefs on")
        if re.search(r"\bstrict\s*(prefs)?\s*off\b|\bdisable\s*strict\s*(prefs)?\b", t, re.I):
            _set_json_setting("autopilot.strict_prefs", False); confirms.append("strict_prefs off")
        # Auto-weight
        if re.search(r"\bauto\s*weight\s*on\b|\benable\s*auto\s*weight\b", t, re.I):
            _set_json_setting("autopilot.signals.auto_weight", True); confirms.append("auto_weight on")
        if re.search(r"\bauto\s*weight\s*off\b|\bdisable\s*auto\s*weight\b", t, re.I):
            _set_json_setting("autopilot.signals.auto_weight", False); confirms.append("auto_weight off")
        # Discovery
        if re.search(r"\bdiscovery\s*only\s*on\b|\benable\s*discovery\s*only\b", t, re.I):
            _set_json_setting("autopilot.discovery_only", True); confirms.append("discovery_only on")
        if re.search(r"\bdiscovery\s*only\s*off\b|\bdisable\s*discovery\s*only\b", t, re.I):
            _set_json_setting("autopilot.discovery_only", False); confirms.append("discovery_only off")
        if re.search(r"\bdiscovery\s*on\b|\benable\s*discovery\b", t, re.I):
            _set_json_setting("autopilot.discovery_enabled", True); confirms.append("discovery on")
        if re.search(r"\bdiscovery\s*off\b|\bdisable\s*discovery\b", t, re.I):
            _set_json_setting("autopilot.discovery_enabled", False); confirms.append("discovery off")
        # Top-N
        m = re.search(r"top\s*n\s*(?:to|=)?\s*(\d+)", t, re.I)
        if m:
            _set_json_setting("autopilot.top_n", int(m.group(1))); confirms.append(f"top_n {int(m.group(1))}")
    except Exception:
        pass
    return confirms

def _extract_symbols(text: str) -> list[str]:
    try:
        import re
    except Exception:
        return []
    if not text:
        return []
    txt = str(text).upper()
    out: list[str] = []
    # Explicit US.TICKER tokens
    out += re.findall(r"\bUS\.[A-Z0-9]{1,6}\b", txt)
    # Bare tickers (2–5 letters) excluding common words
    COMMON = {"THE","AND","FOR","WITH","THIS","THAT","ONLY","WHEN","STOP","TAKE","LOSS","SELL","BUY","LONG","SHORT","NEWS","RSI","ATR","MA","UP","DOWN","HOLD","OPEN","CLOSE","DAY","WEEK","MONTH","YEARS"}
    for token in re.findall(r"\b[A-Z]{2,5}\b", txt):
        if token in COMMON:
            continue
        out.append(f"US.{token}")
    # Dedup preserve order, cap length
    seen = set()
    uniq: list[str] = []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq[:50]


@autopilot_router.get("/prefs")
def autopilot_prefs_get():
    return _get_json_setting("autopilot.prefs", {})


@autopilot_router.put("/prefs")
def autopilot_prefs_put(prefs: AutopilotPrefs):
    cur = _get_json_setting("autopilot.prefs", {})
    upd = cur if isinstance(cur, dict) else {}
    for k, v in prefs.dict().items():
        if v is not None:
            upd[k] = v
    _set_json_setting("autopilot.prefs", upd)
    insert_action_log("prefs_update", mode=_two_mode(), reason="user_update", status="ok", extra=upd)  # type: ignore[name-defined]
    return upd


@autopilot_router.get("/style")
def autopilot_style_get():
    return {
        "raw": _get_json_setting("autopilot.style_raw", "") or "",
        "summary": _get_json_setting("autopilot.style_summary", "") or "",
    }


@autopilot_router.post("/style")
def autopilot_style_post(body: StyleUpdate):
    raw = (body.text or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="text is required")
    summary = _summarize_style(raw)
    _set_json_setting("autopilot.style_raw", raw)
    _set_json_setting("autopilot.style_summary", summary)
    # Extract and store candidate symbols
    syms = list(dict.fromkeys(_extract_symbols(raw) + _extract_symbols(summary)))
    if syms:
        _set_json_setting("autopilot.style_symbols", syms)
    insert_action_log("style_update", mode=_two_mode(), reason="user_update", status="ok", extra={"len": len(raw), "symbols": len(syms)})  # type: ignore[name-defined]
    return {"raw": raw, "summary": summary, "symbols": syms}


@autopilot_router.delete("/style")
def autopilot_style_delete():
    """
    Clear stored natural-language style and its summary (and any derived symbols).
    Safe no-op if nothing is stored.
    """
    try:
        _set_json_setting("autopilot.style_raw", "")
        _set_json_setting("autopilot.style_summary", "")
        # Also clear derived symbols and toggle (best-effort)
        _set_json_setting("autopilot.style_symbols", [])
        _set_json_setting("autopilot.style_symbols_enabled", False)
        insert_action_log("style_update", mode=_two_mode(), reason="delete", status="ok", extra={})  # type: ignore[name-defined]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete style: {e}")
    return {"raw": "", "summary": "", "symbols": []}


class StyleSymbolsUpdate(BaseModel):
    enabled: Optional[bool] = None
    symbols: Optional[List[str]] = None


@autopilot_router.get("/style_symbols")
def autopilot_style_symbols_get():
    enabled = bool(_get_json_setting("autopilot.style_symbols_enabled", False))
    syms = _get_json_setting("autopilot.style_symbols", [])
    if not isinstance(syms, list):
        syms = []
    return {"enabled": enabled, "symbols": syms}


@autopilot_router.put("/style_symbols")
def autopilot_style_symbols_put(body: StyleSymbolsUpdate):
    if isinstance(body.symbols, list):
        def _norm(x: str) -> str:
            x = (x or "").strip().upper()
            return x if "." in x else (f"US.{x}" if x else x)
        symbols = list({ _norm(s) for s in body.symbols if isinstance(s, str) and s.strip() })
        _set_json_setting("autopilot.style_symbols", symbols)
        insert_action_log("style_symbols", mode=_two_mode(), reason="update", status="ok", extra={"n": len(symbols)})  # type: ignore[name-defined]
    if body.enabled is not None:
        _set_json_setting("autopilot.style_symbols_enabled", bool(body.enabled))
        insert_action_log("style_symbols", mode=_two_mode(), reason="enabled_toggle", status="ok", extra={"enabled": bool(body.enabled)})  # type: ignore[name-defined]
    return autopilot_style_symbols_get()


class WatchlistUpdate(BaseModel):
    symbols: List[str]


def _normalize_symbol(s: str) -> str:
    s = (s or "").strip().upper()
    if not s:
        return s
    return s if "." in s else f"US.{s}"


@autopilot_router.get("/watchlist")
def autopilot_watchlist_get():
    wl = _get_json_setting("autopilot.watchlist", None)
    if isinstance(wl, list) and wl:
        return {"symbols": wl}
    env = os.getenv("AUTOPILOT_WATCHLIST", "US.AAPL,US.MSFT,US.TSLA")
    syms = [_normalize_symbol(x) for x in env.split(",") if x.strip()]
    return {"symbols": syms}


@autopilot_router.put("/watchlist")
def autopilot_watchlist_put(body: WatchlistUpdate):
    symbols = list({_normalize_symbol(x) for x in (body.symbols or []) if str(x).strip()})
    _set_json_setting("autopilot.watchlist", symbols)
    insert_action_log("watchlist_update", mode=_two_mode(), reason="user_update", status="ok", extra={"n": len(symbols)})  # type: ignore[name-defined]
    return {"symbols": symbols}


# ---- Discovery config and preview ----
class DiscoveryUpdate(BaseModel):
    enabled: bool | None = None
    only: bool | None = None
    seed: List[str] | None = None


@autopilot_router.get("/discovery")
def autopilot_discovery_get():
    enabled = True
    try:
        raw = _get_json_setting("autopilot.discovery_enabled", None)
        if raw is not None:
            enabled = bool(raw)
    except Exception:
        pass
    only = False
    try:
        raw = _get_json_setting("autopilot.discovery_only", None)
        if raw is not None:
            only = bool(raw)
    except Exception:
        pass
    seed = _get_json_setting("autopilot.discovery_seed", None)
    if not isinstance(seed, list):
        seed = []
    # Optional live preview (best-effort)
    preview: List[str] = []
    try:
        from autopilot.discovery import discover_symbols  # type: ignore
        preview = discover_symbols(get_client(), limit=10, ktype="K_DAY")  # type: ignore[arg-type]
    except Exception:
        preview = []
    return {"enabled": enabled, "only": only, "seed": seed, "preview": preview}


@autopilot_router.put("/discovery")
def autopilot_discovery_put(body: DiscoveryUpdate):
    if body.enabled is not None:
        _set_json_setting("autopilot.discovery_enabled", bool(body.enabled))
        insert_action_log("discovery_update", mode=_two_mode(), reason="enabled_toggle", status="ok", extra={"enabled": bool(body.enabled)})  # type: ignore[name-defined]
    if body.only is not None:
        _set_json_setting("autopilot.discovery_only", bool(body.only))
        insert_action_log("discovery_update", mode=_two_mode(), reason="only_toggle", status="ok", extra={"only": bool(body.only)})  # type: ignore[name-defined]
    if isinstance(body.seed, list):
        # normalize seed to US.TICKER
        symbols = list({_normalize_symbol(x) for x in body.seed if str(x).strip()})
        _set_json_setting("autopilot.discovery_seed", symbols)
        insert_action_log("discovery_update", mode=_two_mode(), reason="seed_update", status="ok", extra={"n": len(symbols)})  # type: ignore[name-defined]
    return autopilot_discovery_get()


# ---- Planner settings (min confidence, top_n) ----
class PlannerUpdate(BaseModel):
    min_confidence: float | None = None
    top_n: int | None = None
    strict_prefs: bool | None = None


@autopilot_router.get("/planner")
def autopilot_planner_get():
    try:
        mc_raw = _get_json_setting("autopilot.min_confidence", None)
        min_conf = float(mc_raw) if mc_raw is not None else 0.6
    except Exception:
        min_conf = 0.6
    try:
        tn_raw = _get_json_setting("autopilot.top_n", None)
        top_n = int(tn_raw) if tn_raw is not None else int(os.getenv("AUTOPILOT_TOP_N", "8") or "8")
    except Exception:
        top_n = int(os.getenv("AUTOPILOT_TOP_N", "8") or "8")
    try:
        sp_raw = _get_json_setting("autopilot.strict_prefs", None)
        strict_prefs = bool(sp_raw) if sp_raw is not None else False
    except Exception:
        strict_prefs = False
    return {"min_confidence": min_conf, "top_n": top_n, "strict_prefs": strict_prefs}


@autopilot_router.put("/planner")
def autopilot_planner_put(body: PlannerUpdate):
    if body.min_confidence is not None:
        _set_json_setting("autopilot.min_confidence", float(body.min_confidence))
        insert_action_log("planner_update", mode=_two_mode(), reason="min_conf", status="ok", extra={"min_conf": float(body.min_confidence)})  # type: ignore[name-defined]
    if isinstance(body.top_n, int) and body.top_n > 0:
        _set_json_setting("autopilot.top_n", int(body.top_n))
        insert_action_log("planner_update", mode=_two_mode(), reason="top_n", status="ok", extra={"top_n": int(body.top_n)})  # type: ignore[name-defined]
    if body.strict_prefs is not None:
        _set_json_setting("autopilot.strict_prefs", bool(body.strict_prefs))
        insert_action_log("planner_update", mode=_two_mode(), reason="strict_prefs", status="ok", extra={"strict_prefs": bool(body.strict_prefs)})  # type: ignore[name-defined]
    return autopilot_planner_get()


# ---- News settings (toggle + ttl) ----
class NewsUpdate(BaseModel):
    enabled: bool | None = None
    ttl_sec: int | None = None
    provider: str | None = None  # 'heuristic' | 'gpt'


@autopilot_router.get("/news")
def autopilot_news_get():
    enabled = True
    try:
        raw = _get_json_setting("autopilot.use_news", None)
        if raw is not None:
            enabled = bool(raw)
    except Exception:
        pass
    try:
        ttl = int(_get_json_setting("autopilot.news_ttl_sec", None) or 0)
    except Exception:
        ttl = 0
    if ttl <= 0:
        ttl = int(os.getenv("AUTOPILOT_NEWS_TTL_SEC", "1800") or "1800")
    # provider (default heuristic)
    provider = "heuristic"
    try:
        pv = _get_json_setting("autopilot.news_provider", None)
        if isinstance(pv, str) and pv.strip():
            provider = pv.strip()
    except Exception:
        pass
    return {"enabled": enabled, "ttl_sec": ttl, "provider": provider}


@autopilot_router.put("/news")
def autopilot_news_put(body: NewsUpdate):
    if body.enabled is not None:
        _set_json_setting("autopilot.use_news", bool(body.enabled))
        insert_action_log("news_update", mode=_two_mode(), reason="enabled_toggle", status="ok", extra={"enabled": bool(body.enabled)})  # type: ignore[name-defined]
    if isinstance(body.ttl_sec, int) and body.ttl_sec > 0:
        _set_json_setting("autopilot.news_ttl_sec", int(body.ttl_sec))
        insert_action_log("news_update", mode=_two_mode(), reason="ttl_update", status="ok", extra={"ttl_sec": int(body.ttl_sec)})  # type: ignore[name-defined]
    if isinstance(body.provider, str) and body.provider.strip():
        pv = body.provider.strip().lower()
        if pv not in ("heuristic", "gpt"):
            raise HTTPException(status_code=400, detail="provider must be 'heuristic' or 'gpt'")
        _set_json_setting("autopilot.news_provider", pv)
        insert_action_log("news_update", mode=_two_mode(), reason="provider", status="ok", extra={"provider": pv})  # type: ignore[name-defined]
    return autopilot_news_get()


# ---- Data settings (ktype, bars ttl) ----
class DataUpdate(BaseModel):
    ktype: str | None = None
    bars_ttl_sec: int | None = None
    deals_sync_sec: int | None = None
    data_source: str | None = None


_KTYPES = {"K_1M","K_5M","K_15M","K_30M","K_60M","K_DAY","K_1D"}


@autopilot_router.get("/data")
def autopilot_data_get():
    ktype = str(_get_json_setting("autopilot.ktype", None) or os.getenv("AUTOPILOT_KTYPE", "K_DAY"))
    bars_ttl = 0
    try:
        bars_ttl = int(_get_json_setting("autopilot.bars_ttl_sec", None) or 0)
    except Exception:
        bars_ttl = 0
    if bars_ttl <= 0:
        bars_ttl = int(os.getenv("AUTOPILOT_BARS_TTL_SEC", "60") or "60")
    try:
        deals_sync = int(_get_json_setting("autopilot.deals_sync_sec", None) or 0)
    except Exception:
        deals_sync = 0
    if deals_sync <= 0:
        deals_sync = int(os.getenv("AUTOPILOT_DEALS_SYNC_SEC", "180") or "180")
    src = str(_get_json_setting("autopilot.data_source", None) or os.getenv("AUTOPILOT_DATA_SOURCE", "futu"))
    return {"ktype": ktype, "bars_ttl_sec": bars_ttl, "deals_sync_sec": deals_sync, "data_source": src}


@autopilot_router.put("/data")
def autopilot_data_put(body: DataUpdate):
    if body.ktype is not None:
        kt = str(body.ktype).upper().strip()
        if kt not in _KTYPES:
            raise HTTPException(status_code=400, detail=f"ktype must be one of: {sorted(_KTYPES)}")
        _set_json_setting("autopilot.ktype", kt)
        insert_action_log("data_update", mode=_two_mode(), reason="ktype", status="ok", extra={"ktype": kt})  # type: ignore[name-defined]
    if isinstance(body.bars_ttl_sec, int) and body.bars_ttl_sec > 0:
        _set_json_setting("autopilot.bars_ttl_sec", int(body.bars_ttl_sec))
        insert_action_log("data_update", mode=_two_mode(), reason="bars_ttl", status="ok", extra={"bars_ttl_sec": int(body.bars_ttl_sec)})  # type: ignore[name-defined]
    if isinstance(body.deals_sync_sec, int) and body.deals_sync_sec > 0:
        _set_json_setting("autopilot.deals_sync_sec", int(body.deals_sync_sec))
        insert_action_log("data_update", mode=_two_mode(), reason="deals_sync", status="ok", extra={"deals_sync_sec": int(body.deals_sync_sec)})  # type: ignore[name-defined]
    if body.data_source is not None:
        ds = str(body.data_source).lower().strip()
        if ds not in {"futu", "yfinance"}:
            raise HTTPException(status_code=400, detail="data_source must be 'futu' or 'yfinance'")
        _set_json_setting("autopilot.data_source", ds)
        insert_action_log("data_update", mode=_two_mode(), reason="data_source", status="ok", extra={"data_source": ds})  # type: ignore[name-defined]
    return autopilot_data_get()


# ---- Signals settings (enable + per-strategy weights) ----
class SignalsSettings(BaseModel):
    enabled: Optional[bool] = None
    strategies: Optional[Dict[str, bool]] = None
    weights: Optional[Dict[str, float]] = None
    auto_weight: Optional[bool] = None


@autopilot_router.get("/signals")
def autopilot_signals_get():
    # defaults
    enabled = True
    strategies: Dict[str, bool] = {
        "macd_cross": True,
        "bb_breakout": True,
        "stoch_rsi_extreme": True,
        "ma_trend": True,
        "rsi_extreme": True,
        "news": True,
    }
    weights: Dict[str, float] = {
        "macd_cross": 1.0,
        "bb_breakout": 1.0,
        "stoch_rsi_extreme": 1.0,
        "ma_trend": 1.0,
        "rsi_extreme": 1.0,
        "news": 1.0,
    }
    try:
        raw = _get_json_setting("autopilot.signals.enabled", None)
        if raw is not None:
            enabled = bool(raw)
    except Exception:
        pass
    try:
        m = _get_json_setting("autopilot.signals.strategies", None)
        if isinstance(m, dict):
            strategies.update({str(k): bool(v) for k, v in m.items()})
    except Exception:
        pass
    try:
        w = _get_json_setting("autopilot.signals.weights", None)
        if isinstance(w, dict):
            for k, v in w.items():
                try:
                    weights[str(k)] = float(v)
                except Exception:
                    continue
    except Exception:
        pass
    # auto-weight flag
    auto_weight = False
    try:
        raw = _get_json_setting("autopilot.signals.auto_weight", None)
        if raw is not None:
            auto_weight = bool(raw)
    except Exception:
        pass
    return {"enabled": enabled, "strategies": strategies, "weights": weights, "auto_weight": auto_weight}


@autopilot_router.put("/signals")
def autopilot_signals_put(body: SignalsSettings):
    if body.enabled is not None:
        _set_json_setting("autopilot.signals.enabled", bool(body.enabled))
        insert_action_log("signals_update", mode=_two_mode(), reason="enabled_toggle", status="ok", extra={"enabled": bool(body.enabled)})  # type: ignore[name-defined]
    if isinstance(body.strategies, dict):
        # sanitize to booleans
        clean = {str(k): bool(v) for k, v in body.strategies.items()}
        _set_json_setting("autopilot.signals.strategies", clean)
        insert_action_log("signals_update", mode=_two_mode(), reason="strategies", status="ok", extra={"n": len(clean)})  # type: ignore[name-defined]
    if isinstance(body.weights, dict):
        clean_w: Dict[str, float] = {}
        for k, v in body.weights.items():
            try:
                clean_w[str(k)] = float(v)
            except Exception:
                continue
        _set_json_setting("autopilot.signals.weights", clean_w)
        insert_action_log("signals_update", mode=_two_mode(), reason="weights", status="ok", extra={"n": len(clean_w)})  # type: ignore[name-defined]
    # optional auto_weight toggle
    try:
        aw = getattr(body, 'auto_weight', None)  # type: ignore
        if aw is not None:
            _set_json_setting("autopilot.signals.auto_weight", bool(aw))
            insert_action_log("signals_update", mode=_two_mode(), reason="auto_weight", status="ok", extra={"enabled": bool(aw)})  # type: ignore[name-defined]
    except Exception:
        pass
    return autopilot_signals_get()

# Ensure all /autopilot routes are registered only after definitions
@autopilot_router.get("/weekly")
def autopilot_weekly():
    """
    Weekly report: realized metrics, per-strategy attribution (from signals_used),
    auto-weight adjustment summary, missed rules, and % dropped by validator.
    """
    try:
        from core.storage import performance_stats, list_action_logs  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage unavailable: {e}")

    out: Dict[str, Any] = {}
    # Realized metrics (7d window)
    try:
        out["performance_7d"] = performance_stats(days=7)
    except Exception:
        out["performance_7d"] = {}

    # Action logs in 7d for attribution + validator/evaluator summaries
    rows = []
    try:
        rows = list_action_logs(limit=2000, symbol=None, since_hours=24*7)
    except Exception:
        rows = []

    import json as _json
    # Per-strategy attribution: count strength weighted appearances in 'autopilot_act' signals_used
    strat_use: Dict[str, float] = {}
    reweights: int = 0
    proposed_total = 0
    validator_dropped = 0
    evaluator_dropped = 0
    missed_rules = {"planner_invalid_json": 0, "guardrails": 0}
    proposed_counts: Dict[str, int] = {}
    executed_counts: Dict[str, int] = {}
    decision_reasons: Dict[str, List[str]] = {}
    for r in rows:
        try:
            act = str(r.get("action") or "")
            src = str(r.get("source") or "")
            reason = str(r.get("reason") or "")
            if act == "autopilot_act":
                extra = {}
                try:
                    extra = _json.loads(r.get("extra_json") or "{}")
                except Exception:
                    extra = {}
                for s in extra.get("signals_used", []) or []:
                    k = str(s.get("strategy") or "")
                    if not k:
                        continue
                    strat_use[k] = strat_use.get(k, 0.0) + float(s.get("strength") or 0.0)
                sym = str(r.get("symbol") or "")
                if sym:
                    executed_counts[sym] = executed_counts.get(sym, 0) + 1
                    rc = extra.get("rule_checks") or {}
                    try:
                        bad = [k for k, v in rc.items() if v is False and k != "unusual_flow"]
                        if bad:
                            decision_reasons.setdefault(sym, []).extend(bad)
                    except Exception:
                        pass
            elif act == "autopilot" and reason == "signals_reweighted":
                reweights += 1
            elif act == "planner_proposed":
                extra = {}
                try:
                    extra = _json.loads(r.get("extra_json") or "{}")
                except Exception:
                    extra = {}
                proposed_total += int(extra.get("n") or 0)
                for s in extra.get("syms") or []:
                    sym = str(s)
                    if sym:
                        proposed_counts[sym] = proposed_counts.get(sym, 0) + 1
            elif act == "validator_result":
                extra = {}
                try:
                    extra = _json.loads(r.get("extra_json") or "{}")
                except Exception:
                    extra = {}
                validator_dropped += int(extra.get("dropped") or 0)
            elif act == "evaluator_result":
                extra = {}
                try:
                    extra = _json.loads(r.get("extra_json") or "{}")
                except Exception:
                    extra = {}
                evaluator_dropped += int(extra.get("dropped") or 0)
            elif act == "autopilot" and reason == "planner_invalid_json":
                missed_rules["planner_invalid_json"] += 1
            elif act == "autopilot_act" and reason == "guardrail":
                missed_rules["guardrails"] += 1
        except Exception:
            continue

    out["attribution"] = strat_use
    out["auto_weight_adjustments"] = reweights
    out["dropped"] = {
        "proposed_total": proposed_total,
        "validator_dropped": validator_dropped,
        "evaluator_dropped": evaluator_dropped,
        "pct_dropped_validator": (0 if proposed_total==0 else round(validator_dropped / proposed_total * 100.0, 2)),
    }
    out["missed_rules"] = missed_rules
    out["proposed_counts"] = proposed_counts
    out["executed_counts"] = executed_counts
    out["decision_reasons"] = decision_reasons
    return out

@autopilot_router.get("/pnl_series")
def autopilot_pnl_series(days: int = 30):
    try:
        from core.storage import pnl_history  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Storage unavailable: {e}")
    try:
        d = max(1, int(days))
    except Exception:
        d = 30
    try:
        return {"series": pnl_history(days=d)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"pnl history failed: {e}")

# Ensure router registration happens after all route definitions
app.include_router(autopilot_router)
