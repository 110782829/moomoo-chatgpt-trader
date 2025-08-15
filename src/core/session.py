"""
Persist/restore connection + account selection.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Optional

SESSION_PATH = Path("data/session.json")


def load_session() -> Optional[Dict[str, Any]]:
    try:
        if SESSION_PATH.exists():
            return json.loads(SESSION_PATH.read_text())
    except Exception:
        pass
    return None


def save_session(host: str, port: int, account_id: Optional[str], trd_env: Optional[str]) -> Dict[str, Any]:
    SESSION_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "host": host,
        "port": int(port),
        "account_id": account_id,
        "trd_env": trd_env,
    }
    SESSION_PATH.write_text(json.dumps(payload, indent=2))
    return payload


def clear_session() -> None:
    try:
        if SESSION_PATH.exists():
            SESSION_PATH.unlink()
    except Exception:
        pass
