"""Skeleton for autopilot mode."""
from __future__ import annotations

class Autopilot:
    """Hold autopilot state."""

    def __init__(self) -> None:
        self.active = False
        self.strategy = ""
        self.last_command = ""

    def start(self, strategy: str | None = None) -> None:
        if strategy:
            self.strategy = strategy
        self.active = True
        self.last_command = "started"

    def stop(self) -> None:
        self.active = False
        self.last_command = "stopped"

    def set_strategy(self, name: str) -> None:
        self.strategy = name
        self.last_command = f"strategy:{name}"

    def tick(self) -> None:
        """Run one cycle placeholder."""
        self.last_command = "tick"

    def status(self) -> dict:
        return {
            "active": self.active,
            "strategy": self.strategy,
            "last_command": self.last_command,
        }
