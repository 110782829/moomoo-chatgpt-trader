"""
Data models for storing trading configurations, orders, fills, positions, and logs.

These models use SQLModel for ORM capabilities, enabling persistence to SQLite or
other supported databases. They represent the core entities used by the trading
bot for recording configurations and runtime state.
"""

from typing import Optional
from datetime import datetime
from sqlmodel import Field, SQLModel

class TickerConfig(SQLModel, table=True):
    """
    Configuration for an individual ticker or instrument.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True, description="Ticker symbol")
    max_position: int = Field(description="Maximum allowable position size for this ticker")

class StrategyConfig(SQLModel, table=True):
    """
    Configuration parameters for a trading strategy.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True, description="Name of the strategy")
    fast_window: int = Field(description="Fast moving average window")
    slow_window: int = Field(description="Slow moving average window")
    risk_per_trade: float = Field(description="Fraction of capital to risk per trade (e.g., 0.01 for 1%)")

class OrderRecord(SQLModel, table=True):
    """
    Record of an order placed by the bot.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Time the order was created")
    symbol: str = Field(index=True, description="Ticker symbol")
    side: str = Field(description="BUY or SELL")
    quantity: int = Field(description="Quantity of shares")
    order_type: str = Field(description="Type of order, e.g., MARKET or LIMIT")
    price: Optional[float] = Field(default=None, description="Limit price if applicable")
    status: str = Field(default="PENDING", description="Current order status")

class Fill(SQLModel, table=True):
    """
    Record of a fill (execution) for an order.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: int = Field(foreign_key="orderrecord.id", description="ID of the associated order")
    fill_timestamp: datetime = Field(default_factory=datetime.utcnow, description="Time of the fill")
    fill_price: float = Field(description="Execution price")
    fill_qty: int = Field(description="Quantity filled")

class Position(SQLModel, table=True):
    """
    Representation of an open position in a ticker.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    symbol: str = Field(index=True, description="Ticker symbol")
    quantity: int = Field(description="Net quantity held")
    avg_entry_price: float = Field(description="Average entry price of the position")

class RunLog(SQLModel, table=True):
    """
    Application runtime logs for audit and debugging.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Time of the log entry")
    level: str = Field(default="INFO", description="Log level (INFO, WARNING, ERROR)")
    message: str = Field(description="Log message text")
