# src/planner_client_gpt.py
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List
import time
import random

import requests

# Strict schema validator from your codebase
try:
    from schemas import PlannerOutput, validate_output  # top-level layout
except Exception:  # fallback if nested under autopilot/
    from autopilot.schemas import PlannerOutput, validate_output  # type: ignore


JSON_ONLY_RULES = """You are a trade planner that must output STRICT JSON matching this schema:
{
  "decisions": [
    {
      "sym": "US.AAPL",
      "action": "open" | "close" | "add" | "trim" | "hold",
      "side": "buy" | "sell",                 // REQUIRED for action=open/add/trim; optional for close/hold
      "entry": "market" | "limit",
      "size_type": "shares" | "notional" | "risk_bps",
      "size_value": number,
      "limit_price": number | null,           // only when entry=limit
      "time_in_force": "day" | "gtc",
      "stop": {"type":"atr"|"percent"|"price","mult":number|null,"value":number|null} | null,
      "take_profit": {"type":"atr"|"percent"|"price","mult":number|null,"value":number|null} | null,
      "confidence": number,                   // 0..1
      "expires_sec": number,                  // suggested time-to-live for this decision
      "rationale": string,                    // short reason
      // optional self-check fields (the server may fill them too)
      "rule_checks": {                        // planner's own checks; server augments
        "strict_prefs_ok": boolean|null,
        "policy_ok": boolean|null,
        "near_earnings": boolean|null,
        "valuation_ok": boolean|null,
        "conflict_index": number|null,        // 0..1, higher = more conflict
        "unusual_flow": boolean|null,
        "unusual_flow_strength": number|null
      } | null,
      "alternatives_considered": string[] | null
    }
  ],
  "global_action": "proceed" | "pause",
  "policy_summary": string,                    // brief statement of how policy was applied (e.g., reduce-only; holds only)
  "notes": string | null                       // why nothing actionable or plan-level notes
}
Rules and policy (Compliance Contract):
- Return ONLY JSON. No commentary, no Markdown, no code fences.
- Symbols look like 'US.TICKER' (no spaces). Keep decisions within trimmed universe.
- Inputs available: account/risk; positions (current qty and avg plus extra fields: last px, upl/upl_pct signed to position direction, signal_strength, signal_net, conflict_index, history, recent_decisions); orders (open/pending with side/qty/price/status); pending_orders_map (per-symbol remaining buy/sell size already working—treat this as reserved unless you intentionally resize the remainder); universe (px, atr, rsi, ma50/ma200, trend, rank, suggested exits, ret_20d_pct, adv_usd_20, vol_regime); prefs, style_summary, and style_hints; strategy_signals (long/short with strength and ttl); news (tone/summary); fundamentals (pe, market_cap, rev_g_yoy, margins, debt_to_equity, fcf_margin, sector, rs_sector_pct, ownership/short when available, analyst/estimates when available) and events (earnings/ex_div dates). A "portfolio" object may also be present with exposure, open_slots, sector concentration and correlation proxy; prefer diversification and respect open_slots. A lightweight "macro" object may be present (e.g., VIX, DXY, 10Y yields) for regime context. A "market" object may include within_hours and flatten_window flags; avoid new entries when false/true respectively. A per-symbol conflict_index map may be present; prefer hold/close when high. 'account.bp_reserved_est' approximates capital reserved by open BUY orders. A 'recently_closed' list highlights tickers you just exited with timestamps—only revisit them when the thesis truly flipped.
- A "history" map may list per-symbol {"last_action","realized_r"}; favor add/hold when realized_r > 0 and avoid fresh opens when realized_r < 0. "recent_decisions_map" summarises prior planner verdicts per symbol (status: kept/rejected/guardrail/idempotent/etc); avoid repeating a rejected action unless something material changed. "eval_feedback" lists recent evaluator scores (score + keep boolean); aim for scores ≥ threshold (~0.25).
- Strongly prefer high-confidence, few decisions. Always include stop/take when prefs exist.
- If planner.strict_prefs=true and prefs include stop/take/ATR guidance, you MUST include stop and take_profit for action=open. Otherwise the decision will be rejected (missing protection is dropped by the validator).
- Strict prefs are enforced server-side; missing protection on required opens will be blocked as `strict_prefs`, so plan accordingly and include the stops/takes up front.
- You MUST comply with 'policy' in the input (reduce_only, long_only, short_only, forbid_new). If reduce_only or forbid_new is true, do not output 'open' or 'add'; use 'close'/'trim'/'hold' instead. If long_only is true, do not output SELL for open/add. If short_only is true, do not output BUY for open/add. Confirm compliance in 'policy_summary'.
- You MUST also respect 'market' constraints: when market.within_hours=false or market.flatten_window=true, avoid 'open'/'add' and prefer 'hold'/'close'. If portfolio.open_slots is 0, do NOT output 'open'.
- For actions open/add/trim you MUST include both 'side' and 'entry'; omit them only for close/hold.
- Avoid duplicate opens: If already long, do NOT open another long unless action is 'add' with clear rationale. If already short, do NOT open another short unless 'add'.
- Interpret style_summary and style_hints: if style_hints.side_bias=-1, favor SELL for new entries when otherwise neutral; if +1, favor BUY. If style_summary references a specific approach (e.g., "al brooks"), bias your rationale toward that style (price action, micro-trend context, second entries) while still following policy and risk.
- Encourage lifecycle decisions:
  * Consider 'close' when: signals reverse strongly, RSI extreme reverts, price crosses against trend, or negative news tone appears; especially before earnings or ex_div events.
  * Consider 'trim' on overbought spikes against prefs; consider 'add' on trend continuation with supportive signals.
  * If upcoming earnings/ex_div within ~3 trading days, down‑weight new entries; prefer 'hold' or smaller 'add', or 'close' if conflict rises.
  * Lifecycle-first: evaluate closes -> trims -> adds before any opens; opens must pass event/valuation/liquidity gates and portfolio constraints (open_slots, sector concentration).
- Position sizing guidance:
  * Scale size_value by confidence and ATR relative to price; do not exceed prefs risk targets.
  * When conflicting signals exist (e.g., bearish news with bullish signal), reduce confidence and prefer 'hold' or no trade.
- Use 'rationale' to state the key drivers (signals, trend, events, prefs). Populate rule_checks (strict_prefs_ok, policy_ok, near_earnings, liquidity_ok) and include 1–3 alternatives_considered per symbol summarizing options you rejected.
- Use 'expires_sec' to 90–180 to allow decisions to lapse and avoid re-placing every tick.
- Align 'expires_sec' with 'planner.target_horizon_min' in the input when provided (e.g., 60 min → ~3600 seconds). Favor quicker, time-boxed trades when horizon is short.
Side selection:
- Use 'side_hint_map' when present: 'sell' favors short-side opens/adds; 'buy' favors long-side; 'none' means infer from signals and trend.
- You may return no decisions in any tick. If nothing is actionable or constraints bind (policy/market/open_slots), return {"decisions": [], "global_action": "proceed", "notes": "why"}.
Portfolio awareness:
- Justify any add/open that increases concentration in the top sector; if open_slots is 0, avoid 'open'. Prefer diversification when conflict_index is elevated.
Scoring:
- Provide a reasonable 'confidence' for each decision (0..1) reflecting your internal score after considering conflict_index, near_earnings, valuation, and portfolio.

Mini example (illustrative only):
Input highlights:
  prefs: {"target_rr":1.8,"stop_loss_pct":0.01,"measured_move_atr_mult":1.5}
  universe (top 2):
    {"sym":"US.AAPL","px":210.1,"atr":3.0,"rsi":62,"trend":"up","interest":8.4,"rank":1,
     "suggested":{"take_atr_mult":1.5}}
    {"sym":"US.TSLA","px":230.5,"atr":6.5,"rsi":72,"trend":"up","interest":7.1,"rank":2}
  strategy_signals: [{"strategy":"ma_trend","sym":"US.AAPL","signal":"long","strength":0.7}]
  news: [{"sym":"US.AAPL","tone":"bullish","summary":"Beat; raises guidance"}]
Desired output:
  {"decisions":[
     {"sym":"US.AAPL","action":"open","side":"buy","entry":"market",
      "size_type":"risk_bps","size_value":25,
      "stop":{"type":"percent","value":1.0},
      "take_profit":{"type":"atr","mult":1.5},
      "time_in_force":"day","confidence":0.72,
      "expires_sec":120,"rationale":"Uptrend + bullish news + signal"}
  ],"global_action":"proceed"}

Conflict example (signals vs news & events):
Input highlights:
  prefs: {"stop_loss_pct":0.01}
  universe: {"sym":"US.NVDA","px":900,"atr":15,"rsi":78,"trend":"up","interest":8.0,"rank":1}
  strategy_signals: [{"strategy":"rsi_extreme","sym":"US.NVDA","signal":"short","strength":0.4}]
  news: [{"sym":"US.NVDA","tone":"bullish","summary":"Upgrade; demand strong"}]
Desired output:
  {"decisions": [
     {"sym":"US.NVDA","action":"hold","side":"buy","entry":"market",
      "size_type":"risk_bps","size_value":0,
      "stop":{"type":"percent","value":1.0},
      "take_profit": null,
      "time_in_force":"day","confidence":0.45,
      "expires_sec":120,"rationale":"Conflicting: RSI short vs bullish news; earnings tomorrow; wait"}
  ],"global_action":"proceed"}
"""

def _strip_to_json(text: str) -> str:
    """Extract the first JSON object from text, tolerating stray prose or code fences."""
    text = re.sub(r"^```(json)?|```$", "", text.strip(), flags=re.MULTILINE)
    try:
        json.loads(text)
        return text
    except Exception:
        pass
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        return m.group(0)
    raise ValueError(f"no JSON object found in response: {text!r}")


class GPTPlannerClient:
    """
    Minimal, dependency-light GPT caller using 'requests' and Chat Completions API.
    Env:
      - OPENAI_API_KEY (required)
      - OPENAI_MODEL (default 'gpt-4o-mini')
      - OPENAI_BASE_URL (default 'https://api.openai.com/v1')
      - OPENAI_TIMEOUT (default '15')
      - OPENAI_TEMPERATURE (default '0')
    """
    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
        base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
        self.url = f"{base}/chat/completions"
        self.timeout = float(os.getenv("OPENAI_TIMEOUT", "15"))
        self.temperature = float(os.getenv("OPENAI_TEMPERATURE", "0"))
        # Optional client-side pacing to avoid hitting RPM
        try:
            self._min_interval = float(os.getenv("OPENAI_MIN_INTERVAL_SEC", "0") or 0.0)
        except Exception:
            self._min_interval = 0.0
        self._last_call_ts = 0.0

    def _chat(self, system: str, user: str) -> str:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        try:
            if os.getenv("OPENAI_JSON_MODE", "0") not in ("0", "false", "no"):
                payload["response_format"] = {"type": "json_object"}
        except Exception:
            pass
        max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "4") or 4)
        base_delay = float(os.getenv("OPENAI_RETRY_BASE_SEC", "1.0") or 1.0)
        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                # Optional pacing
                if self._min_interval > 0:
                    now = time.time()
                    dt = now - self._last_call_ts
                    if dt < self._min_interval:
                        time.sleep(max(0.0, self._min_interval - dt))
                resp = requests.post(self.url, headers=headers, json=payload, timeout=self.timeout)
                # Explicitly handle rate limits and transient 5xx
                if resp.status_code in (429, 500, 502, 503, 504):
                    # Derive delay from headers when available
                    retry_after = resp.headers.get("Retry-After")
                    if retry_after is not None:
                        try:
                            delay = max(0.5, float(retry_after))
                        except Exception:
                            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                    else:
                        delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
                    if attempt < max_retries - 1:
                        time.sleep(delay)
                        continue
                resp.raise_for_status()
                data = resp.json()
                self._last_call_ts = time.time()
                return data["choices"][0]["message"]["content"]
            except requests.RequestException as e:
                last_exc = e
                # Backoff on transient network errors
                if attempt < max_retries - 1:
                    time.sleep(base_delay * (2 ** attempt) + random.uniform(0, 0.5))
                    continue
                break
        # Exhausted retries
        if last_exc:
            raise last_exc
        raise RuntimeError("OpenAI chat call failed")

    def plan(self, planner_input: Dict[str, Any]) -> PlannerOutput:
        system = JSON_ONLY_RULES

        # Minify planner input to avoid overloading the model with large series
        def _minify(inp: Dict[str, Any]) -> Dict[str, Any]:
            out: Dict[str, Any] = {}
            # Helper: keep only whitelisted keys in universe items
            uni_keep: List[str] = [
                "sym","px","atr","atr_pct","rsi","ma50","ma200","trend","rank","interest",
                "change_1d_pct","ret_20d_pct","dist_ma50_pct","dist_ma200_pct","adv_usd_20","vol_regime",
                "suggested","nbbo_spread_pct","nbbo_spread_med","nbbo_samples","halted","broker_risk",
            ]
            # Top-level shallow copy of primitives/maps
            for k in [
                "timestamp","mode","account","risk","positions","style_summary","prefs","planner",
                "style_hints","market","orders",
                "strategy_signals","news","fundamentals","events","macro","breadth","policy",
                "sig_strength_map","sig_dir_map","side_hint_map","conflict_index","portfolio",
                # keep a single corr proxy map; drop additional windows to save tokens
                "corr_portfolio_map","ivr_map","unusual_flow_map","unusual_flow_strength_map",
            ]:
                if k in inp and inp.get(k) is not None:
                    out[k] = inp[k]
            # Orders: keep only a compact view
            if "orders" in out and isinstance(out["orders"], list):
                ords = []
                for r in (out["orders"] or [])[:12]:
                    if not isinstance(r, dict):
                        continue
                    ords.append({
                        "sym": r.get("sym"),
                        "side": r.get("side"),
                        "qty": r.get("qty"),
                        "filled": r.get("filled"),
                        "price": r.get("price"),
                        "status": r.get("status"),
                        "order_type": r.get("order_type"),
                        "tif": r.get("tif"),
                    })
                out["orders"] = ords

            # Universe: drop heavy series keys (prefixed with '_') and keep only important numerics
            uni: List[Dict[str, Any]] = []
            for u in (inp.get("universe") or []):
                if not isinstance(u, dict):
                    continue
                u2: Dict[str, Any] = {kk: vv for kk, vv in u.items() if kk in uni_keep}
                # Always keep sym
                s = str(u.get("sym") or "")
                if s and "sym" not in u2:
                    u2["sym"] = s
                uni.append(u2)
            out["universe"] = uni

            # Trim strategy_signals fields
            sigs: List[Dict[str, Any]] = []
            for s in (inp.get("strategy_signals") or [])[:24]:
                if not isinstance(s, dict):
                    continue
                sigs.append({
                    "strategy": s.get("strategy"),
                    "sym": s.get("sym"),
                    "signal": s.get("signal"),
                    "strength": s.get("strength"),
                    "ttl_sec": s.get("ttl_sec"),
                })
            out["strategy_signals"] = sigs

            # News: keep summary fields only
            news_out: List[Dict[str, Any]] = []
            for n in (inp.get("news") or []):
                if not isinstance(n, dict):
                    continue
                news_out.append({
                    "sym": n.get("sym"),
                    "tone": n.get("tone"),
                    "summary": n.get("summary"),
                })
            out["news"] = news_out

            # Fundamentals: keep a compact set of keys per symbol
            f_keep = {
                "pe","market_cap","rev_g_yoy","gp_margin","op_margin","fcf_margin","debt_to_equity","sector",
                "rs_sector_pct","float_shares","shares_out","inst_own","insider_own","short_pct_float",
                "ivr_proxy_90","iv_term_slope","iv_rr25d_short","iv_rr25d_long","insider_net_shares_90d",
                "vol_proxy_atr_pct",
            }
            fins = {}
            try:
                fin_in = inp.get("fundamentals") or {}
                # Restrict to trimmed universe symbols
                uni_syms = {str(u.get("sym")) for u in uni if u.get("sym")}
                for sym, val in fin_in.items():
                    if uni_syms and sym not in uni_syms:
                        continue
                    if isinstance(val, dict):
                        fins[sym] = {kk: vv for kk, vv in val.items() if kk in f_keep}
            except Exception:
                fins = fin_in if isinstance(inp.get("fundamentals"), dict) else {}
            out["fundamentals"] = fins

            # Correlation maps: keep only current-window proxy when available
            if "corr_portfolio_w20" in inp:
                out["corr_portfolio_w20"] = inp.get("corr_portfolio_w20")
            return out

        compact = _minify(planner_input)
        user = "PlannerInput JSON:\n" + json.dumps(compact, separators=(",", ":"), ensure_ascii=False)

        attempts = 2
        last_exc: Exception | None = None
        for _ in range(attempts):
            try:
                text = self._chat(system, user)
                txt = _strip_to_json(text)
                out_obj = json.loads(txt)
                return validate_output(out_obj)
            except Exception as e:
                last_exc = e
                system = JSON_ONLY_RULES + "\nIf your last output failed validation, fix it and return ONLY JSON."

        # Raise to allow CompositePlanner to fall back to stub
        if last_exc:
            raise last_exc
        raise RuntimeError("planner failed")
