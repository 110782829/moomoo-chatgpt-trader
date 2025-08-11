"""
Base classes and utilities for trading strategies.

All strategy implementations should inherit from `StrategyBase` and implement
its abstract methods. A strategy is responsible for processing market data and
producing trading signals.
"""

from abc import ABC, abstractmethod
from typing import Any, List

class StrategyBase(ABC):
    """
    Abstract base class for trading strategies.

    Args:
        config (Any): A configuration object or dictionary containing strategy parameters.
    """

    def __init__(self, config: Any) -> None:
        self.config = config

    @abstractmethod
    def on_bar(self, data: Any) -> None:
        """
        Process a new bar or tick of market data.

        Args:
            data (Any): The latest market data point (e.g., price, volume, etc.).
        """
        raise NotImplementedError

    @abstractmethod
    def generate_orders(self) -> List[Any]:
        """
        Generate trading orders based on internal state and signals.

        Returns:
            List[Any]: A list of order instructions.
        """
        raise NotImplementedError
