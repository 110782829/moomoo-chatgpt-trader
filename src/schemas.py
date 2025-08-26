from pydantic import BaseModel
from typing import List, Optional

class ConnectRequest(BaseModel):
  host: Optional[str] = None
  port: Optional[int] = None
  client_id: Optional[int] = None

class SelectAccountRequest(BaseModel):
  account_id: str
  trd_env: str = "SIMULATE"

class PlaceOrderRequest(BaseModel):
  symbol: str
  qty: float
  side: str
  order_type: str = "MARKET"
  price: Optional[float] = None

class CancelOrderRequest(BaseModel):
  order_id: str

class SubscribeQuotesRequest(BaseModel):
  symbols: List[str]

class FlattenRequest(BaseModel):
  symbols: Optional[List[str]] = None

class StartMACrossoverRequest(BaseModel):
  symbol: str
  fast: int = 20
  slow: int = 50
  ktype: str = "K_1M"
  qty: float = 1
  size_mode: Optional[str] = "shares"
  dollar_size: Optional[float] = 0.0
  stop_loss_pct: Optional[float] = 0.0
  take_profit_pct: Optional[float] = 0.0
  interval_sec: int = 15
  allow_real: bool = False

class UpdateStrategyRequest(BaseModel):
  fast: Optional[int] = None
  slow: Optional[int] = None
  ktype: Optional[str] = None
  qty: Optional[float] = None
  size_mode: Optional[str] = None
  dollar_size: Optional[float] = None
  stop_loss_pct: Optional[float] = None
  take_profit_pct: Optional[float] = None
  allow_real: Optional[bool] = None
  interval_sec: Optional[int] = None
  active: Optional[bool] = None

class BacktestMARequest(BaseModel):
  symbol: str
  fast: int = 20
  slow: int = 50
  ktype: str = "K_1M"
  qty: float = 1.0
  size_mode: Optional[str] = "shares"
  dollar_size: Optional[float] = 0.0
  stop_loss_pct: Optional[float] = 0.0
  take_profit_pct: Optional[float] = 0.0
  commission_per_share: Optional[float] = 0.0
  slippage_bps: Optional[float] = 0.0

class BacktestMAGridRequest(BaseModel):
  symbol: str
  ktype: str = "K_1M"
  fast_min: int = 5
  fast_max: int = 30
  fast_step: int = 5
  slow_min: int = 40
  slow_max: int = 200
  slow_step: int = 10
  qty: float = 1.0
  size_mode: Optional[str] = "shares"
  dollar_size: Optional[float] = 0.0
  stop_loss_pct: Optional[float] = 0.0
  take_profit_pct: Optional[float] = 0.0
  commission_per_share: Optional[float] = 0.0
  slippage_bps: Optional[float] = 0.0
  top_n: int = 10

class RiskConfig(BaseModel):
  enabled: Optional[bool] = None
  max_usd_per_trade: Optional[float] = None
  max_open_positions: Optional[int] = None
  max_daily_loss_usd: Optional[float] = None
  symbol_whitelist: Optional[List[str]] = None
  trading_hours_pt: Optional[dict] = None
  flatten_before_close_min: Optional[int] = None

class BotModeRequest(BaseModel):
  mode: str

class FlattenAllRequest(BaseModel):
  symbols: Optional[List[str]] = None

