"""
Storage utilities for the trading bot.

This module encapsulates database interactions using SQLModel. It provides a
simple interface to create the database engine and obtain sessions for
executing queries and persisting models.
"""

from sqlmodel import SQLModel, create_engine, Session
from typing import Generator

class Storage:
    """
    Storage handles database connections and session management.
    """

    def __init__(self, db_url: str = "sqlite:///data/trading.db") -> None:
        """
        Initialize the storage backend.

        Args:
            db_url (str): Database URL. Defaults to a SQLite file in the data directory.
        """
        # Create the engine. The `echo` flag can be toggled for SQL debugging.
        self.engine = create_engine(db_url, echo=False)
        # Create all tables defined in models
        SQLModel.metadata.create_all(self.engine)

    def get_session(self) -> Generator[Session, None, None]:
        """
        Provide a context-managed session for database operations.

        Yields:
            Session: A SQLModel Session instance.
        """
        with Session(self.engine) as session:
            yield session

# SQLite-backed storage for strategies and run logs.

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, List

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
