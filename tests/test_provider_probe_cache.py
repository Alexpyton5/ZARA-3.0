import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.lab_v1.domain import Availability, ProviderInfo, ProviderResult
from core.lab_v1.providers.base import ProviderAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.service import LabV1Service


class CountingAdapter(ProviderAdapter):
    id = "counting"
    label = "Counting"

    def __init__(self, delay=0.0):
        self.probes = 0
        self.delay = delay
        self._lock = threading.Lock()

    def probe(self):
        with self._lock:
            self.probes += 1
        if self.delay:
            time.sleep(self.delay)
        return ProviderInfo(
            id=self.id, label=self.label, adapter=self.id,
            availability=Availability.AVAILABLE, detail="factual",
            observed_at=123.5,
        )

    def complete(self, **kwargs):
        return ProviderResult(True, availability=Availability.AVAILABLE)


def test_probe_cache_preserves_fact_and_adverse_overlay_without_contamination(tmp_path):
    adapter = CountingAdapter()
    registry = ProviderRegistry(tmp_path / "health.json", probe_ttl_s=30)
    registry.register(adapter)

    first = registry.list_providers()[0]
    first.detail = "caller mutation"
    registry.record_result(
        adapter.id, "model", ProviderResult(False, availability=Availability.AUTH_REQUIRED, error="denied"),
        observed_at=time.time(),
    )
    adverse = registry.list_providers()[0]

    assert adapter.probes == 2  # real result invalidates the factual probe
    assert first.observed_at == 123.5
    assert adverse.availability is Availability.AUTH_REQUIRED
    assert adverse.observed_at > 0
    registry.record_result(
        adapter.id, "model", ProviderResult(True, availability=Availability.AVAILABLE), observed_at=time.time()
    )
    recovered = registry.list_providers()[0]
    assert recovered.availability is Availability.AVAILABLE
    assert recovered.observed_at == 123.5


def test_probe_cache_force_refresh_and_ttl(tmp_path):
    adapter = CountingAdapter()
    # TTL e sleep bem acima da resolucao do relogio Windows (15.6ms) para evitar flaky
    registry = ProviderRegistry(tmp_path / "health.json", probe_ttl_s=0.1)
    registry.register(adapter)
    registry.list_providers()
    registry.list_providers()
    assert adapter.probes == 1
    registry.list_providers(force_refresh=True)
    assert adapter.probes == 2
    time.sleep(0.25)
    registry.list_providers()
    assert adapter.probes == 3


def test_slow_probe_ttl_starts_after_probe_completion(tmp_path):
    adapter = CountingAdapter(delay=0.03)
    registry = ProviderRegistry(tmp_path / "health.json", probe_ttl_s=0.01)
    registry.register(adapter)
    registry.list_providers()
    registry.list_providers()
    assert adapter.probes == 1


def test_concurrent_first_poll_coalesces_probe(tmp_path):
    adapter = CountingAdapter()
    registry = ProviderRegistry(tmp_path / "health.json", probe_ttl_s=30)
    registry.register(adapter)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: registry.list_providers()[0], range(8)))
    assert adapter.probes == 1
    assert all(item.observed_at == 123.5 for item in results)


def test_register_replacement_invalidates_probe(tmp_path):
    first = CountingAdapter()
    second = CountingAdapter()
    registry = ProviderRegistry(tmp_path / "health.json", probe_ttl_s=30)
    registry.register(first)
    registry.list_providers()
    registry.register(second)
    registry.list_providers()
    assert first.probes == 1
    assert second.probes == 1


@pytest.mark.asyncio
async def test_background_starts_without_waiting_for_codex_metadata_discovery(monkeypatch):
    entered = threading.Event()
    release = threading.Event()

    class SlowCodex:
        id = "codex_cli"
        label = "OpenAI Codex"
        cache = {}

        def probe(self):
            return ProviderInfo(
                id="codex_cli", label="OpenAI Codex", adapter="codex_cli",
                availability=Availability.AUTH_REQUIRED,
            )

        def discover_models(self):
            entered.set()
            assert release.wait(timeout=2)
            self.cache = {"authenticated": True, "models": [{"model": "gpt-test"}]}
            return ()

    service = LabV1Service()
    registry = ProviderRegistry()
    registry.register(SlowCodex())
    service._runtime = SimpleNamespace(registry=registry)
    service._supervisor = SimpleNamespace(
        policy=lambda: {"background_enabled": False, "cadence_seconds": 3600}
    )
    service._start_operation_consumer = AsyncMock()

    started_at = time.monotonic()
    task = service._start_provider_discovery()
    elapsed = time.monotonic() - started_at

    assert task is service._provider_discovery_task
    assert elapsed < 0.2
    assert await asyncio.to_thread(entered.wait, 1)
    release.set()
    await asyncio.wait_for(service._provider_discovery_task, timeout=2)
    assert service._provider_discovery_error is None
    await service.stop_background()
