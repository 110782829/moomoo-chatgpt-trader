# SQLite-backed storage for strategies and run logs.

import json
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, List, Tuple
from datetime import datetime, timezone, date

DB_PATH = Path(os.getenv("TRADER_DB", "data/trader.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _conn() as c:
        # strategies & runs (existing)
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

        # --- NEW: broker execution ledger ---
        c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broker_order_id TEXT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,      -- 'BUY' | 'SELL'
            qty REAL NOT NULL,
            price REAL,
            order_type TEXT NOT NULL, -- 'MARKET' | 'LIMIT' | ...
            status TEXT NOT NULL,     -- broker status text
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("""
        CREATE INDEX IF NOT EXISTS idx_orders_broker_id ON orders(broker_order_id)
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS fills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            broker_order_id TEXT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,     -- 'BUY' | 'SELL'
            qty REAL NOT NULL,
            price REAL NOT NULL,
            ts DATETIME NOT NULL
        )""")
        c.execute("""
        CREATE INDEX IF NOT EXISTS idx_fills_ts ON fills(ts)
        """)
        c.execute("""
        CREATE INDEX IF NOT EXISTS idx_fills_symbol ON fills(symbol)
        """)

        # --- NEW: action log (bot explainability & chronology) ---
        c.execute("""
        CREATE TABLE IF NOT EXISTS action_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts DATETIME DEFAULT CURRENT_TIMESTAMP,
            mode TEXT,               -- 'assist' | 'semi' | 'auto' (optional)
            action TEXT NOT NULL,    -- 'propose' | 'place' | 'cancel' | 'flatten' | 'error' | ...
            symbol TEXT,
            side TEXT,               -- 'BUY' | 'SELL' (optional)
            qty REAL,
            price REAL,
            reason TEXT,             -- short explainer
            status TEXT,             -- 'ok' | 'blocked' | 'error' | broker status
            extra_json TEXT          -- arbitrary JSON payload
        )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_action_log_ts ON action_log(ts)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_action_log_symbol ON action_log(symbol)")


# ----- strategies & runs (existing API) -----

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


# ----- NEW: settings helpers -----

def get_setting(key: str) -> Optional[str]:
    with _conn() as c:
        cur = c.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = cur.fetchone()
        return row["value"] if row else None

def set_setting(key: str, value: Any) -> None:
    with _conn() as c:
        c.execute("INSERT INTO settings(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                  (key, json.dumps(value) if not isinstance(value, str) else value))

def all_settings() -> Dict[str, Any]:
    with _conn() as c:
        cur = c.execute("SELECT key, value FROM settings")
        out = {}
        for r in cur.fetchall():
            try:
                out[r["key"]] = json.loads(r["value"])
            except Exception:
                out[r["key"]] = r["value"]
        return out


# ----- NEW: orders/fills recording -----

def record_order(
    broker_order_id: Optional[str],
    symbol: str,
    side: str,
    qty: float,
    order_type: str,
    status: str,
    price: Optional[float] = None,
) -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO orders
               (broker_order_id, symbol, side, qty, price, order_type, status)
               VALUES (?,?,?,?,?,?,?)""",
            (str(broker_order_id) if broker_order_id else None,
             symbol, side, float(qty), price, order_type, status),
        )


def record_fill(
    broker_order_id: Optional[str],
    symbol: str,
    side: str,
    qty: float,
    price: float,
    ts_str: str,
) -> None:
    # naive de-dup: skip if same broker_order_id+ts+qty already exists
    with _conn() as c:
        cur = c.execute(
            "SELECT 1 FROM fills WHERE broker_order_id=? AND ts=? AND ABS(qty-?)<1e-9",
            (str(broker_order_id) if broker_order_id else None, ts_str, float(qty)),
        )
        if cur.fetchone():
            return
        c.execute(
            """INSERT INTO fills
               (broker_order_id, symbol, side, qty, price, ts)
               VALUES (?,?,?,?,?,?)""",
            (str(broker_order_id) if broker_order_id else None,
             symbol, side, float(qty), float(price), ts_str),
        )


# ----- NEW: Action log helpers -----

def insert_action_log(
    action: str,
    *,
    mode: Optional[str] = None,
    symbol: Optional[str] = None,
    side: Optional[str] = None,
    qty: Optional[float] = None,
    price: Optional[float] = None,
    reason: str = "",
    status: str = "ok",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO action_log(mode, action, symbol, side, qty, price, reason, status, extra_json)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (mode, action, symbol, side,
             (float(qty) if qty is not None else None),
             (float(price) if price is not None else None),
             reason, status,
             (json.dumps(extra) if extra is not None else None))
        )

def list_action_logs(
    limit: int = 100,
    symbol: Optional[str] = None,
    since_hours: Optional[int] = None,
) -> List[Dict[str, Any]]:
    where: List[str] = []
    vals: List[Any] = []
    if symbol:
        where.append("symbol = ?")
        vals.append(symbol)
    if since_hours and since_hours > 0:
        where.append("ts >= datetime('now', ?)")
        vals.append(f"-{int(since_hours)} hours")
    q = "SELECT * FROM action_log"
    if where:
        q += " WHERE " + " AND ".join(where)
    q += " ORDER BY id DESC LIMIT ?"
    vals.append(int(limit))
    with _conn() as c:
        cur = c.execute(q, tuple(vals))
        return [dict(r) for r in cur.fetchall()]


# ----- PnL (FIFO/avg-cost style, computed from fills) -----

def _iter_fills_ordered() -> List[sqlite3.Row]:
    with _conn() as c:
        cur = c.execute("SELECT * FROM fills ORDER BY ts ASC, id ASC")
        return cur.fetchall()


def pnl_history(days: int = 7) -> List[Dict[str, Any]]:
    # Walk all fills to compute realized PnL by calendar day.
    # Maintains per-symbol position & avg cost across the whole history.
    from collections import defaultdict

    pos: Dict[str, float] = defaultdict(float)
    avg: Dict[str, float] = defaultdict(float)
    realized_by_day: Dict[str, float] = defaultdict(float)

    for r in _iter_fills_ordered():
        sym = r["symbol"]
        side = str(r["side"]).upper()
        q = float(r["qty"])
        px = float(r["price"])
        d = str(r["ts"])[:10]  # YYYY-MM-DD

        if side == "BUY":
            new_pos = pos[sym] + q
            new_avg = ((avg[sym] * pos[sym]) + (px * q)) / new_pos if new_pos > 0 else 0.0
            pos[sym] = new_pos
            avg[sym] = new_avg
        else:  # SELL
            # realized vs current avg
            realized_by_day[d] += (px - avg[sym]) * q
            pos[sym] = pos[sym] - q
            if pos[sym] <= 0:
                pos[sym] = 0.0
                avg[sym] = 0.0

    # return last N days (if available) sorted asc by date
    items = sorted(realized_by_day.items(), key=lambda x: x[0])[-int(days):]
    return [{"date": k, "realized_pnl": float(v)} for k, v in items]


def pnl_today() -> Dict[str, Any]:
    hist = pnl_history(days=30)  # cheap
    today_str = datetime.now().strftime("%Y-%m-%d")
    today = 0.0
    for row in hist:
        if row["date"] == today_str:
            today = float(row["realized_pnl"])
            break
    return {"date": today_str, "realized_pnl": today}
