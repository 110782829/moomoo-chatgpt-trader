from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class OrderSide(str, Enum):
    buy = "buy"
    sell = "sell"
    sell_short = "sell_short"
    buy_to_cover = "buy_to_cover"


class OrderType(str, Enum):
    market = "market"
    limit = "limit"


class TimeInForce(str, Enum):
    day = "day"
    gtc = "gtc"


class OrderStatus(str, Enum):
    pending = "pending"
    open = "open"
    filled = "filled"
    partially_filled = "partially_filled"
    canceled = "canceled"
    rejected = "rejected"


class OrderSpec(BaseModel):
    symbol: str
    side: OrderSide
    order_type: OrderType = OrderType.market
    limit_price: Optional[float] = None
    size_type: str = Field(..., description="shares | notional | risk_bps")
    size_value: float
    tif: TimeInForce = TimeInForce.day
    decision_id: Optional[int] = None


class PlacedOrder(BaseModel):
    order_id: str
    status: OrderStatus
    symbol: str
    side: OrderSide
    order_type: OrderType
    limit_price: Optional[float]
    requested_qty: int
    filled_qty: int
    avg_fill_price: Optional[float]
    tif: TimeInForce
    decision_id: Optional[int]
    created_at: str
    updated_at: str
    reject_reason: Optional[str] = None


class FillRecord(BaseModel):
    fill_id: str
    order_id: str
    symbol: str
    qty: int
    price: float
    ts: str
