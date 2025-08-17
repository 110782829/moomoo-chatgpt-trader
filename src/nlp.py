"""Map natural-language commands to actions."""
from __future__ import annotations

def parse_command(text: str) -> dict:
    t = text.lower().strip()
    if "start autopilot" in t:
        return {"action": "start_autopilot"}
    if "stop autopilot" in t:
        return {"action": "stop_autopilot"}
    if "run backtest" in t:
        return {"action": "run_backtest"}
    if t.startswith("set strategy"):
        name = t.split("set strategy", 1)[1].strip()
        return {"action": "set_strategy", "name": name}
    if "status" in t:
        return {"action": "status"}
    return {"action": "unknown", "text": text}
