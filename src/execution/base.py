from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, List, Optional
from .types import OrderSpec, PlacedOrder, FillRecord


class ExecutionContext:
    def __init__(self, account_id: str, last_prices: Dict[str, float], equity: float, simulate: bool = True):
        self.account_id = account_id
        self.last_prices = last_prices
        self.equity = equity
        self.simulate = simulate


class ExecutionService(ABC):
    @abstractmethod
    def place_order(self, spec: OrderSpec, ctx: ExecutionContext) -> PlacedOrder: ...
    @abstractmethod
    def cancel_order(self, order_id: str) -> bool: ...
    @abstractmethod
    def try_fill_resting(self, last_prices: Dict[str, float]) -> None: ...
    @abstractmethod
    def list_orders(self, *, symbol: Optional[str] = None, status: Optional[str] = None,
                    limit: int = 200) -> List[PlacedOrder]: ...
    @abstractmethod
    def list_fills(self, *, symbol: Optional[str] = None, limit: int = 500) -> List[FillRecord]: ...
