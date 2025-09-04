from __future__ import annotations

import time
import uuid
import sqlite3
from typing import Callable, Dict, List, Optional, Any, Iterable, Union

from .base import ExecutionService, ExecutionContext
from .types import OrderSpec, PlacedOrder, FillRecord, OrderStatus, OrderType, OrderSide, TimeInForce


def _utc_ts() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class MoomooExecutionService(ExecutionService):
    """
    Execution driver that sends orders to Moomoo via a provided client accessor,
    and mirrors orders/fills into the same SQLite schema used by SimBroker.

    - MARKET/LIMIT orders are submitted to broker immediately.
    - STOP orders are handled as software stops: they are recorded locally and
      try_fill_resting() will submit a MARKET order when price crosses.
    - list_orders/fills reflect the local mirror; fill reconciliation can be
      achieved via a separate /sync/deals endpoint if desired.
    """

    def __init__(self, conn: sqlite3.Connection, client_accessor: Callable[[], object]):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self._client_accessor = client_accessor

    # ---- helpers to mirror orders/fills ----
    def _insert_order(self, row: Dict[str, Any]) -> None:
        self.conn.execute(
            """
            INSERT INTO orders (
                order_id, broker_order_id, created_at, updated_at, status, account_id,
                symbol, side, order_type, limit_price, tif,
                requested_qty, filled_qty, avg_fill_price, decision_id, reject_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["order_id"], row.get("broker_order_id"), row["created_at"], row["updated_at"], row["status"], row.get("account_id"),
                row["symbol"], row["side"], row["order_type"], row.get("limit_price"), row["tif"],
                row["requested_qty"], row["filled_qty"], row.get("avg_fill_price"), row.get("decision_id"), row.get("reject_reason"),
            ),
        )
        self.conn.commit()

    def _row_to_order(self, r) -> PlacedOrder:
        return PlacedOrder(
            order_id=r["order_id"], status=OrderStatus(r["status"]), symbol=r["symbol"], side=OrderSide(r["side"]),
            order_type=OrderType(r["order_type"]), limit_price=r["limit_price"], requested_qty=r["requested_qty"],
            filled_qty=r["filled_qty"], avg_fill_price=r["avg_fill_price"], tif=TimeInForce(r["tif"]),
            decision_id=r["decision_id"], created_at=r["created_at"], updated_at=r["updated_at"], reject_reason=r["reject_reason"],
        )

    # ---- interface ----
    def place_order(self, spec: OrderSpec, ctx: ExecutionContext) -> PlacedOrder:
        ts = _utc_ts()
        order_id = uuid.uuid4().hex
        status = OrderStatus.pending.value
        # Mirror locally first (so UI reflects intent)
        row = {
            "order_id": order_id,
            "created_at": ts,
            "updated_at": ts,
            "status": status,
            "account_id": ctx.account_id,
            "symbol": spec.symbol,
            "side": spec.side.value,
            "order_type": spec.order_type.value,
            "limit_price": spec.limit_price,
            "tif": spec.tif.value,
            "requested_qty": 0,  # will compute below
            "filled_qty": 0,
            "avg_fill_price": None,
            "decision_id": spec.decision_id,
            "reject_reason": None,
        }

        # Determine qty per sizing
        last = (ctx.last_prices or {}).get(spec.symbol) or 0.0
        if spec.size_type == "shares":
            qty = int(spec.size_value)
        elif spec.size_type == "notional":
            qty = int(float(spec.size_value) // float(last or 1.0))
        else:  # risk_bps
            notional = float(ctx.equity) * (float(spec.size_value) / 10000.0)
            qty = int(notional // float(last or 1.0))
        if qty < 1:
            row["status"] = OrderStatus.rejected.value
            row["reject_reason"] = "sizing_zero_qty"
            self._insert_order(row)
            return self._row_to_order(self.conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone())
        row["requested_qty"] = qty

        # Submit to broker for MARKET/LIMIT; STOP stays local until fired
        try:
            client = self._client_accessor()
        except Exception:
            client = None

        if spec.order_type in (OrderType.market, OrderType.limit) and client is not None:
            try:
                res = client.place_order(symbol=spec.symbol, qty=qty, side=("BUY" if spec.side==OrderSide.buy else "SELL"),
                                   order_type=("MARKET" if spec.order_type==OrderType.market else "LIMIT"),
                                   price=(spec.limit_price if spec.order_type==OrderType.limit else None))
                row["status"] = OrderStatus.open.value
                try:
                    recs = (res or {}).get("result") or []
                    if isinstance(recs, list) and recs:
                        boid = recs[0].get("order_id") or recs[0].get("orderId") or recs[0].get("orderID")
                        if boid is not None:
                            row["broker_order_id"] = str(boid)
                except Exception:
                    pass
            except Exception as e:
                row["status"] = OrderStatus.rejected.value
                row["reject_reason"] = str(e)
        elif spec.order_type == OrderType.stop:
            row["status"] = OrderStatus.open.value
        else:
            row["status"] = OrderStatus.rejected.value
            row["reject_reason"] = "no_client"

        self._insert_order(row)
        cur = self.conn.execute("SELECT * FROM orders WHERE order_id=?", (order_id,)).fetchone()
        return self._row_to_order(cur)

    def cancel_order(self, order_id: str) -> bool:
        # Local cancel + try broker cancel when broker_order_id present
        ts = _utc_ts()
        cur = self.conn.execute("SELECT status, broker_order_id FROM orders WHERE order_id=?", (order_id,)).fetchone()
        if not cur:
            return False
        if cur["status"] in (OrderStatus.filled.value, OrderStatus.canceled.value, OrderStatus.rejected.value):
            return False
        try:
            boid = cur["broker_order_id"]
            if boid:
                client = self._client_accessor()
                if client is not None:
                    try:
                        client.cancel_order(int(boid))
                    except Exception:
                        pass
        except Exception:
            pass
        self.conn.execute("UPDATE orders SET status=?, updated_at=? WHERE order_id=?",
                          (OrderStatus.canceled.value, ts, order_id))
        self.conn.commit()
        return True

    def try_fill_resting(self, last_prices: Dict[str, float]) -> None:
        # Software STOP handler: convert to market order when triggered; mark as filled locally
        cur = self.conn.execute(
            "SELECT * FROM orders WHERE status IN (?, ?) AND order_type IN (?, ?)",
            (OrderStatus.open.value, OrderStatus.pending.value, OrderType.limit.value, OrderType.stop.value))
        rows = cur.fetchall()
        for r in rows:
            sym = r["symbol"]
            lp = float((last_prices or {}).get(sym) or 0.0)
            if lp <= 0:
                # Fallback to live quote for faster triggers
                try:
                    client = self._client_accessor()
                    if client is not None:
                        q = client.get_quote_latest(sym) or {}
                        lp = float(q.get("last_price") or q.get("last") or q.get("price") or 0.0)
                except Exception:
                    lp = 0.0
            if lp <= 0:
                continue
            if r["order_type"] == OrderType.stop.value:
                trig = r["limit_price"]
                if trig is None:
                    continue
                if r["side"] in (OrderSide.buy.value, OrderSide.buy_to_cover.value):
                    fire = lp >= float(trig)
                else:
                    fire = lp <= float(trig)
                if fire:
                    try:
                        client = self._client_accessor()
                        if client is not None:
                            client.place_order(symbol=sym, qty=int(r["requested_qty"]), side=("BUY" if r["side"]==OrderSide.buy.value else "SELL"), order_type="MARKET")
                    except Exception:
                        pass
                    # mirror fill locally
                    fill_id = uuid.uuid4().hex
                    ts = _utc_ts()
                    self.conn.execute("INSERT INTO fills (fill_id, order_id, ts, symbol, qty, price) VALUES (?, ?, ?, ?, ?, ?)",
                                      (fill_id, r["order_id"], ts, sym, int(r["requested_qty"]), float(lp)))
                    self.conn.execute("UPDATE orders SET status=?, filled_qty=?, avg_fill_price=?, updated_at=? WHERE order_id=?",
                                      (OrderStatus.filled.value, int(r["requested_qty"]), float(lp), ts, r["order_id"]))
                    self.conn.commit()

    def list_orders(self, *, symbol: Optional[str] = None,
                    status: Optional[Union[str, Iterable[str]]] = None,
                    limit: int = 200) -> List[PlacedOrder]:
        q = "SELECT * FROM orders"
        clauses, params = [], []
        if symbol:
            clauses.append("symbol = ?")
            params.append(symbol)
        if status:
            if isinstance(status, (list, tuple, set)):
                placeholders = ",".join(["?"] * len(status))
                clauses.append(f"status IN ({placeholders})")
                params.extend(list(status))
            else:
                clauses.append("status = ?")
                params.append(status)
        if clauses:
            q += " WHERE " + " AND ".join(clauses)
        q += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        cur = self.conn.execute(q, tuple(params))
        return [self._row_to_order(r) for r in cur.fetchall()]

    def list_fills(self, *, symbol: Optional[str] = None, limit: int = 500) -> List[FillRecord]:
        q = "SELECT * FROM fills"
        params = []
        if symbol:
            q += " WHERE symbol = ?"; params.append(symbol)
        q += " ORDER BY ts DESC LIMIT ?"; params.append(limit)
        cur = self.conn.execute(q, tuple(params))
        out: List[FillRecord] = []
        for r in cur.fetchall():
            out.append(FillRecord(fill_id=r["fill_id"], order_id=r["order_id"], ts=r["ts"], symbol=r["symbol"], qty=r["qty"], price=r["price"]))
        return out

    def sync_deals(self, recs: List[Dict[str, Any]]) -> int:
        """Insert fills and update orders.

        Raises ValueError if any required field is missing to avoid silently
        dropping broker fills.
        """
        inserted = 0
        for r in recs:
            oid = str(r.get("order_id") or r.get("orderId") or "")
            code = str(r.get("code") or r.get("stock_code") or "")
            qty = float(r.get("deal_qty") or r.get("qty") or r.get("fill_qty") or 0)
            price = float(r.get("deal_price") or r.get("price") or r.get("fill_price") or 0)
            ts = str(r.get("create_time") or r.get("time") or r.get("ts") or "")
            if not oid or not code or qty <= 0 or price <= 0 or not ts:
                raise ValueError(f"invalid deal record: {r}")
            cur = self.conn.execute(
                "SELECT 1 FROM fills WHERE order_id=? AND ts=?", (oid, ts)
            ).fetchone()
            if cur:
                continue
            fid = uuid.uuid4().hex
            self.conn.execute(
                "INSERT INTO fills (fill_id, order_id, ts, symbol, qty, price) VALUES (?, ?, ?, ?, ?, ?)",
                (fid, oid, ts, code, int(qty), float(price)),
            )
            o = self.conn.execute(
                "SELECT filled_qty, requested_qty, avg_fill_price FROM orders WHERE order_id=?",
                (oid,),
            ).fetchone()
            if o:
                prev_qty = int(o["filled_qty"] or 0)
                prev_avg = float(o["avg_fill_price"] or 0.0)
                new_qty = prev_qty + int(qty)
                new_avg = (
                    (prev_avg * prev_qty + float(price) * int(qty)) / new_qty
                    if new_qty > 0
                    else 0.0
                )
                status = (
                    OrderStatus.filled.value
                    if new_qty >= int(o["requested_qty"] or 0)
                    else OrderStatus.open.value
                )
                self.conn.execute(
                    "UPDATE orders SET filled_qty=?, avg_fill_price=?, status=?, updated_at=? WHERE order_id=?",
                    (new_qty, new_avg, status, _utc_ts(), oid),
                )
            inserted += 1
        self.conn.commit()
        return inserted

    # Optional positions view for UI (best-effort via broker)
    def list_positions(self) -> List[Dict[str, Any]]:
        try:
            client = self._client_accessor()
        except Exception:
            client = None
        out: List[Dict[str, Any]] = []
        if client is None:
            return out
        try:
            poss = client.get_positions() or []
        except Exception:
            poss = []
        last_map: Dict[str, float] = {}
        for p in poss:
            code = p.get("code") or p.get("stock_code") or p.get("symbol")
            if not code:
                continue
            qty = float(p.get("qty") or p.get("qty_total") or p.get("qty_today") or 0.0)
            avg = float(p.get("cost_price") or p.get("avg_cost_price") or 0.0)
            if qty == 0:
                continue
            last = last_map.get(code)
            if last is None:
                try:
                    q = client.get_quote_latest(code) or {}
                    last = float(q.get("last_price") or q.get("last") or q.get("price") or 0.0)
                except Exception:
                    last = 0.0
                last_map[code] = last
            mv = (last if last else avg) * qty
            upl = None if not last else (last - avg) * qty
            out.append({
                "symbol": code, "qty": int(qty), "avg_cost": avg,
                "last": last or None,
                "mv": mv,
                "upl": upl,
                "rpl_today": 0.0,
            })
        return out
