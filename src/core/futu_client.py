"""
Moomoo/Futu OpenAPI client for stock trading (paper or live).
Provides methods to connect to the OpenD gateway, list accounts, place orders,
subscribe to quotes, and disconnect.
"""

from typing import List, Optional, Sequence, Dict, Any

try:
    from futu import (
        OpenQuoteContext,
        OpenTradeContext,
        TrdEnv,
        TrdSide,
        OrderType,
        SubType,
        RET_OK,
    )
except ImportError:
    # Dummy fallback types for type checking if futu is not installed.
    OpenQuoteContext = object  # type: ignore
    OpenTradeContext = object  # type: ignore
    TrdEnv = object  # type: ignore
    TrdSide = object  # type: ignore
    OrderType = object  # type: ignore
    SubType = object  # type: ignore
    RET_OK = 0

class MoomooClient:
    """Wrapper around the Futu OpenAPI for trading stocks via moomoo."""

    def __init__(self, host: str, port: int, env: Optional[str] = "SIMULATE") -> None:
        """Initialize the client.

        Args:
            host: Hostname or IP of the OpenD gateway.
            port: Port number of the OpenD gateway.
            env: Trading environment ("SIMULATE" or "REAL").
        """
        self.host = host
        self.port = port
        # Determine trading environment
        if isinstance(env, str):
            env_upper = env.upper()
            if env_upper == "REAL":
                self.env = TrdEnv.REAL
            else:
                self.env = TrdEnv.SIMULATE
        else:
            self.env = env or TrdEnv.SIMULATE

        self.quote_ctx: Optional[OpenQuoteContext] = None
        self.trade_ctx: Optional[OpenTradeContext] = None
        self.connected: bool = False
        self.account_id: Optional[int] = None

    def connect(self) -> None:
        """Connect to the OpenD gateway and initialize quote/trade contexts."""
        if self.connected:
            return
        try:
            self.quote_ctx = OpenQuoteContext(host=self.host, port=self.port)
            self.trade_ctx = OpenTradeContext(host=self.host, port=self.port)
        except Exception as exc:
            raise RuntimeError(f"Failed to connect to OpenD: {exc}") from exc
        self.connected = True

    def list_accounts(self) -> List[str]:
        """Retrieve list of available trading accounts.

        Returns:
            A list of account identifiers.
        """
        if not self.connected or self.trade_ctx is None:
            raise RuntimeError("Client is not connected")
        ret, accounts = self.trade_ctx.get_acc_list()
        if ret == RET_OK:
            # accounts is a DataFrame with 'acc_id' column
            acc_list = accounts["acc_id"].tolist()
            return [str(acc) for acc in acc_list]
        return []

    def set_account(self, account_id: str) -> None:
        """Set the default account id to use for trading.

        Args:
            account_id: The account identifier.
        """
        self.account_id = int(account_id)

    def place_order(
        self,
        ticker: str,
        qty: int,
        order_type: str = "MARKET",
        price: Optional[float] = None,
        side: str = "BUY",
    ) -> Dict[str, Any]:
        """Place an order via the trading context.

        Args:
            ticker: Stock ticker symbol.
            qty: Quantity to buy or sell.
            order_type: "MARKET" or "LIMIT".
            price: Limit price if order_type is "LIMIT".
            side: "BUY" or "SELL".

        Returns:
            Response dictionary with order details.
        """
        if not self.connected or self.trade_ctx is None:
            raise RuntimeError("Client is not connected")

        # Determine order type and side enums
        ot = OrderType.MARKET if order_type.upper() == "MARKET" else OrderType.NORMAL
        trd_side = TrdSide.BUY if side.upper() == "BUY" else TrdSide.SELL

        # Use selected account or first available
        acc_id = self.account_id or int(self.list_accounts()[0])

        ret, data = self.trade_ctx.place_order(
            price=price or 0.0,
            qty=qty,
            code=ticker,
            trd_side=trd_side,
            order_type=ot,
            trd_env=self.env,
            acc_id=acc_id,
        )
        if ret == RET_OK:
            # data is DataFrame; return first row as dict
            if hasattr(data, "iloc"):
                return data.iloc[0].to_dict()
            return {}
        raise RuntimeError(f"Order placement failed: {data}")

    def subscribe_quotes(self, tickers: Sequence[str], sub_types: Optional[Sequence[SubType]] = None) -> None:
        """Subscribe to real-time quotes for given tickers.

        Args:
            tickers: Sequence of ticker symbols, e.g. ["AAPL"].
            sub_types: Sequence of subscription types (default: [SubType.QUOTE]).
        """
        if not self.connected or self.quote_ctx is None:
            raise RuntimeError("Client is not connected")
        if sub_types is None:
            sub_types = [SubType.QUOTE]
        ret, _ = self.quote_ctx.subscribe(list(tickers), list(sub_types), subscribe=True)
        if ret != RET_OK:
            raise RuntimeError("Failed to subscribe to quotes")

    def unsubscribe_quotes(self, tickers: Sequence[str], sub_types: Optional[Sequence[SubType]] = None) -> None:
        """Unsubscribe from quotes.

        Args:
            tickers: List of ticker symbols.
            sub_types: Subscription types.
        """
        if not self.connected or self.quote_ctx is None:
            return
        if sub_types is None:
            sub_types = [SubType.QUOTE]
        self.quote_ctx.unsubscribe(list(tickers), list(sub_types))

    def get_quote(self, ticker: str) -> Dict[str, Any]:
        """Retrieve latest quote for a ticker.

        Args:
            ticker: Stock ticker symbol.

        Returns:
            Dictionary with quote information.
        """
        if not self.connected or self.quote_ctx is None:
            raise RuntimeError("Client is not connected")
        ret, data = self.quote_ctx.get_market_snapshot([ticker])
        if ret == RET_OK and hasattr(data, "iloc"):
            return data.iloc[0].to_dict()
        raise RuntimeError("Failed to get quote")

    def disconnect(self) -> None:
        """Close all contexts and disconnect."""
        if self.quote_ctx is not None:
            self.quote_ctx.close()
            self.quote_ctx = None
        if self.trade_ctx is not None:
            self.trade_ctx.close()
            self.trade_ctx = None
        self.connected = False
