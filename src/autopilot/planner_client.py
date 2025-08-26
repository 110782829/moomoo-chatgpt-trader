# src/autopilot/planner_client.py
from __future__ import annotations

import os, json, re
from typing import Any, Dict, List, Optional

from .schemas import PlannerOutput, validate_output

# Env
PROVIDER = os.getenv("PLANNER_PROVIDER", "stub").strip().lower()   # "stub" | "gpt" | "openai"
FALLBACK_STUB = os.getenv("PLANNER_FALLBACK_STUB", "1").strip().lower() not in ("0", "false", "no")

# Try both locations for the GPT client
GPTPlannerClientType = None
try:
    from .planner_client_gpt import GPTPlannerClient as _GPTClient  # local package
    GPTPlannerClientType = _GPTClient
except Exception:
    try:
        from planner_client_gpt import GPTPlannerClient as _GPTClient  # top-level
        GPTPlannerClientType = _GPTClient
    except Exception:
        GPTPlannerClientType = None  # not available

# -------- helpers --------
def _sym_key(d: Dict[str, Any]) -> Optional[str]:
    return d.get("sym") or d.get("symbol") or d.get("ticker")

def _pos_map(inp: Dict[str, Any]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for p in (inp.get("positions") or []):
        s = _sym_key(p)
        if s:
            try:
                out[str(s)] = float(p.get("qty") or 0.0)
            except Exception:
                out[str(s)] = 0.0
    return out

def _universe_syms(inp: Dict[str, Any]) -> List[str]:
    syms: List[str] = []
    for u in (inp.get("universe") or []):
        s = _sym_key(u)
        if s:
            syms.append(str(s))
    return syms

# -------- open-only stub (no ping-pong) --------
class OpenOnlyStubPlanner:
    """
    Opens 1 share of the first universe symbol that is not long yet.
    Never auto-closes. Once all symbols are >= 1 share, returns no decisions.
    """
    def plan(self, planner_input: Dict[str, Any]) -> PlannerOutput:
        pos = _pos_map(planner_input)
        for s in _universe_syms(planner_input):
            if pos.get(s, 0.0) <= 0.0:
                return validate_output({
                    "decisions": [{
                        "sym": s,
                        "action": "open",
                        "side": "buy",
                        "entry": "market",
                        "size_type": "shares",
                        "size_value": 1.0,
                        "limit_price": None,
                        "time_in_force": "day",
                    }],
                    "global_action": "proceed"
                })
        return validate_output({"decisions": [], "global_action": "proceed"})

# -------- composite --------
class CompositePlanner:
    def __init__(self) -> None:
        self.stub = OpenOnlyStubPlanner()
        self.gpt = None
        if PROVIDER in ("gpt", "openai") and GPTPlannerClientType is not None:
            try:
                self.gpt = GPTPlannerClientType()
            except Exception:
                self.gpt = None  # fall back to stub if misconfigured

    def plan(self, planner_input: Dict[str, Any]) -> PlannerOutput:
        # Prefer GPT
        if self.gpt is not None:
            try:
                out = self.gpt.plan(planner_input)
                # If GPT produced any decisions, execute them
                decisions = list(getattr(out, "decisions", []))
                if len(decisions) > 0:
                    return out
                # GPT returned valid but empty -> no trade
                return out
            except Exception:
                pass  # fall through to stub (if enabled)

        # Optional fallback
        if FALLBACK_STUB:
            return self.stub.plan(planner_input)

        # No trades
        return validate_output({"decisions": [], "global_action": "proceed"})

def get_planner_client():
    return CompositePlanner()
