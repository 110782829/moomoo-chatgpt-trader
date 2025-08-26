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
      "symbol": "US.AAPL",
      "action": "open" | "close",
      "side": "buy" | "sell",             // required for action=open; ignored for close
      "entry": "market" | "limit",
      "size_type": "shares" | "notional" | "risk_bps",
      "size_value": number,
      "limit_price": number | null,       // only when entry=limit
      "time_in_force": "day" | "gtc"
    }
  ],
  "global_action": "proceed" | "pause"
}
Rules:
- Return ONLY JSON. No commentary, no Markdown, no code fences.
- Symbols look like 'US.TICKER' (no spaces).
- When action='open', 'side' is required.
- Use conservative sizes suitable for SIM.
- If nothing is actionable, return {"decisions": [], "global_action": "proceed"}.
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
