# Simple async scheduler that runs active strategies every N seconds.

import asyncio
import time
from typing import Dict, Callable, Any, Optional
from core.storage import list_strategies, insert_run, get_setting
from core.moomoo_client import MoomooClient

StrategyStep = Callable[[int, MoomooClient, str, Dict[str, Any]], None]

class TraderScheduler:
    def __init__(self, client_getter: Callable[[], Optional[MoomooClient]]) -> None:
        self._get_client = client_getter
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._registry: Dict[str, StrategyStep] = {}

    def register(self, name: str, step_fn: StrategyStep) -> None:
        self._registry[name] = step_fn

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._tick_all()
            except Exception as e:
                print("Scheduler tick error:", e)
            await asyncio.sleep(1.0)

    async def _tick_all(self) -> None:
        client = self._get_client()
        if client is None or not client.connected:
            return
        mode = (get_setting("bot_mode") or "assist").lower()
        if mode not in {"semi", "auto"}:
            for s in list_strategies():
                if s["active"]:
                    insert_run(s["id"], "SKIP", f"bot_mode={mode}")
            return
        now = time.time()
        for s in list_strategies():
            if not s["active"]:
                continue
            step_fn = self._registry.get(s["name"])
            if not step_fn:
                insert_run(s["id"], "ERROR", f"Strategy '{s['name']}' not registered")
                continue
            if int(now) % max(1, s["interval_sec"]) == 0:
                try:
                    step_fn(s["id"], client, s["symbol"], s["params"])
                except Exception as e:
                    insert_run(s["id"], "ERROR", str(e))

    async def stop(self) -> None:
        self._running = False
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except Exception:
                pass
            self._task = None
