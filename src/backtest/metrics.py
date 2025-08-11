"""
Backtest metrics utilities.

Provides functions to compute key metrics like total return, average return, maximum drawdown, and Sharpe ratio.
"""

from typing import Sequence
import pandas as pd
import numpy as np


def calculate_returns(equity_curve: Sequence[float]) -> pd.Series:
    """
    Compute periodic returns from an equity curve.

    :param equity_curve: Sequence of portfolio values over time.
    :return: Series of percentage returns.
    """
    return pd.Series(equity_curve).pct_change().dropna()


def calculate_sharpe(returns: pd.Series, risk_free_rate: float = 0.0) -> float:
    """
    Compute annualized Sharpe ratio for a series of returns.

    :param returns: Series of periodic returns.
    :param risk_free_rate: Risk-free rate per period (e.g. per return interval).
    :return: Annualized Sharpe ratio.
    """
    if returns.empty:
        return 0.0
    # Annualize assuming returns are daily; adjust factor if using other intervals.
    excess = returns - (risk_free_rate)
    return np.sqrt(len(returns)) * excess.mean() / (excess.std() + 1e-9)


def calculate_max_drawdown(equity_curve: Sequence[float]) -> float:
    """
    Compute maximum drawdown from an equity curve.

    :param equity_curve: Sequence of portfolio values over time.
    :return: The maximum drawdown as a negative float (e.g., -0.2 for -20%).
    """
    curve = np.asarray(equity_curve)
    running_max = np.maximum.accumulate(curve)
    drawdowns = (curve - running_max) / running_max
    return float(drawdowns.min())
