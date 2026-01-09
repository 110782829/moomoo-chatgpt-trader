# src/autopilot/planner_client.py
from __future__ import annotations

import os, json, re
from typing import Any, Dict, List, Optional

from .schemas import PlannerOutput, validate_output

# Env
PROVIDER = os.getenv("PLANNER_PROVIDER", "stub").strip().lower()   # "stub" | "gpt" | "openai"
# Auto-upgrade to GPT if API key is present and provider left as default 'stub'
try:
    if PROVIDER == "stub" and (os.getenv("OPENAI_API_KEY", "").strip()):
        PROVIDER = "gpt"
except Exception:
    pass
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
    Minimal fallback planner.
    Prefers closing high-risk positions using exit hints when GPT is unavailable,
    otherwise opens 1 share of the first universe symbol that is not long yet.
    """
    def plan(self, planner_input: Dict[str, Any]) -> PlannerOutput:
        pos = _pos_map(planner_input)
        exits = planner_input.get("positions_exit_candidates") or []
        if exits and isinstance(exits, list):
            for cand in exits:
                try:
                    sym = str(cand.get("sym") or "")
                    if not sym:
                        continue
                    qty_live = float(pos.get(sym) or 0.0)
                    if qty_live == 0.0:
                        continue
                    exit_bias = str(cand.get("exit_bias") or "")
                    score = float(cand.get("exit_score") or 0.0)
                    if exit_bias == "close" or score >= 0.6:
                        side = "sell" if qty_live > 0 else "buy"
                        size_val = abs(int(qty_live)) or 1
                        return validate_output({
                            "decisions": [{
                                "sym": sym,
                                "action": "close",
                                "side": side,
                                "entry": "market",
                                "size_type": "shares",
                                "size_value": float(size_val),
                                "limit_price": None,
                                "time_in_force": "day",
                                "confidence": max(0.3, min(0.9, score or 0.6)),
                                "expires_sec": 180,
                                "rationale": "stub_close_exit_signal",
                            }],
                            "global_action": "proceed",
                        })
                    if exit_bias == "trim" and abs(qty_live) > 1:
                        side = "sell" if qty_live > 0 else "buy"
                        trim_size = max(1, abs(int(qty_live)) // 2)
                        return validate_output({
                            "decisions": [{
                                "sym": sym,
                                "action": "trim",
                                "side": side,
                                "entry": "market",
                                "size_type": "shares",
                                "size_value": float(trim_size),
                                "limit_price": None,
                                "time_in_force": "day",
                                "confidence": max(0.2, min(0.7, score or 0.4)),
                                "expires_sec": 180,
                                "rationale": "stub_trim_exit_signal",
                            }],
                            "global_action": "proceed",
                        })
                except Exception:
                    continue
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
                        "confidence": 0.4,
                        "expires_sec": 180,
                        "rationale": "stub_open_first_available",
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
                return self.gpt.plan(planner_input)
            except Exception:
                if not FALLBACK_STUB:
                    raise
                # fall through to stub when enabled
                pass

        # Optional fallback
        if FALLBACK_STUB:
            return self.stub.plan(planner_input)

        # No trades
        return validate_output({"decisions": [], "global_action": "proceed"})

def get_planner_client():
    return CompositePlanner()
