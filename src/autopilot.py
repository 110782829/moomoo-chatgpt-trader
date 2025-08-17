"""Skeleton for autopilot mode."""
from __future__ import annotations

class Autopilot:
    """Hold autopilot state."""
    def __init__(self) -> None:
        self.active = False
        self.last_command = ""

    def start(self) -> None:
        self.active = True
        self.last_command = "started"

    def stop(self) -> None:
        self.active = False
        self.last_command = "stopped"

    def status(self) -> dict:
        return {"active": self.active, "last_command": self.last_command}
