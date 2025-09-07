# src/planner_client_gpt.py
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict

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
        "conflict_index": number|null         // 0..1, higher = more conflict
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
- Inputs available: account/risk; positions (current qty and avg); universe (px, atr, rsi, ma50/ma200, trend, rank, suggested exits, ret_20d_pct, adv_usd_20, vol_regime); prefs and style_summary; strategy_signals (long/short with strength and ttl); news (tone/summary); fundamentals (pe, market_cap, rev_g_yoy, margins, debt_to_equity, fcf_margin, sector, rs_sector_pct, ownership/short when available, analyst/estimates when available) and events (earnings/ex_div dates). A "portfolio" object may also be present with exposure, open_slots, sector concentration and correlation proxy; prefer diversification and respect open_slots. A lightweight "macro" object may be present (e.g., VIX, DXY, 10Y yields) for regime context. A per-symbol conflict_index map may be present; prefer hold/close when high.
- Strongly prefer high-confidence, few decisions. Always include stop/take when prefs exist.
- If planner.strict_prefs=true and prefs include stop/take/ATR guidance, you MUST include stop and take_profit for action=open. Otherwise the decision will be rejected.
- You MUST comply with 'policy' in the input (reduce_only, long_only, short_only, forbid_new). If reduce_only or forbid_new is true, do not output 'open' or 'add'; use 'close'/'trim'/'hold' instead. If long_only is true, do not output SELL for open/add. If short_only is true, do not output BUY for open/add. Confirm compliance in 'policy_summary'.
- For actions open/add/trim you MUST include both 'side' and 'entry'; omit them only for close/hold.
- Avoid duplicate opens: If already long, do NOT open another long unless action is 'add' with clear rationale. If already short, do NOT open another short unless 'add'.
- Encourage lifecycle decisions:
  * Consider 'close' when: signals reverse strongly, RSI extreme reverts, price crosses against trend, or negative news tone appears; especially before earnings or ex_div events.
  * Consider 'trim' on overbought spikes against prefs; consider 'add' on trend continuation with supportive signals.
  * If upcoming earnings/ex_div within ~3 trading days, down‑weight new entries; prefer 'hold' or smaller 'add', or 'close' if conflict rises.
  * Lifecycle-first: evaluate closes -> trims -> adds before any opens; opens must pass event/valuation/liquidity gates and portfolio constraints (open_slots, sector concentration).
- Position sizing guidance:
  * Scale size_value by confidence and ATR relative to price; do not exceed prefs risk targets.
  * When conflicting signals exist (e.g., bearish news with bullish signal), reduce confidence and prefer 'hold' or no trade.
- Use 'rationale' to state the key drivers (signals, trend, events, prefs). Populate rule_checks if you can, and include 1–3 alternatives_considered per symbol when relevant.
- Use 'expires_sec' to 90–180 to allow decisions to lapse and avoid re-placing every tick.
- If nothing is actionable, return {"decisions": [], "global_action": "proceed", "notes": "why"}.
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
        resp = requests.post(self.url, headers=headers, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def plan(self, planner_input: Dict[str, Any]) -> PlannerOutput:
        system = JSON_ONLY_RULES
        user = "PlannerInput JSON:\n" + json.dumps(planner_input, separators=(",", ":"), ensure_ascii=False)

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
