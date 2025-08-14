# SQLite-backed storage for strategies and run logs.

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple

DB_PATH = Path(os.getenv("TRADER_DB", "data/trader.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> None:
    with _conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS strategies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            symbol TEXT NOT NULL,
            params_json TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            interval_sec INTEGER NOT NULL DEFAULT 15,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id INTEGER NOT NULL,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP,
            status TEXT NOT NULL,
            message TEXT,
            FOREIGN KEY(strategy_id) REFERENCES strategies(id)
        )""")
        c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")

def insert_strategy(name: str, symbol: str, params: Dict[str, Any], interval_sec: int) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO strategies (name, symbol, params_json, interval_sec, active) VALUES (?,?,?,?,1)",
            (name, symbol, json.dumps(params), interval_sec),
        )
        return cur.lastrowid

def set_strategy_active(strategy_id: int, active: bool) -> None:
    with _conn() as c:
        c.execute("UPDATE strategies SET active=? WHERE id=?", (1 if active else 0, strategy_id))

def get_strategy(strategy_id: int) -> Optional[Dict[str, Any]]:
    with _conn() as c:
        cur = c.execute("SELECT * FROM strategies WHERE id=?", (strategy_id,))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "symbol": row["symbol"],
            "params": json.loads(row["params_json"]),
            "active": bool(row["active"]),
            "interval_sec": int(row["interval_sec"]),
            "created_at": row["created_at"],
        }

def list_strategies() -> List[Dict[str, Any]]:
    with _conn() as c:
        cur = c.execute("SELECT * FROM strategies ORDER BY id DESC")
        rows = cur.fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            out.append({
                "id": r["id"],
                "name": r["name"],
                "symbol": r["symbol"],
                "params": json.loads(r["params_json"]),
                "active": bool(r["active"]),
                "interval_sec": int(r["interval_sec"]),
                "created_at": r["created_at"],
            })
        return out

def insert_run(strategy_id: int, status: str, message: str = "") -> None:
    with _conn() as c:
        c.execute(
            "INSERT INTO runs (strategy_id, status, message) VALUES (?,?,?)",
            (strategy_id, status, message),
        )

def list_runs(strategy_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    with _conn() as c:
        cur = c.execute(
            "SELECT * FROM runs WHERE strategy_id=? ORDER BY id DESC LIMIT ?",
            (strategy_id, limit),
        )
        return [dict(r) for r in cur.fetchall()]

def update_strategy(
    strategy_id: int,
    params: Optional[Dict[str, Any]] = None,
    interval_sec: Optional[int] = None,
    active: Optional[bool] = None,
) -> Optional[Dict[str, Any]]:
    cur = get_strategy(strategy_id)
    if not cur:
        return None

    # merge params if provided
    new_params = cur["params"].copy()
    if params:
        for k, v in params.items():
            if v is not None:
                new_params[k] = v

    sets: List[str] = []
    vals: List[Any] = []

    if params is not None:
        sets.append("params_json=?")
        vals.append(json.dumps(new_params))

    if interval_sec is not None:
        sets.append("interval_sec=?")
        vals.append(int(interval_sec))

    if active is not None:
        sets.append("active=?")
        vals.append(1 if active else 0)

    if sets:
        with _conn() as c:
            q = f"UPDATE strategies SET {', '.join(sets)} WHERE id=?"
            vals.append(strategy_id)
            c.execute(q, tuple(vals))

    return get_strategy(strategy_id)
