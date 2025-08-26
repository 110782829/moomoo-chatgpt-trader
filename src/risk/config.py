import json
import os
from pathlib import Path

RISK_PATH = Path(os.getenv("RISK_FILE", "data/risk.json"))
_DEFAULT_RISK = {
    "enabled": True,
    "max_usd_per_trade": 1000.0,
    "max_open_positions": 5,
    "max_daily_loss_usd": 200.0,
    "symbol_whitelist": [],
    "trading_hours_pt": {"start": "06:30", "end": "13:00"},
    "flatten_before_close_min": 5,
}

# Load risk config from file or create default
def load_config() -> dict:
    try:
        if RISK_PATH.exists():
            return json.loads(RISK_PATH.read_text())
    except Exception:
        pass
    RISK_PATH.parent.mkdir(parents=True, exist_ok=True)
    RISK_PATH.write_text(json.dumps(_DEFAULT_RISK, indent=2))
    return dict(_DEFAULT_RISK)

# Save risk config to file
def save_config(cfg: dict) -> None:
    RISK_PATH.parent.mkdir(parents=True, exist_ok=True)
    RISK_PATH.write_text(json.dumps(cfg, indent=2))

