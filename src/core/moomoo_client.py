"""
Wrapper client for the moomoo/Futu OpenAPI for stock trading.

This module provides high-level methods for logging in, retrieving account info,
and placing orders. It interacts with the OpenD session and Futu API via our wrapper.
"""

from typing import List, Optional, Dict, Any
import os
import pandas as pd

from core.futu_client import (
    FUTU_AVAILABLE,
    TradeContext,
    OpenQuoteContext,
    TrdEnv,
    TrdSide,
    OrderType,
    SubType,
    RET_OK,
)


# ---------------- utilities ---------------- #

def _df_to_records(df) -> List[Dict[str, Any]]:
    """Convert a Futu DataFrame (or list) into a list[dict]."""
    try:
        import pandas as _pd
        if isinstance(df, _pd.DataFrame):
            return df.to_dict(orient="records")
    except Exception:
        pass
    return df if isinstance(df, list) else []


# ---------------- client ---------------- #

class MoomooClient:
    # safety rails (configurable via env)
    MAX_QTY = float(os.getenv("MAX_QTY", "1000"))
    SIM_ONLY = os.getenv("SIM_ONLY", "1") == "1"

    def __init__(self, host: str, port: int) -> None:
        """
        Initialize the MoomooClient with the host and port of the OpenD gateway.

        Args:
            host (str): Hostname or IP address of the OpenD gateway.
            port (int): Port number of the OpenD gateway.
        """
        self.host = host
        self.port = port
        self.connected: bool = False
        self.account_id: int | None = None

        # trading/quote contexts
        self.trading_ctx = None
        self.quote_ctx = None  # type: ignore

        if not FUTU_AVAILABLE:
            raise RuntimeError(
                "futu-api not available. Install on Python 3.10/3.11 via `pip install futu-api`."
            )
        self.env = TrdEnv.SIMULATE

    def connect(self) -> None:
        """
        Connect to the OpenD gateway and initialize the trading and quote contexts.
        """
        if self.connected:
            return
        if TradeContext is None:
            raise RuntimeError("Trade context class not found in futu (USTrade/SecTrade).")

        # Trade context
        self.trading_ctx = TradeContext(host=self.host, port=self.port)

        # Quote context (optional; best-effort)
        try:
            self.quote_ctx = OpenQuoteContext(host=self.host, port=self.port)
        except Exception:
            self.quote_ctx = None

        self.connected = True

    def disconnect(self) -> None:
        """
        Close contexts if open.
        """
        try:
            if self.trading_ctx is not None:
                self.trading_ctx.close()
        finally:
            self.trading_ctx = None

        try:
            if self.quote_ctx is not None:
                self.quote_ctx.close()
        finally:
            self.quote_ctx = None

        self.connected = False

    # -------- accounts -------- #

    def list_accounts(self) -> List[str]:
        if not self.connected:
            raise RuntimeError("Not connected to OpenD")

        tried = [
            {"trd_env": self.env},
            {"env": self.env},
            {},
        ]
        last_err = None
        for kwargs in tried:
            try:
                ret, df = self.trading_ctx.get_acc_list(**kwargs)  # type: ignore[arg-type]
                if ret != RET_OK:
                    raise RuntimeError(f"get_acc_list failed: {df}")
                # Extract account IDs
                recs = _df_to_records(df)
                ids: List[str] = []
                for r in recs:
                    acc = r.get("acc_id") or r.get("accCode") or r.get("account_id")
                    if acc is not None:
                        ids.append(str(acc))
                # fallback if schema is unexpected
                if not ids:
                    for r in recs:
                        for v in r.values():
                            if isinstance(v, (str, int)):
                                ids.append(str(v))
                                break
                return ids
            except TypeError as e:
                last_err = e
                continue
        raise RuntimeError(f"get_acc_list incompatible with this futu build: {last_err}")

    def set_account(self, account_id: str, trd_env) -> None:
        """
        Set the active account and trading environment.
        trd_env should be TrdEnv.SIMULATE or TrdEnv.REAL.
        """
        if not self.connected:
            raise RuntimeError("Not connected to OpenD")
        try:
            self.account_id = int(account_id)
        except ValueError:
            raise RuntimeError(f"Invalid account_id: {account_id}")
        self.env = trd_env

    # -------- read data -------- #

    def get_positions(self) -> List[Dict[str, Any]]:
        if not self.connected:
            raise RuntimeError("Not connected")
        if not self.account_id:
            raise RuntimeError("No account selected")

        tried = [
            {"trd_env": self.env, "acc_id": self.account_id},
            {"env": self.env, "acc_id": self.account_id},
            {"acc_id": self.account_id},
            {},
        ]
        last_err = None
        for kwargs in tried:
            try:
                ret, df = self.trading_ctx.position_list_query(**kwargs)  # type: ignore[arg-type]
                if ret != RET_OK:
                    raise RuntimeError(f"position_list_query failed: {df}")
                return _df_to_records(df)
            except TypeError as e:
                last_err = e
                continue
        raise RuntimeError(f"position_list_query incompatible with this futu build: {last_err}")

    def get_orders(self) -> List[Dict[str, Any]]:
        if not self.connected:
            raise RuntimeError("Not connected")
        if not self.account_id:
            raise RuntimeError("No account selected")

        tried = [
            {"trd_env": self.env, "acc_id": self.account_id},
            {"env": self.env, "acc_id": self.account_id},
            {"acc_id": self.account_id},
            {},
        ]
        last_err = None
        for kwargs in tried:
            try:
                ret, df = self.trading_ctx.order_list_query(**kwargs)  # type: ignore[arg-type]
                if ret != RET_OK:
                    raise RuntimeError(f"order_list_query failed: {df}")
                return _df_to_records(df)
            except TypeError as e:
                last_err = e
                continue
        raise RuntimeError(f"order_list_query incompatible with this futu build: {last_err}")

    def get_order(self, order_id: str | int) -> Dict[str, Any]:
        if not self.connected:
            raise RuntimeError("Not connected")
        if not self.account_id:
            raise RuntimeError("No account selected")

        tried = [
            {"trd_env": self.env, "acc_id": self.account_id, "order_id": int(order_id)},
            {"env": self.env, "acc_id": self.account_id, "order_id": int(order_id)},
            {"order_id": int(order_id)},
        ]
        last_err = None
        for kwargs in tried:
            try:
                ret, df = self.trading_ctx.order_list_query(**kwargs)  # type: ignore[arg-type]
                if ret != RET_OK:
                    raise RuntimeError(f"order_list_query failed: {df}")
                recs = _df_to_records(df)
                return recs[0] if recs else {}
            except TypeError as e:
                last_err = e
                continue
        raise RuntimeError(f"order_list_query incompatible with this futu build: {last_err}")

    # -------- NEW: fills (deals) -------- #

    def get_deals(self) -> List[Dict[str, Any]]:
        """
        Return recent deals/fills for the active account.
        """
        if not self.connected:
            raise RuntimeError("Not connected")
        if not self.account_id:
            raise RuntimeError("No account selected")

        tried = [
            {"trd_env": self.env, "acc_id": self.account_id},
            {"env": self.env, "acc_id": self.account_id},
            {"acc_id": self.account_id},
            {},
        ]
        last_err = None
        for kwargs in tried:
            try:
                # Some builds expose 'deal_list_query'
                fn = getattr(self.trading_ctx, "deal_list_query", None)
                if not callable(fn):
                    raise RuntimeError("deal_list_query not available in this futu build")
                ret, df = fn(**kwargs)  # type: ignore[arg-type]
                if ret != RET_OK:
                    raise RuntimeError(f"deal_list_query failed: {df}")
                return _df_to_records(df)
            except TypeError as e:
                last_err = e
                continue
        raise RuntimeError(f"deal_list_query incompatible with this futu build: {last_err}")

    # -------- trade ops -------- #

    def place_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        order_type: str = "MARKET",
        price: Optional[float] = None,
    ) -> Dict[str, Any]:
        if not self.connected:
            raise RuntimeError("Not connected")
        if not self.account_id:
            raise RuntimeError("No account selected")

        # safety rails
        if self.SIM_ONLY and self.env != TrdEnv.SIMULATE:
            raise RuntimeError("Real trading disabled by server config (SIM_ONLY=1)")
        if qty > self.MAX_QTY:
            raise RuntimeError(f"Quantity {qty} exceeds server limit MAX_QTY={self.MAX_QTY}")

        symbol = symbol.strip()
        code = symbol if "." in symbol else f"US.{symbol.upper()}"

        side_enum = TrdSide.BUY if side.upper() == "BUY" else TrdSide.SELL

        ot = order_type.upper()
        if ot == "MARKET":
            order_type_enum = OrderType.MARKET
            if price is None:
                price = 0  # many builds ignore price for market
        elif ot == "LIMIT":
            if price is None:
                raise RuntimeError("price is required for LIMIT orders")
            # many builds treat NORMAL as 'limit'
            order_type_enum = OrderType.NORMAL
        else:
            order_type_enum = OrderType.NORMAL

        tried = [
            dict(code=code, price=price, qty=qty, trd_side=side_enum,
                 order_type=order_type_enum, trd_env=self.env, acc_id=self.account_id),
            dict(code=code, price=price, qty=qty, trd_side=side_enum,
                 order_type=order_type_enum, env=self.env, acc_id=self.account_id),
            dict(code=code, price=price, qty=qty, trd_side=side_enum,
                 order_type=order_type_enum),
        ]
        last_err = None
        for kwargs in tried:
            try:
                ret, df = self.trading_ctx.place_order(**kwargs)  # type: ignore[arg-type]
                if ret != RET_OK:
                    raise RuntimeError(f"place_order failed: {df}")
                return {"status": "ok", "result": _df_to_records(df)}
            except TypeError as e:
                last_err = e
                continue
        raise RuntimeError(f"place_order incompatible with this futu build: {last_err}")

    def cancel_order(self, order_id: str | int) -> Dict[str, Any]:
        if not self.connected:
            raise RuntimeError("Not connected")
        if not self.account_id:
            raise RuntimeError("No account selected")

        # Prefer native cancel_order if present (some builds)
        fn = getattr(self.trading_ctx, "cancel_order", None)
        if callable(fn):
            tried = [
                {"order_id": int(order_id), "trd_env": self.env, "acc_id": self.account_id},
                {"order_id": int(order_id), "env": self.env, "acc_id": self.account_id},
                {"order_id": int(order_id)},
            ]
            last_err = None
            for kwargs in tried:
                try:
                    ret, data = fn(**kwargs)  # type: ignore[misc]
                    if ret != RET_OK:
                        raise RuntimeError(f"cancel_order failed: {data}")
                    return {"status": "ok", "result": _df_to_records(data)}
                except TypeError as e:
                    last_err = e
                    continue
            # if native cancel didn't work, fall through to modify_order

        # ---- Fallback: modify_order(CANCEL) with required qty/price ----
        try:
            try:
                from futu import ModifyOrderOp  # type: ignore
            except Exception:
                from futu.common.constant import ModifyOrderOp  # type: ignore
        except Exception as e:
            raise RuntimeError(f"modify_order not available: {e}")

        op = getattr(ModifyOrderOp, "CANCEL", "CANCEL")

        # Get current order to provide qty/price if the API insists
        cur = {}
        try:
            cur = self.get_order(order_id)
        except Exception:
            pass
        qty = float(cur.get("qty", 0) or 0)
        price = float(cur.get("price", 0) or 0)

        attempts = [
            {"modify_order_op": op, "order_id": int(order_id), "qty": qty, "price": price,
             "trd_env": self.env, "acc_id": self.account_id},
            {"op": op, "order_id": int(order_id), "qty": qty, "price": price,
             "trd_env": self.env, "acc_id": self.account_id},
            {"op": op, "order_id": int(order_id), "qty": qty, "price": price,
             "env": self.env, "acc_id": self.account_id},
            ("positional", (op, int(order_id), qty, price), {"trd_env": self.env, "acc_id": self.account_id}),
            ("positional", (op, int(order_id), qty, price), {}),
        ]

        last_err = None
        for entry in attempts:
            try:
                if isinstance(entry, dict):
                    ret, data = self.trading_ctx.modify_order(**entry)  # type: ignore[arg-type]
                else:
                    _, args, kwargs = entry
                    ret, data = self.trading_ctx.modify_order(*args, **kwargs)  # type: ignore[arg-type]
                if ret != RET_OK:
                    raise RuntimeError(f"modify_order cancel failed: {data}")
                return {"status": "ok", "result": _df_to_records(data)}
            except TypeError as e:
                last_err = e
                continue

        raise RuntimeError(f"modify_order CANCEL incompatible with this futu build: {last_err}")

    # -------- quotes -------- #

    def subscribe_quotes(self, symbols: List[str]) -> Dict[str, Any]:
        if not self.connected:
            raise RuntimeError("Not connected")
        if not self.quote_ctx:
            raise RuntimeError("Quote context not available")

        codes = [s if "." in s else f"US.{s.upper()}" for s in symbols]
        from core.futu_client import SubType

        tried = [
            {"codes": codes, "subtype_list": [SubType.QUOTE], "is_first_push": True},
            {"code_list": codes, "subtype_list": [SubType.QUOTE], "is_first_push": True},
        ]
        last_err = None
        for kwargs in tried:
            try:
                ret, data = self.quote_ctx.subscribe(**kwargs)  # type: ignore[arg-type]
                if ret != RET_OK:
                    raise RuntimeError(f"subscribe failed: {data}")
                return {"status": "ok", "subscribed": codes}
            except TypeError as e:
                last_err = e
                continue
        raise RuntimeError(f"subscribe incompatible with this futu build: {last_err}")

    def get_quote_latest(self, symbol: str) -> Dict[str, Any]:
        if not self.connected:
            raise RuntimeError("Not connected")
        if not self.quote_ctx:
            raise RuntimeError("Quote context not available")

        code = symbol if "." in symbol else f"US.{symbol.upper()}"

        tried = [
            {"codes": [code]},
            {"code_list": [code]},
        ]
        last_err = None
        for kwargs in tried:
            try:
                ret, df = self.quote_ctx.get_stock_quote(**kwargs)  # type: ignore[arg-type]
                if ret != RET_OK:
                    msg = str(df)
                    if "No right to get the quote" in msg:
                        raise RuntimeError(
                            "Your account lacks US quote entitlements. Orders still work; "
                            "enable US quotes in Moomoo to fetch live prices."
                        )
                    raise RuntimeError(f"get_stock_quote failed: {df}")
                recs = _df_to_records(df)
                return recs[0] if recs else {}
            except TypeError as e:
                last_err = e
                continue
        raise RuntimeError(f"get_stock_quote incompatible with this futu build: {last_err}")
