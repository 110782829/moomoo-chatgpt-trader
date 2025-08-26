# src/execution/container.py
from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

# Choose a stable DB path aligned with your repo layout.
# You can override with ENV EXEC_DB_PATH if you prefer a different file.
_DB_PATH = Path(os.getenv("EXEC_DB_PATH") or "db/trader.db")
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_conn: Optional[sqlite3.Connection] = None

# --- Desired schemas (canonical) ---

ORDERS_TABLE = "orders"
ORDERS_COLS: Dict[str, str] = {
    "order_id": "TEXT",                    # preferred PK (may not be PK if table pre-existed)
    "created_at": "TEXT NOT NULL",
    "updated_at": "TEXT NOT NULL",
    "status": "TEXT NOT NULL",
    "account_id": "TEXT",
    "symbol": "TEXT NOT NULL",
    "side": "TEXT NOT NULL",
    "order_type": "TEXT NOT NULL",
    "limit_price": "REAL",
    "tif": "TEXT NOT NULL",
    "requested_qty": "INTEGER NOT NULL",
    "filled_qty": "INTEGER NOT NULL",
    "avg_fill_price": "REAL",
    "decision_id": "INTEGER",
    "reject_reason": "TEXT",
}

FILLS_TABLE = "fills"
FILLS_COLS: Dict[str, str] = {
    "fill_id": "TEXT",                     # preferred PK (may not be PK if table pre-existed)
    "order_id": "TEXT",
    "ts": "TEXT NOT NULL",
    "symbol": "TEXT NOT NULL",
    "qty": "INTEGER NOT NULL",
    "price": "REAL NOT NULL",
}

POSITIONS_TABLE = "positions"
POSITIONS_COLS: Dict[str, str] = {
    "symbol": "TEXT",
    "qty": "INTEGER NOT NULL",
    "avg_cost": "REAL NOT NULL",
    "realized_today": "REAL NOT NULL",
}

CREATE_ORDERS = f"""
CREATE TABLE IF NOT EXISTS {ORDERS_TABLE} (
  order_id TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  status TEXT NOT NULL,
  account_id TEXT,
  symbol TEXT NOT NULL,
  side TEXT NOT NULL,
  order_type TEXT NOT NULL,
  limit_price REAL,
  tif TEXT NOT NULL,
  requested_qty INTEGER NOT NULL,
  filled_qty INTEGER NOT NULL,
  avg_fill_price REAL,
  decision_id INTEGER,
  reject_reason TEXT
);
"""
CREATE_FILLS = f"""
CREATE TABLE IF NOT EXISTS {FILLS_TABLE} (
  fill_id TEXT,
  order_id TEXT,
  ts TEXT NOT NULL,
  symbol TEXT NOT NULL,
  qty INTEGER NOT NULL,
  price REAL NOT NULL
);
"""
CREATE_POSITIONS = f"""
CREATE TABLE IF NOT EXISTS {POSITIONS_TABLE} (
  symbol TEXT,
  qty INTEGER NOT NULL,
  avg_cost REAL NOT NULL,
  realized_today REAL NOT NULL
);
"""

INDEXES: Tuple[Tuple[str, str, Iterable[str]], ...] = (
    ("idx_orders_symbol", f"CREATE INDEX IF NOT EXISTS idx_orders_symbol ON {ORDERS_TABLE}(symbol)", ("symbol",)),
    ("idx_orders_status", f"CREATE INDEX IF NOT EXISTS idx_orders_status ON {ORDERS_TABLE}(status)", ("status",)),
    ("idx_fills_symbol", f"CREATE INDEX IF NOT EXISTS idx_fills_symbol ON {FILLS_TABLE}(symbol)", ("symbol",)),
    ("idx_fills_order",  f"CREATE INDEX IF NOT EXISTS idx_fills_order  ON {FILLS_TABLE}(order_id)", ("order_id",)),
)

def _get_conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
    return _conn

def _columns(conn: sqlite3.Connection, table: str) -> Dict[str, bool]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    cols = {row["name"]: True for row in cur.fetchall()}
    return cols

def _ensure_table(conn: sqlite3.Connection, create_sql: str, table: str, required: Dict[str, str]) -> None:
    conn.execute(create_sql)  # no-op if already exists
    existing = _columns(conn, table)
    for col, decl in required.items():
        if col not in existing:
            # Best-effort: add missing column with a compatible type
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    conn.commit()

def _ensure_indexes(conn: sqlite3.Connection) -> None:
    # Only create an index if all its columns exist in the table (avoids "no such column" failures)
    ord_cols = _columns(conn, ORDERS_TABLE)
    fil_cols = _columns(conn, FILLS_TABLE)
    for name, sql, cols in INDEXES:
        needed = set(cols)
        have = ord_cols if "orders" in sql else fil_cols
        if not needed.issubset(have):
            continue
        try:
            conn.execute(sql)
        except sqlite3.OperationalError:
            # ignore indexes that still fail for any reason
            pass
    conn.commit()

def _ensure_tables() -> None:
    conn = _get_conn()
    _ensure_table(conn, CREATE_ORDERS, ORDERS_TABLE, ORDERS_COLS)
    _ensure_table(conn, CREATE_FILLS, FILLS_TABLE, FILLS_COLS)
    _ensure_table(conn, CREATE_POSITIONS, POSITIONS_TABLE, POSITIONS_COLS)
    _ensure_indexes(conn)

def init_execution(app=None) -> None:
    """Initialize SIM execution storage (idempotent). Call once at app startup."""
    _ensure_tables()

def get_execution():
    """Return the execution service (SimBroker)."""
    from .sim import SimBroker
    return SimBroker(_get_conn())
