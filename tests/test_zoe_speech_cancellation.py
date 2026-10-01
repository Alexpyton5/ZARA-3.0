"""An outer Kore recovery timeout must release the real queued speech sender."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from core.gemini_live_voice import GeminiLiveVoice, GeminiLiveVoiceConfig


@pytest.mark.asyncio
async def test_cancelling_active_speech_releases_sender_and_cuts_audio():
    voice = GeminiLiveVoice(GeminiLiveVoiceConfig(api_key='test-only'))
    voice._task = asyncio.create_task(asyncio.Event().wait())
    voice._speech_queue = asyncio.Queue()
    voice.interrupt_speech = AsyncMock()
    speech = asyncio.create_task(voice.speak('Resposta', timeout=10))
    _, done = await voice._speech_queue.get()
    voice._speech_done = done
    speech.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await speech
        assert done.is_set()
        voice.interrupt_speech.assert_awaited_once()
    finally:
        voice._task.cancel()
        await asyncio.gather(voice._task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancelling_queued_speech_does_not_interrupt_another_utterance():
    voice = GeminiLiveVoice(GeminiLiveVoiceConfig(api_key='test-only'))
    voice._task = asyncio.create_task(asyncio.Event().wait())
    voice._speech_queue = asyncio.Queue()
    voice.interrupt_speech = AsyncMock()
    voice._speech_done = asyncio.Event()
    speech = asyncio.create_task(voice.speak('Resposta', timeout=10))
    _, done = await voice._speech_queue.get()
    speech.cancel()
    try:
        with pytest.raises(asyncio.CancelledError):
            await speech
        assert done.is_set()
        voice.interrupt_speech.assert_not_awaited()
    finally:
        voice._task.cancel()
        await asyncio.gather(voice._task, return_exceptions=True)
