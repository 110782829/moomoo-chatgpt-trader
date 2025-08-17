"""Skeleton for autopilot mode."""
from __future__ import annotations

import threading
import time


class Autopilot:
    """Hold autopilot state."""

    def __init__(self) -> None:
        self.active = False
        self.strategy = ""
        self.last_command = ""
        self.ticks = 0
        self._thread: threading.Thread | None = None
        self.tick_interval = 1.0

    def start(self, strategy: str | None = None) -> None:
        if self.active:
            return
        if strategy:
            self.strategy = strategy
        self.active = True
        self.ticks = 0
        self.last_command = "started"
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while self.active:
            self.tick()
            time.sleep(self.tick_interval)

    def stop(self) -> None:
        self.active = False
        t = self._thread
        if t and t.is_alive():
            t.join(timeout=0.1)
        self._thread = None
        self.last_command = "stopped"

    def set_strategy(self, name: str) -> None:
        self.strategy = name
        self.last_command = f"strategy:{name}"

    def tick(self) -> None:
        """Run one cycle placeholder."""
        self.ticks += 1
        self.last_command = f"tick:{self.ticks}"

    def status(self) -> dict:
        return {
            "active": self.active,
            "strategy": self.strategy,
            "last_command": self.last_command,
            "ticks": self.ticks,
        }
