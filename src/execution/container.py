"""Execution container: broker-only adapter (Moomoo).

Removes local SIM storage and DB mirroring. Keeps a mode switch for future
expansion, but currently returns the moomoo-backed execution service in all
cases.
"""

from __future__ import annotations

from typing import Callable, Optional

_client_accessor: Optional[Callable[[], object]] = None  # returns MoomooClient
_mode: str = "moomoo"  # fixed for now; selector retained for future expansion


def init_execution(app=None) -> None:
    # No-op: no local storage required
    return None


def set_client_accessor(fn: Callable[[], object]) -> None:
    global _client_accessor
    _client_accessor = fn


def set_mode(mode: str) -> None:
    # Keep the selector for UI, but ignore non-moomoo modes for now
    global _mode
    _mode = (mode or "moomoo").strip().lower() or "moomoo"


def get_mode() -> str:
    return _mode


def get_execution():
    if _client_accessor is None:
        raise RuntimeError("Moomoo client accessor missing")
    from .moomoo_exec import MoomooExecutionService  # type: ignore
    return MoomooExecutionService(_client_accessor)
