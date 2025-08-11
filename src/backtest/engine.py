"""
Backtesting engine for evaluating trading strategies.
"""

from typing import Callable, List, Dict, Any, Iterable


class BacktestEngine:
    """
    Simple backtesting engine that iterates over historical price data and executes
    a trading strategy. This class should be extended to support more advanced
    backtesting features such as order execution simulation, commission models,
    and performance metrics.
    """

    def __init__(self, strategy_class: Callable[..., Any], data: Iterable[Dict[str, Any]], config: Dict[str, Any]):
        """
        Initialize the backtesting engine.

        Args:
            strategy_class: A callable that returns a strategy instance when provided with a config.
            data: An iterable of historical data points (e.g., bars or ticks).
            config: Configuration dictionary for the strategy.
        """
        self.strategy = strategy_class(config)
        self.data = data
        self.results: List[Dict[str, Any]] = []

    def run(self) -> List[Dict[str, Any]]:
        """
        Run the backtest over the provided data. Calls the strategy's on_bar method
        for each data point and collects results. This method is a stub and should
        be implemented with actual backtesting logic.

        Returns:
            A list of results or metrics captured during the backtest.

        Raises:
            NotImplementedError: Indicates the run logic is not yet implemented.
        """
        # TODO: implement backtesting loop calling strategy.on_bar() and collecting results
        raise NotImplementedError("Backtest run not implemented yet.")
