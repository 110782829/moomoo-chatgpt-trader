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
      "side": "buy" | "sell",                 // required for action=open/add/trim; ignored for close/hold
      "entry": "market" | "limit",
      "size_type": "shares" | "notional" | "risk_bps",
      "size_value": number,
      "limit_price": number | null,           // only when entry=limit
      "time_in_force": "day" | "gtc",
      "stop": {"type":"atr"|"percent"|"price","mult":number|null,"value":number|null} | null,
      "take_profit": {"type":"atr"|"percent"|"price","mult":number|null,"value":number|null} | null,
      "confidence": number,                   // 0..1
      "expires_sec": number,                  // suggested time-to-live for this decision
      "rationale": string                     // short reason
    }
  ],
  "global_action": "proceed" | "pause"
}
Rules:
- Return ONLY JSON. No commentary, no Markdown, no code fences.
- Symbols look like 'US.TICKER' (no spaces).
- Use conservative sizes suitable for SIM.
- Use inputs if provided: account/risk/positions/universe (with rsi/atr/ma50/ma200/trend/px and interest rank), prefs (targets), style_summary (user constraints), strategy_signals (ttl+strength), and news (summary/tone).
- Favor fewer, high-confidence decisions; include stop/take_profit when prefs exist.
 - Favor fewer, high-confidence decisions; include stop/take_profit when prefs exist.
 - If planner.strict_prefs=true and prefs include stop/take/ATR guidance, you MUST include stop and appropriate take_profit for action=open, otherwise your decision will be rejected.
- If nothing is actionable, return {"decisions": [], "global_action": "proceed"}.

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

Conflict example (signals vs news):
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
      "expires_sec":120,"rationale":"Conflicting: RSI short vs bullish news; wait"}
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
    return m.group(0) if m else '{"decisions":[],"global_action":"proceed"}'


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

        # Fallback: empty, schema-valid output
        try:
            return validate_output({"decisions": [], "global_action": "proceed"})
        except Exception:
            return PlannerOutput(decisions=[], global_action="proceed")  # type: ignore
