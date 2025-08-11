"""
Moving Average Crossover strategy implementation.

This strategy calculates a fast and a slow simple moving average (SMA) over the
incoming price data. When the fast SMA crosses above the slow SMA, it
generates a buy signal; when the fast SMA crosses below the slow SMA, it
signals a sell. Orders are returned as simple dictionaries that can later be
translated into broker-specific order requests.
"""

from typing import Any, List, Dict

from .base import StrategyBase

class MACrossoverStrategy(StrategyBase):
    """
    Simple moving average crossover strategy.
    """

    def __init__(self, config: Any) -> None:
        super().__init__(config)
        # Store historical prices for SMA calculations
        self.prices: List[float] = []
        # Track whether we are currently in a long position
        self.in_position: bool = False

    def on_bar(self, price: float) -> None:
        """
        Process the latest price data point.

        Args:
            price (float): Latest closing price.
        """
        self.prices.append(price)
        # Limit stored prices to the maximum window needed
        max_window = max(self.config.get("fast_window", 5), self.config.get("slow_window", 20))
        if len(self.prices) > max_window:
            self.prices.pop(0)

    def _sma(self, window: int) -> float:
        """
        Calculate the simple moving average for the given window.

        Args:
            window (int): Number of periods for the SMA.

        Returns:
            float: Calculated SMA value, or 0.0 if insufficient data.
        """
        if len(self.prices) < window:
            return 0.0
        return sum(self.prices[-window:]) / window

    def generate_orders(self) -> List[Dict[str, Any]]:
        """
        Generate buy or sell orders based on SMA crossover signals.

        Returns:
            List[Dict[str, Any]]: A list of order instructions.
        """
        orders: List[Dict[str, Any]] = []
        fast_window = self.config.get("fast_window", 5)
        slow_window = self.config.get("slow_window", 20)
        position_size = self.config.get("position_size", 1)

        fast_ma = self._sma(fast_window)
        slow_ma = self._sma(slow_window)

        # If insufficient data, do nothing
        if fast_ma == 0.0 or slow_ma == 0.0:
            return orders

        # Generate signals
        if not self.in_position and fast_ma > slow_ma:
            # Buy signal
            orders.append({
                "action": "BUY",
                "size": position_size,
                "reason": "Fast MA crossed above slow MA"
            })
            self.in_position = True
        elif self.in_position and fast_ma < slow_ma:
            # Sell signal
            orders.append({
                "action": "SELL",
                "size": position_size,
                "reason": "Fast MA crossed below slow MA"
            })
            self.in_position = False

        return orders
