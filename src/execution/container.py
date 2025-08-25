# src/execution/container.py
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

# Use a single process-wide SQLite connection (thread-safe for FastAPI with check_same_thread=False)
_DB_PATH = Path(__file__).resolve().parents[2] / "db" / "trader.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_conn: Optional[sqlite3.Connection] = None

ORDERS_SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
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
CREATE INDEX IF NOT EXISTS idx_orders_symbol ON orders(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
"""

FILLS_SCHEMA = """
CREATE TABLE IF NOT EXISTS fills (
  fill_id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  symbol TEXT NOT NULL,
  qty INTEGER NOT NULL,
  price REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fills_symbol ON fills(symbol);
CREATE INDEX IF NOT EXISTS idx_fills_order ON fills(order_id);
"""

POSITIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
  symbol TEXT PRIMARY KEY,
  qty INTEGER NOT NULL,
  avg_cost REAL NOT NULL,
  realized_today REAL NOT NULL
);
"""

def _get_conn() -> sqlite3.Connection:
  global _conn
  if _conn is None:
    _conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    _conn.row_factory = sqlite3.Row
  return _conn

def _ensure_tables() -> None:
  conn = _get_conn()
  conn.executescript(ORDERS_SCHEMA + FILLS_SCHEMA + POSITIONS_SCHEMA)
  conn.commit()

# Public: init at app startup
def init_execution(app=None) -> None:
  _ensure_tables()
  try:
    if app is not None:
      # attach to lifespan: nothing heavy here, just ensure tables exist
      pass
  except Exception:
    pass

# Public: get the active execution service (SimBroker for now)
def get_execution():
  from .sim import SimBroker
  return SimBroker(_get_conn())
