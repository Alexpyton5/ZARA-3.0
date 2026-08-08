"""HermesBridge — ponte de estado entre a ZARA e o gateway Hermes.

- load_config(): lê config/api_keys.json, sobe o gateway se ativo, inicia
  o monitor de saúde (daemon thread com event loop próprio, pois roda na
  thread da UI antes do loop do asyncio existir).
- route_message(): envia para o cérebro com histórico; fallback para o
  handler local se inativo/indisponível.
"""
from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from integrations.hermes.client import HermesClient
from integrations.hermes.ensure_gateway import start_gateway

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "api_keys.json"


@dataclass
class HealthStatus:
    connected: bool = False
    status: str = "unknown"
    version: str = ""
    latency_ms: float | None = None


@dataclass
class BridgeStatus:
    hermes_ativo: bool = False
    health: HealthStatus = field(default_factory=HealthStatus)


class HermesBridge:
    def __init__(self, config_path: Path | str | None = None):
        self._config_path = Path(config_path) if config_path else CONFIG_PATH
        self._status = BridgeStatus()
        self._client: HermesClient | None = None
        self._health_task: asyncio.Task | None = None
        self._on_health_change: Callable[[HealthStatus], None] | None = None

    # ------------------------------------------------------------------ #
    # Config
    # ------------------------------------------------------------------ #
    def load_config(self) -> dict:
        try:
            with open(self._config_path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:  # noqa: BLE001
            data = {}
        active = bool(data.get("hermes_ativo", False))
        self._status.hermes_ativo = active
        self._client = HermesClient(
            {
                "url": data.get("hermes_url"),
                "api_key": data.get("hermes_api_key"),
                "timeout": data.get("hermes_timeout"),
            }
        )
        if active:
            start_gateway(self._client.base_url)
            self._start_health_monitor()
        return data

    # ------------------------------------------------------------------ #
    # Estado
    # ------------------------------------------------------------------ #
    @property
    def is_active(self) -> bool:
        return self._status.hermes_ativo

    @property
    def status(self) -> BridgeStatus:
        return self._status

    def set_active(self, active: bool) -> None:
        self._status.hermes_ativo = active
        if active:
            self._start_health_monitor()
        elif self._health_task is not None:
            self._health_task.cancel()
            self._health_task = None

    def set_health_callback(self, cb: Callable[[HealthStatus], None]) -> None:
        self._on_health_change = cb

    def start_gateway(self) -> bool:
        """Start the Hermes gateway if not already running."""
        if not self._client:
            return False
        success = start_gateway(self._client.base_url)
        if success:
            self._status.hermes_ativo = True
            self._start_health_monitor()
        return success

    def stop_gateway(self) -> None:
        """Stop the Hermes gateway monitoring."""
        self._status.hermes_ativo = False
        if self._health_task is not None:
            self._health_task.cancel()
            self._health_task = None

    # ------------------------------------------------------------------ #
    # Saúde
    # ------------------------------------------------------------------ #
    async def check_health(self) -> HealthStatus:
        hs = HealthStatus()
        if self._client is None:
            return hs
        import time

        t0 = time.monotonic()
        try:
            ok = await asyncio.to_thread(self._client.health)
            hs.connected = ok
            hs.status = "connected" if ok else "offline"
            hs.latency_ms = round((time.monotonic() - t0) * 1000, 1)
        except Exception:  # noqa: BLE001
            hs.connected = False
            hs.status = "offline"
        return hs

    def _start_health_monitor(self) -> None:
        if self._health_task is not None and not self._health_task.done():
            return

        async def _monitor() -> None:
            while self._status.hermes_ativo:
                try:
                    health = await self.check_health()
                    self._status.health = health
                    if self._on_health_change:
                        self._on_health_change(health)
                except Exception:  # noqa: BLE001
                    pass
                await asyncio.sleep(30)

        try:
            loop = asyncio.get_running_loop()
            self._health_task = loop.create_task(_monitor())
        except RuntimeError:
            # load_config roda na thread da UI antes do loop existir
            threading.Thread(
                target=lambda: asyncio.run(_monitor()),
                daemon=True,
                name="hermes-health",
            ).start()

    # ------------------------------------------------------------------ #
    # Roteamento
    # ------------------------------------------------------------------ #
    def route_message(
        self,
        message: str,
        fallback_handler: Callable[[str], Any] | None = None,
        history: list | None = None,
    ) -> Any:
        """Retorna a resposta do cérebro, ou chama o fallback se indisponível."""
        if not self.is_active or self._client is None:
            if fallback_handler:
                return fallback_handler(message)
            return None
        result = self._client.send_message(message, history)
        if result["success"]:
            return result["text"]
        if fallback_handler:
            return fallback_handler(message)
        return None

    async def route_message_async(
        self,
        message: str,
        fallback_handler: Callable[[str], Any] | None = None,
        history: list | None = None,
    ) -> Any:
        if not self.is_active or self._client is None:
            return fallback_handler(message) if fallback_handler else None
        result = await asyncio.to_thread(self._client.send_message, message, history)
        if result["success"]:
            return result["text"]
        return fallback_handler(message) if fallback_handler else None
