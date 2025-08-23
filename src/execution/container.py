import os
import sqlite3
from pathlib import Path
from fastapi import Request
from .sim import SimBroker
from .base import ExecutionService

# Use same DB file as the rest of the app, override with DB_PATH if needed.
_DB_PATH = os.environ.get("DB_PATH", "data.db")


_ORDERS_FILLS_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS orders (
  order_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  status TEXT NOT NULL,
  account_id TEXT NOT NULL,
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
CREATE INDEX IF NOT EXISTS idx_orders_created ON orders(created_at DESC);

CREATE TABLE IF NOT EXISTS fills (
  fill_id TEXT PRIMARY KEY,
  order_id TEXT NOT NULL,
  ts TEXT NOT NULL,
  symbol TEXT NOT NULL,
  qty INTEGER NOT NULL,
  price REAL NOT NULL,
  FOREIGN KEY(order_id) REFERENCES orders(order_id)
);

CREATE INDEX IF NOT EXISTS idx_fills_order ON fills(order_id);
CREATE INDEX IF NOT EXISTS idx_fills_ts ON fills(ts DESC);
"""


def _ensure_dirs(db_path: str) -> None:
    # If DB_PATH includes a directory (e.g., "data/data.db"), create it.
    p = Path(db_path).expanduser().resolve()
    if p.parent and not p.parent.exists():
        p.parent.mkdir(parents=True, exist_ok=True)


def _ensure_schema(conn: sqlite3.Connection) -> None:
    # Create orders/fills tables if they don't exist.
    conn.executescript(_ORDERS_FILLS_SCHEMA)
    conn.commit()


def init_execution(app) -> None:
    """
    Initialize the execution service (SimBroker) and ensure required tables exist.
    Call this once during app startup (e.g., in server.py after creating FastAPI app).
    """
    db_path = os.environ.get("DB_PATH", _DB_PATH)
    _ensure_dirs(db_path)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    # Enforce foreign keys and create tables on first run.
    conn.execute("PRAGMA foreign_keys = ON;")
    _ensure_schema(conn)
    app.state.execution_service = SimBroker(conn)


def get_execution(request: Request) -> ExecutionService:
    """
    Retrieve the initialized execution service from FastAPI app state.
    """
    svc = getattr(request.app.state, "execution_service", None)
    if svc is None:
        # Defensive: if not initialized for some reason, initialize on-demand with default path.
        init_execution(request.app)
        svc = request.app.state.execution_service
    return svc
