import sqlite3
import time
import uuid
from typing import Dict, List, Optional
from .base import ExecutionService, ExecutionContext
from .types import OrderSpec, PlacedOrder, FillRecord, OrderStatus, OrderType, OrderSide, TimeInForce


def _utc_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class SimBroker(ExecutionService):
    """
    Simple paper engine backed by SQLite.
    - Market orders: immediate fill at last price.
    - Limit orders: fill immediately only if price crosses; else remain OPEN until try_fill_resting().
    - Sizing:
        shares: size_value treated as desired share count
        notional: floor(size_value / last_price)
        risk_bps: floor((equity * (bps/10000)) / last_price)
    """
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row

    # --- Internals ---
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
                row["order_id"], row["created_at"], row["updated_at"], row["status"], row["account_id"],
                row["symbol"], row["side"], row["order_type"], row["limit_price"], row["tif"],
                row["requested_qty"], row["filled_qty"], row["avg_fill_price"], row["decision_id"], row["reject_reason"],
            ),
        )
        self.conn.commit()

    def _insert_fill(self, fill) -> None:
        self.conn.execute(
            """
            INSERT INTO fills (fill_id, order_id, ts, symbol, qty, price)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
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
        last = ctx.last_prices.get(spec.symbol)
        if last is None or last <= 0:
            return 0
        if spec.size_type == "shares":
            return max(0, int(spec.size_value))
        if spec.size_type == "notional":
            return max(0, int(spec.size_value // last))
        if spec.size_type == "risk_bps":
            notional = ctx.equity * (spec.size_value / 10000.0)
            return max(0, int(notional // last))
        return 0

    def _maybe_fill_now(self, order_row, last_price: Optional[float]) -> Optional[FillRecord]:
        if last_price is None:
            return None
        side = order_row["side"]
        if order_row["order_type"] == OrderType.market.value:
            qty = order_row["requested_qty"]
            price = float(last_price)
        else:  # limit
            lp = order_row["limit_price"]
            if lp is None:
                return None
            if side in (OrderSide.buy.value, OrderSide.buy_to_cover.value):
                if last_price <= lp:
                    qty = order_row["requested_qty"]
                    price = float(min(lp, last_price))
                else:
                    return None
            else:  # sell or sell_short
                if last_price >= lp:
                    qty = order_row["requested_qty"]
                    price = float(max(lp, last_price))
                else:
                    return None

        # Fill
        fill_id = uuid.uuid4().hex
        ts = _utc_ts()
        self._insert_fill({
            "fill_id": fill_id, "order_id": order_row["order_id"], "ts": ts,
            "symbol": order_row["symbol"], "qty": qty, "price": price
        })
        self.conn.execute(
            """
            UPDATE orders
            SET status = ?, filled_qty = ?, avg_fill_price = ?, updated_at = ?
            WHERE order_id = ?
            """,
            (OrderStatus.filled.value, qty, price, ts, order_row["order_id"]),
        )
        self.conn.commit()
        return FillRecord(fill_id=fill_id, order_id=order_row["order_id"], symbol=order_row["symbol"], qty=qty, price=price, ts=ts)

    # --- Interface impl ---
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

        # Guardrail: qty must be >=1 after sizing
        if requested_qty < 1:
            row["status"] = OrderStatus.rejected.value
            row["reject_reason"] = "sizing_zero_qty"
            self._insert_order(row)
            return self._row_to_order(row)

        # Insert first, then attempt immediate fill
        row["status"] = OrderStatus.open.value if spec.order_type == OrderType.limit else OrderStatus.pending.value
        self._insert_order(row)

        fill = self._maybe_fill_now(row, last)
        if not fill:
            # If not filled immediately, ensure status is OPEN
            self.conn.execute(
                "UPDATE orders SET status = ?, updated_at = ? WHERE order_id = ?",
                (OrderStatus.open.value, _utc_ts(), order_id),
            )
            self.conn.commit()

        # Read-back
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
            out.append(FillRecord(
                fill_id=r["fill_id"], order_id=r["order_id"], ts=r["ts"],
                symbol=r["symbol"], qty=r["qty"], price=r["price"]
            ))
        return out
