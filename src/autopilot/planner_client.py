# src/autopilot/planner_client.py
from __future__ import annotations
from typing import Dict, Any
from .schemas import PlannerOutput, validate_output

class PlannerClient:
    """
    Deterministic SIM-friendly stub:
    - Pick the first symbol in universe with price > 0 (fallback: the first symbol).
    - If not already long (qty <= 0), emit a single 1-share MARKET BUY (time_in_force=day).
    - Otherwise, no decisions.
    This guarantees at least one decision most of the time so the Act stage can be exercised.
    """
    def plan(self, planner_input: Dict[str, Any]) -> PlannerOutput:
        # map current positions by symbol
        pos_map = {}
        for p in (planner_input.get("positions") or []):
            sym = str(p.get("sym") or "")
            if sym:
                try:
                    pos_map[sym] = float(p.get("qty") or 0.0)
                except Exception:
                    pos_map[sym] = 0.0

        universe = list(planner_input.get("universe") or [])
        pick = None
        # prefer any with price > 0
        for u in universe:
            if float(u.get("px") or 0.0) > 0:
                pick = u
                break
        if pick is None and universe:
            pick = universe[0]

        decisions = []
        if pick is not None:
            sym = str(pick.get("sym") or "")
            if sym and pos_map.get(sym, 0.0) <= 0.0:
                decisions.append({
                    "sym": sym,
                    "action": "open",
                    "side": "buy",
                    "size_type": "shares",
                    "size_value": 1.0,
                    "entry": "market",
                    "limit_price": None,
                    "time_in_force": "day",
                })

        out = {"decisions": decisions, "global_action": "proceed"}
        return validate_output(out)

def get_planner_client() -> PlannerClient:
    return PlannerClient()
