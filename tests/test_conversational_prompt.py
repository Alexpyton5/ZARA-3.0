from types import SimpleNamespace

import pytest

from core.model_router import ModelProvider
from core.zara_orchestrator import CONVERSATIONAL_SYSTEM_PROMPT, ZaraOrchestrator


class _Response:
    status_code = 200

    def json(self):
        return {
            "choices": [{"message": {"content": "ok"}}],
            "candidates": [{"content": {"parts": [{"text": "ok"}]}}],
        }


class _Client:
    def __init__(self):
        self.payload = None

    async def post(self, _url, *, json, **_kwargs):
        self.payload = json
        return _Response()


def _model(provider):
    return SimpleNamespace(
        provider=provider,
        api_model="test-model",
        base_url="https://example.invalid",
        max_tokens=128,
        id="test-model",
    )


def test_conversational_prompt_sets_a_short_human_default():
    assert "uma a três frases curtas" in CONVERSATIONAL_SYSTEM_PROMPT
    assert "não encerre toda resposta com outra pergunta" in CONVERSATIONAL_SYSTEM_PROMPT
    assert "Não transforme uma pergunta simples em lista" in CONVERSATIONAL_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_openai_compatible_uses_shared_conversational_prompt():
    client = _Client()
    await ZaraOrchestrator()._call_openai_compatible(
        "oi", _model(ModelProvider.GROQ), "test-key", client
    )
    assert client.payload["messages"][0]["content"] == CONVERSATIONAL_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_gemini_uses_shared_conversational_prompt():
    client = _Client()
    await ZaraOrchestrator()._call_gemini(
        "oi", _model(ModelProvider.GEMINI), "test-key", client
    )
    assert client.payload["systemInstruction"]["parts"][0]["text"] == CONVERSATIONAL_SYSTEM_PROMPT
