
# src/autopilot/planner_client.py
from __future__ import annotations
from typing import Dict, Any
from .schemas import PlannerInput, PlannerOutput, empty_output, validate_output

class PlannerClient:
    """
    Stubbed planner client. In v1, returns an empty 'proceed' output.
    Later, this can call an LLM and must return strict JSON matching PlannerOutput.
    """
    def __init__(self):
        pass

    def plan(self, planner_input: Dict[str, Any]) -> PlannerOutput:
        # For now: always return empty decisions
        out = {"decisions": [], "global_action": "proceed"}
        return validate_output(out)

def get_planner_client() -> PlannerClient:
    return PlannerClient()
