
# src/autopilot/schemas.py
from __future__ import annotations
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, validator
from datetime import datetime

# --- Planner Input (v1 + forward-compatible v2 field) ---

class AccountSnapshot(BaseModel):
    equity: float = 0.0
    bp: float = 0.0
    pnl_today: float = 0.0

class RiskSnapshot(BaseModel):
    max_positions: int = 0
    max_risk_bps: int = 0
    max_day_dd_bps: int = 0
    per_symbol_max_bps: int = 0

class PositionItem(BaseModel):
    sym: str
    qty: float
    avg: float

class UniverseItem(BaseModel):
    sym: str
    px: float
    atr: float
    rsi: int
    ma50: float
    ma200: float
    trend: Literal['flat','up','down']

class StrategySignal(BaseModel):
    strategy: str
    sym: str
    signal: Literal['long','short','exit','none']
    strength: float = Field(0.0, ge=0.0, le=1.0)
    ttl_sec: int = 120
    metadata: Dict[str, Any] = {}

class PlannerInput(BaseModel):
    timestamp: str
    mode: Literal['auto']
    account: AccountSnapshot
    risk: RiskSnapshot
    positions: List[PositionItem] = []
    universe: List[UniverseItem] = []
    style_summary: str = ""
    strategy_signals: List[StrategySignal] = []  # v2 optional

# --- Planner Output (strict) ---

class StopSpec(BaseModel):
    type: Literal['atr','percent','price']
    mult: Optional[float] = None
    value: Optional[float] = None

class TakeProfitSpec(BaseModel):
    type: Literal['atr','percent','price']
    mult: Optional[float] = None
    value: Optional[float] = None

class Decision(BaseModel):
    sym: str
    action: Literal['open','add','trim','close','hold']
    side: Literal['buy','sell']
    size_type: Literal['risk_bps','shares','notional']
    size_value: float
    entry: Literal['market','limit']
    limit_price: Optional[float] = None
    stop: Optional[StopSpec] = None
    take_profit: Optional[TakeProfitSpec] = None
    time_in_force: Literal['day','gtc'] = 'day'
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    expires_sec: int = 120
    rationale: str = ""

class PlannerOutput(BaseModel):
    decisions: List[Decision] = []
    global_action: Literal['proceed','pause','flatten_if_dd_exceeded'] = 'proceed'

# Helpers
def validate_output(data: dict) -> PlannerOutput:
    """
    Validates planner output dict against the strict schema and returns the model.
    Raises pydantic.ValidationError on failure.
    """
    return PlannerOutput.parse_obj(data)

def empty_output() -> PlannerOutput:
    return PlannerOutput(decisions=[], global_action='proceed')
