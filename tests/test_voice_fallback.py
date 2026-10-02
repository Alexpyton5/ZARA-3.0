from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.ipc_handlers import IPCHandler
from core.voice_fallback import KoreRecoveryPolicy


class FakeKore:
    active = True

    def __init__(self, behavior):
        self.behavior = behavior
        self.calls = 0
        self.timeouts: list[float] = []

    async def speak(self, text: str, *, timeout: float) -> bool:
        self.calls += 1
        self.timeouts.append(timeout)
        return await self.behavior(text, timeout)


def _fast_policy() -> KoreRecoveryPolicy:
    return KoreRecoveryPolicy(
        minimum_timeout_seconds=0.01,
        maximum_timeout_seconds=0.01,
        base_timeout_seconds=0,
    )


@pytest.mark.asyncio
async def test_dead_kore_fails_fast_and_selects_fallback_route():
    async def dead(_text: str, _timeout: float) -> bool:
        raise ConnectionError("Kore unavailable")

    policy = _fast_policy()
    assert await policy.try_kore(FakeKore(dead), "Bom dia") is False
    assert policy.last_outcome == "error:ConnectionError"
    assert policy.current_engine == "fallback"
    assert policy.consecutive_failures == 1


@pytest.mark.asyncio
async def test_slow_kore_is_bounded_by_timeout():
    async def frozen(_text: str, timeout: float) -> bool:
        await asyncio.sleep(timeout * 20)
        return True

    policy = _fast_policy()
    kore = FakeKore(frozen)
    started = asyncio.get_running_loop().time()
    assert await policy.try_kore(kore, "Resposta curta") is False
    elapsed = asyncio.get_running_loop().time() - started

    assert elapsed < 0.15
    assert policy.last_outcome == "timeout"
    assert policy.current_engine == "fallback"
    assert kore.timeouts == [0.01]


@pytest.mark.asyncio
async def test_each_later_turn_reprobes_kore_and_uses_it_after_recovery():
    answers = [ConnectionError("temporary"), True]

    async def recovers(_text: str, _timeout: float) -> bool:
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    policy = _fast_policy()
    kore = FakeKore(recovers)

    assert await policy.try_kore(kore, "Primeira") is False
    assert policy.current_engine == "fallback"
    assert await policy.try_kore(kore, "Depois da recuperação") is True
    assert policy.last_outcome == "kore"
    assert policy.current_engine == "kore"
    assert policy.consecutive_failures == 0
    assert kore.calls == 2


@pytest.mark.asyncio
async def test_inactive_kore_is_not_called():
    async def should_not_run(_text: str, _timeout: float) -> bool:
        raise AssertionError("inactive Kore must not be called")

    kore = FakeKore(should_not_run)
    kore.active = False
    policy = _fast_policy()

    assert await policy.try_kore(kore, "Sem Kore") is False
    assert policy.last_outcome == "unavailable"
    assert kore.calls == 0


@pytest.mark.asyncio
async def test_ipc_times_out_kore_once_then_uses_existing_local_fallback():
    class FrozenKore:
        active = True

        def __init__(self):
            self.calls = 0

        async def speak(self, _text: str, *, timeout: float) -> bool:
            self.calls += 1
            await asyncio.sleep(timeout * 20)
            return True

        def ultimo_audio_entregue(self):
            return None

    class FakeEdge:
        voice_name = "test-edge"

        def __init__(self):
            self.spoken: list[str] = []

        def play(self, text, voice=None, speed=1.0, blocking=True):
            self.spoken.append(text)

    handler = IPCHandler(AsyncMock())
    handler.send_event = AsyncMock()
    handler._tts_initialized = True
    handler._kore_recovery_policy = KoreRecoveryPolicy(
        minimum_timeout_seconds=0.01,
        maximum_timeout_seconds=0.01,
        base_timeout_seconds=0,
    )
    kore = FrozenKore()
    edge = FakeEdge()
    handler.gemini_live_voice = kore
    handler.tts_manager = SimpleNamespace(
        edge=edge, kokoro=None, gemini=None
    )

    await handler._speak_response("Use a voz local se Kore travar.")

    assert kore.calls == 1
    assert handler._kore_recovery_policy.last_outcome == "timeout"
    assert edge.spoken == ["Use a voz local se Kore travar."]
