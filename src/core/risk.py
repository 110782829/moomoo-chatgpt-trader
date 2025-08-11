"""
Risk management module for the trading bot.

This module defines a RiskManager class which enforces constraints such as
maximum position size, maximum daily loss, per-trade risk limits, and trading
windows. It can be extended to include more sophisticated risk controls.
"""

from datetime import datetime, time, date
from typing import Optional

class RiskManager:
    """
    Enforces trading risk parameters and constraints.
    """

    def __init__(
        self,
        max_daily_loss: float,
        max_position_percent: float,
        risk_per_trade: float,
        trading_start: time = time(9, 30),
        trading_end: time = time(16, 0),
    ) -> None:
        """
        Initialize the risk manager with various risk thresholds.

        Args:
            max_daily_loss (float): Maximum dollar loss allowed per day.
            max_position_percent (float): Maximum percent of total capital allowed in a single position.
            risk_per_trade (float): Fraction of capital to risk per trade (e.g., 0.01 for 1%).
            trading_start (time): Start time of allowed trading window.
            trading_end (time): End time of allowed trading window.
        """
        self.max_daily_loss = max_daily_loss
        self.max_position_percent = max_position_percent
        self.risk_per_trade = risk_per_trade
        self.trading_start = trading_start
        self.trading_end = trading_end
        self.daily_loss = 0.0
        self.last_reset_date: Optional[date] = None

    def reset_daily_loss(self) -> None:
        """
        Reset the tracked daily loss at the start of a new trading day.
        """
        self.daily_loss = 0.0
        self.last_reset_date = date.today()

    def update_daily_loss(self, pnl: float) -> None:
        """
        Update the running daily loss.

        Args:
            pnl (float): Profit or loss of a completed trade. Negative values increase loss.
        """
        self.daily_loss += -pnl  # subtract PnL to accumulate losses (negative PnL increases loss)

    def can_trade(self, current_time: Optional[datetime] = None) -> bool:
        """
        Determine whether trading is allowed at the current time and daily loss level.

        Args:
            current_time (Optional[datetime]): Current time, defaults to now.

        Returns:
            bool: True if trading is permitted, False otherwise.
        """
        now = current_time or datetime.now()
        # Reset daily loss at start of new day
        if self.last_reset_date != now.date():
            self.reset_daily_loss()
        # Check time window
        within_window = self.trading_start <= now.time() <= self.trading_end
        # Check daily loss
        within_loss = self.daily_loss < self.max_daily_loss
        return within_window and within_loss

    def max_position_size(self, total_capital: float) -> float:
        """
        Calculate the maximum position size allowed based on total capital.

        Args:
            total_capital (float): Total account capital.

        Returns:
            float: Maximum dollar amount allowed for a single position.
        """
        return total_capital * self.max_position_percent

    def allowed_risk_per_trade(self, total_capital: float) -> float:
        """
        Calculate the dollar risk allowed per trade.

        Args:
            total_capital (float): Total account capital.

        Returns:
            float: Dollar amount allowed to risk per trade.
        """
        return total_capital * self.risk_per_trade
