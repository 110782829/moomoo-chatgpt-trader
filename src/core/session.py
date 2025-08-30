"""
Persist/restore connection + account selection.
"""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Dict, Optional

from core.moomoo_client import MoomooClient
from core.futu_client import TrdEnv

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


def reconnect_from_session() -> Optional[MoomooClient]:
    """Try connect using saved session."""
    s = load_session()
    if not s:
        return None
    host = s.get("host")
    port = s.get("port")
    if not host or not port:
        return None
    try:
        c = MoomooClient(host, int(port))
        c.connect()
        acc = s.get("account_id")
        env = s.get("trd_env")
        if acc and env:
            env_obj = TrdEnv.SIMULATE if str(env).upper() == "SIMULATE" else TrdEnv.REAL
            try:
                c.set_account(str(acc), env_obj)
            except Exception:
                pass
        return c
    except Exception:
        return None
