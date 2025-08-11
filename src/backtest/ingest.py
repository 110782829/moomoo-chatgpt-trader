"""
Data ingestion utilities for backtesting.

This module provides functions to load historical market data.
"""

from typing import Optional, List
import pandas as pd


def load_csv(filepath: str, parse_dates: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Load historical price data from a CSV file into a pandas DataFrame.

    :param filepath: Path to the CSV file.
    :param parse_dates: List of column names to parse as datetimes.
    :return: DataFrame with the loaded data.
    """
    return pd.read_csv(filepath, parse_dates=parse_dates)


def load_from_moomoo(client, symbol: str, start: str, end: str, interval: str = "1m") -> pd.DataFrame:
    """
    Load historical price data from the Moomoo/Futu API.

    :param client: Moomoo client instance.
    :param symbol: Stock ticker symbol.
    :param start: Start date in ISO format (YYYY-MM-DD).
    :param end: End date in ISO format (YYYY-MM-DD).
    :param interval: Timeframe for candles (e.g. "1m", "5m", "1d").
    :return: DataFrame with the loaded data.
    """
    raise NotImplementedError("Historical data loading via Moomoo API is not yet implemented.")
