#!/usr/bin/env python3
from __future__ import annotations
import asyncio
import sys

from core.model_router import ModelProvider, get_model_config, route_message
from core.zara_orchestrator import ZaraOrchestrator

cfg = get_model_config("ollama_qwen3_4b")
assert cfg is not None, "ollama_qwen3_4b missing"
assert cfg.provider == ModelProvider.OLLAMA, "wrong provider"

primary, chain = route_message(
    "Explique em uma frase qual é a função do laboratório da ZARA."
)
assert primary is not None, "no AUTO model available"
assert primary.id == "ollama_qwen3_4b", f"expected local AUTO, got {primary.id}"

async def main():
    orch = ZaraOrchestrator()
    await orch.initialize()
    result = await orch.process_message(
        "Responda exatamente: ZARA_OLLAMA_OK",
        engine="ollama_qwen3_4b",
    )
    if "ZARA_OLLAMA_OK" not in result:
        raise AssertionError(f"unexpected local response: {result[:200]}")
    print("PASS: ZARA AUTO sees Ollama and direct local inference works")

asyncio.run(main())
