"""
Natural language intents for command parsing.
"""

from typing import Dict, Callable, Any
import re

class Intent:
    """
    A simple representation of an intent derived from user natural language input.
    """
    def __init__(self, action: str, parameters: Dict[str, Any]):
        self.action = action
        self.parameters = parameters


# Predefined pattern mapping (to be expanded)
INTENT_PATTERNS: Dict[str, Callable[[str], "Intent"]] = {}

def parse_intent(user_input: str) -> "Intent":
    """
    Parse user natural language input into an Intent object capturing
    desired configuration changes.

    The parser recognizes phrases related to stop‑loss, take‑profit,
    risk per trade, position size, moving average windows (fast/slow),
    and trading window times like "9:30-12:00" or "between 09:45 and 12:00".

    Args:
        user_input: The natural language input from the user.

    Returns:
        An Intent describing the requested changes. The action will be
        "update_config" with a parameters dictionary when recognized,
        otherwise "unknown" with an empty dictionary.
    """
    user_input_lower = user_input.lower()
    params: Dict[str, Any] = {}

    # Stop loss percentage (e.g., "stop 1.5%" or "stop loss at 1")
    stop_match = re.search(r"(?:stop loss|stop-loss|stop)\s*(?:to|at)?\s*(\d+(?:\.\d+)?)\s*%?", user_input_lower)
    if stop_match:
        value = float(stop_match.group(1))
        params["stop_loss"] = value / 100 if value > 1 else value

    # Take profit percentage (e.g., "take profit 3%", "profit target 2.5")
    tp_match = re.search(r"(?:take profit|profit target|tp)\s*(?:to|at)?\s*(\d+(?:\.\d+)?)\s*%?", user_input_lower)
    if tp_match:
        value = float(tp_match.group(1))
        params["take_profit"] = value / 100 if value > 1 else value

    # Risk per trade percentage (e.g., "risk 0.5% per trade")
    risk_match = re.search(r"risk(?: per trade)?\s*(?:is|to|at)?\s*(\d+(?:\.\d+)?)\s*%?", user_input_lower)
    if risk_match:
        value = float(risk_match.group(1))
        params["risk_per_trade"] = value / 100 if value > 1 else value

    # Position size percentage (e.g., "position size 10%")
    pos_match = re.search(r"(?:position size|position|size)\s*(?:is|to|at)?\s*(\d+(?:\.\d+)?)\s*%?", user_input_lower)
    if pos_match:
        value = float(pos_match.group(1))
        params["position_size"] = value / 100 if value > 1 else value

    # Moving average windows (e.g., "fast 5", "slow 20")
    fast_match = re.search(r"fast(?: ma| moving average)?\s*(\d+)", user_input_lower)
    if fast_match:
        params["fast_window"] = int(fast_match.group(1))
    slow_match = re.search(r"slow(?: ma| moving average)?\s*(\d+)", user_input_lower)
    if slow_match:
        params["slow_window"] = int(slow_match.group(1))

    # Trading window times (e.g., "9:45-12:00" or "between 09:30 and 12:00")
    time_match = re.search(r"(?:between\s*)?(\d{1,2}:\d{2})\s*(?:am|pm)?\s*(?:to|and|-|–)\s*(\d{1,2}:\d{2})\s*(?:am|pm)?", user_input_lower)
    if time_match:
        start_time = time_match.group(1)
        end_time = time_match.group(2)
        params["trading_start"] = start_time
        params["trading_end"] = end_time

    if params:
        return Intent("update_config", params)
    return Intent("unknown", {})
