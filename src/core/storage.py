"""
Storage utilities for the trading bot.

This module encapsulates database interactions using SQLModel. It provides a
simple interface to create the database engine and obtain sessions for
executing queries and persisting models.
"""

from sqlmodel import SQLModel, create_engine, Session
from typing import Generator

class Storage:
    """
    Storage handles database connections and session management.
    """

    def __init__(self, db_url: str = "sqlite:///data/trading.db") -> None:
        """
        Initialize the storage backend.

        Args:
            db_url (str): Database URL. Defaults to a SQLite file in the data directory.
        """
        # Create the engine. The `echo` flag can be toggled for SQL debugging.
        self.engine = create_engine(db_url, echo=False)
        # Create all tables defined in models
        SQLModel.metadata.create_all(self.engine)

    def get_session(self) -> Generator[Session, None, None]:
        """
        Provide a context-managed session for database operations.

        Yields:
            Session: A SQLModel Session instance.
        """
        with Session(self.engine) as session:
            yield session
