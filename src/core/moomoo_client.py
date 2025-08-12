"""
Wrapper client for the moomoo/Futu OpenAPI for stock trading.

This module provides high-level methods for logging in, retrieving account info,
and placing orders. It should interact with the OpenD session and Futu API.

Note: Implementation details depend on the moomoo/futu OpenAPI Python SDK.
"""
from typing import List, Optional, Dict, Any
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


def _df_to_records(df) -> List[Dict[str, Any]]:
    try:
        import pandas as _pd
        if isinstance(df, _pd.DataFrame):
            return df.to_dict(orient="records")
    except Exception:
        pass
    return df if isinstance(df, list) else []

class MoomooClient:
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
        # Placeholder for the futu OpenAPI trading context
        self.trading_ctx = None
        if not FUTU_AVAILABLE:
            raise RuntimeError("futu-api not available. Install on Python 3.10/3.11 via `pip install futu-api`.")
        self.env = TrdEnv.SIMULATE
    def connect(self) -> None:
        """
        Connect to the OpenD gateway and initialize the trading context.

        Actual implementation will use the futu OpenAPI to create an OpenD session.
        """
        # TODO: Create trading context using futu API
        # For example: self.trading_ctx = OpenSecTradeContext(host=self.host, port=self.port)
        # may also need to login with API key or credentials.
        if self.connected:
            return
        if TradeContext is None:
            raise RuntimeError(
                "Trade context class not found in futu (USTrade/SecTrade)."
            )
        self.trading_ctx = TradeContext(host=self.host, port=self.port)
        self.connected = True

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
                # Extract account IDs from DataFrame or list
                recs = _df_to_records(df)
                ids: List[str] = []
                for r in recs:
                    # Futu builds vary; try common keys
                    acc = r.get("acc_id") or r.get("accCode") or r.get("account_id")
                    if acc is not None:
                        ids.append(str(acc))
                # If no obvious keys, fall back to any stringy values
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
        trd_env should be TrdEnv.SIMULATE or TrdEnv.REAL
        """
        if not self.connected:
            raise RuntimeError("Not connected to OpenD")
        try:
            self.account_id = int(account_id)  # <<-- cast to int here
        except ValueError:
            raise RuntimeError(f"Invalid account_id: {account_id}")
        self.env = trd_env
    
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
        
        symbol = symbol.strip()
        code = symbol if "." in symbol else f"US.{symbol.upper()}"

        side_enum = TrdSide.BUY if side.upper() == "BUY" else TrdSide.SELL
        ot = order_type.upper()
        if ot == "MARKET":
            order_type_enum = OrderType.MARKET
            if price is None:
                price = 0  # ignored by many builds for market orders
        elif ot == "LIMIT":
            if price is None:
                raise RuntimeError("price is required for LIMIT orders")
            # many builds treat NORMAL as limit
            order_type_enum = OrderType.NORMAL
        else:
            order_type_enum = OrderType.NORMAL

        tried = [
            dict(code=symbol, price=price, qty=qty, trd_side=side_enum,
                order_type=order_type_enum, trd_env=self.env, acc_id=self.account_id),
            dict(code=symbol, price=price, qty=qty, trd_side=side_enum,
                order_type=order_type_enum, env=self.env, acc_id=self.account_id),
            dict(code=symbol, price=price, qty=qty, trd_side=side_enum,
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

