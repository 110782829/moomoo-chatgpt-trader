# src/execution/sim.py
import sqlite3
import time
import uuid
from typing import Dict, List, Optional, Any

from .base import ExecutionService, ExecutionContext
from .types import (
    OrderSpec,
    PlacedOrder,
    FillRecord,
    OrderStatus,
    OrderType,
    OrderSide,
    TimeInForce,
)


def _utc_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# Synthetic fallback price for MARKET fills when no last is available
DEFAULT_MARKET_SYNTH_PRICE = 100.0

# Positions schema (defensive; container can also create this)
_POSITIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
  symbol TEXT PRIMARY KEY,
  qty INTEGER NOT NULL,
  avg_cost REAL NOT NULL,
  realized_today REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
"""


class SimBroker(ExecutionService):
    """
    Simple paper engine backed by SQLite.

    Fills:
      - Market: immediate at last price (from last known tick/fill you pass in).
               If last is missing/zero, falls back to most recent fill; else a synthetic price.
      - Limit: fill if crossed, else remains OPEN; try_fill_resting() attempts later fills.

    Sizing:
      - shares   -> size_value
      - notional -> floor(size_value / last)
      - risk_bps -> floor((equity * bps/10000) / last)

    Maintains positions (symbol, signed qty, avg_cost, realized_today).
    Exposes list_positions() and pnl_today().
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_POSITIONS_SCHEMA)
        self.conn.commit()

    # ---------------- internals: order/fill rows ----------------

    def _insert_order(self, row) -> None:
        self.conn.execute(
            """
            INSERT INTO orders (
                order_id, created_at, updated_at, status, account_id,
                symbol, side, order_type, limit_price, tif,
                requested_qty, filled_qty, avg_fill_price, decision_id, reject_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["order_id"],
                row["created_at"],
                row["updated_at"],
                row["status"],
                row["account_id"],
                row["symbol"],
                row["side"],
                row["order_type"],
                row["limit_price"],
                row["tif"],
                row["requested_qty"],
                row["filled_qty"],
                row["avg_fill_price"],
                row["decision_id"],
                row["reject_reason"],
            ),
        )
        self.conn.commit()

    def _insert_fill(self, fill) -> None:
        self.conn.execute(
            "INSERT INTO fills (fill_id, order_id, ts, symbol, qty, price) VALUES (?, ?, ?, ?, ?, ?)",
            (fill["fill_id"], fill["order_id"], fill["ts"], fill["symbol"], fill["qty"], fill["price"]),
        )
        self.conn.commit()

    def _row_to_order(self, r) -> PlacedOrder:
        return PlacedOrder(
            order_id=r["order_id"],
            status=OrderStatus(r["status"]),
            symbol=r["symbol"],
            side=OrderSide(r["side"]),
            order_type=OrderType(r["order_type"]),
            limit_price=r["limit_price"],
            requested_qty=r["requested_qty"],
            filled_qty=r["filled_qty"],
            avg_fill_price=r["avg_fill_price"],
            tif=TimeInForce(r["tif"]),
            decision_id=r["decision_id"],
            created_at=r["created_at"],
            updated_at=r["updated_at"],
            reject_reason=r["reject_reason"],
        )

    def _compute_qty(self, spec: OrderSpec, ctx: ExecutionContext) -> int:
        # Shares don't need last price
        if spec.size_type == "shares":
            return max(0, int(spec.size_value))

        # For notional / risk_bps we need a price; try ctx, then recent fill
        last = (ctx.last_prices or {}).get(spec.symbol)
        if last is None or last <= 0:
            try:
                last = self._recent_last(spec.symbol)  # falls back to last fill if you have it
            except Exception:
                last = None
        if last is None or last <= 0:
            return 0

        if spec.size_type == "notional":
            return max(0, int(spec.size_value // last))
        if spec.size_type == "risk_bps":
            notional = float(ctx.equity) * (float(spec.size_value) / 10000.0)
            return max(0, int(notional // last))
        return 0

    # ---------------- positions helpers ----------------

    def _recent_last(self, symbol: str) -> Optional[float]:
        cur = self.conn.execute("SELECT price FROM fills WHERE symbol = ? ORDER BY ts DESC LIMIT 1", (symbol,))
        r = cur.fetchone()
        return float(r["price"]) if r else None

    def _load_pos(self, symbol: str) -> Optional[sqlite3.Row]:
        cur = self.conn.execute("SELECT * FROM positions WHERE symbol = ?", (symbol,))
        return cur.fetchone()

    def _save_pos(self, symbol: str, qty: int, avg_cost: float, realized_today_add: float = 0.0) -> None:
        cur = self.conn.execute("SELECT realized_today FROM positions WHERE symbol = ?", (symbol,))
        row = cur.fetchone()
        if row:
            realized = float(row["realized_today"]) + float(realized_today_add)
            self.conn.execute(
                "UPDATE positions SET qty = ?, avg_cost = ?, realized_today = ? WHERE symbol = ?",
                (qty, avg_cost, realized, symbol),
            )
        else:
            self.conn.execute(
                "INSERT INTO positions (symbol, qty, avg_cost, realized_today) VALUES (?, ?, ?, ?)",
                (symbol, qty, avg_cost, float(realized_today_add)),
            )
        self.conn.commit()

    def _realize(self, side: str, qty: int, price: float, cur_qty: int, avg_cost: float) -> float:
        """Realized PnL for the portion that closes existing exposure."""
        realized = 0.0
        if side == OrderSide.sell.value and cur_qty > 0:
            close_qty = min(qty, cur_qty)
            realized += (price - avg_cost) * close_qty
        elif side == OrderSide.buy.value and cur_qty < 0:
            close_qty = min(qty, -cur_qty)
            realized += (avg_cost - price) * close_qty
        return realized

    def _update_position_on_fill(self, symbol: str, side: str, qty: int, price: float) -> None:
        r = self._load_pos(symbol)
        cur_qty = int(r["qty"]) if r else 0
        avg_cost = float(r["avg_cost"]) if r else 0.0

        realized_add = self._realize(side, qty, price, cur_qty, avg_cost)

        if side == OrderSide.buy.value:
            if cur_qty >= 0:
                new_qty = cur_qty + qty
                new_avg = ((cur_qty * avg_cost) + (qty * price)) / max(1, new_qty)
            else:
                new_qty = cur_qty + qty
                if new_qty < 0:
                    new_avg = avg_cost
                elif new_qty == 0:
                    new_avg = 0.0
                else:
                    new_avg = price  # flipped to long; start fresh
        else:  # sell
            if cur_qty <= 0:
                new_qty = cur_qty - qty  # more short
                new_avg = ((abs(cur_qty) * avg_cost) + (qty * price)) / max(1, abs(new_qty))
            else:
                new_qty = cur_qty - qty
                if new_qty > 0:
                    new_avg = avg_cost
                elif new_qty == 0:
                    new_avg = 0.0
                else:
                    new_avg = price  # flipped to short; start fresh

        self._save_pos(symbol, int(new_qty), float(new_avg), realized_today_add=realized_add)

    # ---------------- fill logic ----------------

    def _maybe_fill_now(self, order_row, last_price: Optional[float]) -> Optional[FillRecord]:
        # Normalize last price; treat None/zero as missing and fallback
        lp = float(last_price) if (last_price is not None) else None
        if lp is None or lp <= 0.0:
            lp = self._recent_last(order_row["symbol"])

        side = order_row["side"]

        if order_row["order_type"] == OrderType.market.value:
            qty = int(order_row["requested_qty"])
            # For market orders, if we still have no price, use a synthetic nonzero
            if lp is None or lp <= 0.0:
                lp = float(DEFAULT_MARKET_SYNTH_PRICE)
            price = float(lp)

        else:  # LIMIT logic requires a price to compare/cross
            if lp is None or lp <= 0.0:
                return None
            limit_px = order_row["limit_price"]
            if limit_px is None:
                return None
            if side in (OrderSide.buy.value, OrderSide.buy_to_cover.value):
                if lp <= float(limit_px):
                    qty = int(order_row["requested_qty"])
                    price = float(min(limit_px, lp))
                else:
                    return None
            else:
                if lp >= float(limit_px):
                    qty = int(order_row["requested_qty"])
                    price = float(max(limit_px, lp))
                else:
                    return None

        fill_id = uuid.uuid4().hex
        ts = _utc_ts()
        self._insert_fill(
            {"fill_id": fill_id, "order_id": order_row["order_id"], "ts": ts, "symbol": order_row["symbol"], "qty": qty, "price": price}
        )
        self.conn.execute(
            "UPDATE orders SET status = ?, filled_qty = ?, avg_fill_price = ?, updated_at = ? WHERE order_id = ?",
            (OrderStatus.filled.value, qty, price, ts, order_row["order_id"]),
        )
        self.conn.commit()

        self._update_position_on_fill(order_row["symbol"], side, int(qty), float(price))
        return FillRecord(
            fill_id=fill_id, order_id=order_row["order_id"], symbol=order_row["symbol"], qty=qty, price=price, ts=ts
        )

    # ---------------- ExecutionService interface ----------------

    def place_order(self, spec: OrderSpec, ctx: ExecutionContext) -> PlacedOrder:
        ts = _utc_ts()
        last = ctx.last_prices.get(spec.symbol)
        requested_qty = self._compute_qty(spec, ctx)

        order_id = uuid.uuid4().hex
        row = {
            "order_id": order_id,
            "created_at": ts,
            "updated_at": ts,
            "status": OrderStatus.pending.value,
            "account_id": ctx.account_id,
            "symbol": spec.symbol,
            "side": spec.side.value,
            "order_type": spec.order_type.value,
            "limit_price": spec.limit_price,
            "tif": spec.tif.value,
            "requested_qty": requested_qty,
            "filled_qty": 0,
            "avg_fill_price": None,
            "decision_id": spec.decision_id,
            "reject_reason": None,
        }

        if requested_qty < 1:
            row["status"] = OrderStatus.rejected.value
            row["reject_reason"] = "sizing_zero_qty"
            self._insert_order(row)
            return self._row_to_order(row)

        row["status"] = OrderStatus.open.value if spec.order_type == OrderType.limit else OrderStatus.pending.value
        self._insert_order(row)

        fill = self._maybe_fill_now(row, last)
        if not fill:
            self.conn.execute(
                "UPDATE orders SET status = ?, updated_at = ? WHERE order_id = ?",
                (OrderStatus.open.value, _utc_ts(), order_id),
            )
            self.conn.commit()

        cur = self.conn.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
        return self._row_to_order(cur.fetchone())

    def cancel_order(self, order_id: str) -> bool:
        ts = _utc_ts()
        cur = self.conn.execute("SELECT status FROM orders WHERE order_id = ?", (order_id,))
        r = cur.fetchone()
        if not r:
            return False
        if r["status"] in (OrderStatus.filled.value, OrderStatus.canceled.value, OrderStatus.rejected.value):
            return False
        self.conn.execute(
            "UPDATE orders SET status = ?, updated_at = ? WHERE order_id = ?",
            (OrderStatus.canceled.value, ts, order_id),
        )
        self.conn.commit()
        return True

    def try_fill_resting(self, last_prices: Dict[str, float]) -> None:
        cur = self.conn.execute(
            "SELECT * FROM orders WHERE status IN (?, ?) AND order_type = ?",
            (OrderStatus.open.value, OrderStatus.pending.value, OrderType.limit.value),
        )
        rows = cur.fetchall()
        for r in rows:
            last = last_prices.get(r["symbol"])
            self._maybe_fill_now(r, last)

    def list_orders(self, *, symbol: Optional[str] = None, status: Optional[str] = None, limit: int = 200):
        q = "SELECT * FROM orders"
        clauses, params = [], []
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if status:
            clauses.append("status = ?")
            params.append(status)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cur = self.conn.execute(q, tuple(params))
        return [self._row_to_order(r) for r in cur.fetchall()]

    def list_fills(self, *, symbol: Optional[str] = None, limit: int = 500):
        q = "SELECT * FROM fills"
        params = []
        if symbol:
            q += " WHERE symbol = ?"
            params.append(symbol)
        q += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        cur = self.conn.execute(q, tuple(params))
        out = []
        for r in cur.fetchall():
            out.append(FillRecord(fill_id=r["fill_id"], order_id=r["order_id"], ts=r["ts"], symbol=r["symbol"], qty=r["qty"], price=r["price"]))
        return out

    # ---------------- positions & pnl ----------------

    def list_positions(self) -> List[Dict[str, Any]]:
        cur = self.conn.execute("SELECT symbol, qty, avg_cost, realized_today FROM positions ORDER BY symbol")
        rows = cur.fetchall()
        out: List[Dict[str, Any]] = []
        for r in rows:
            sym = r["symbol"]
            qty = int(r["qty"])
            avg = float(r["avg_cost"])
            last = self._recent_last(sym)
            mv = (last * qty) if last is not None else None
            upl = ((last - avg) * qty) if (last is not None and qty != 0) else None
            out.append(
                {
                    "symbol": sym,
                    "qty": qty,
                    "avg_cost": avg,
                    "last": last,
                    "mv": mv,
                    "upl": upl,
                    "rpl_today": float(r["realized_today"]),
                }
            )
        return out

    def pnl_today(self) -> Dict[str, Any]:
        cur = self.conn.execute("SELECT COALESCE(SUM(realized_today), 0.0) AS r FROM positions")
        r = cur.fetchone()
        realized = float(r["r"] if r and r["r"] is not None else 0.0)
        # Date in YYYY-MM-DD based on UTC
        day = time.strftime("%Y-%m-%d", time.gmtime())
        return {"date": day, "realized_pnl": realized}
