"""ZARA-MEETING-TRANSCRIBER-001 (Alex, 2026-08-28). Peça isolada.

Transcreve um ARQUIVO de áudio já gravado (faster-whisper, já dependência
do projeto) e resume o texto. Escopo deliberadamente menor que o pedido
original: capturar áudio do SISTEMA ao vivo (loopback, não microfone) é uma
peça de captura separada e mais arriscada (específica de driver de áudio),
não construída aqui -- este módulo assume que o .wav/.mp3 da reunião já
existe em disco, de qualquer fonte.

`summarize_transcript` reusa o mesmo padrão de chamada de modelo enxuta e
falha-fechada de `core/intent_classifier.py`/`core/screen_understanding.py`
-- não altera core/model_router.py, só lê a config dele.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_DEFAULT_MODEL_SIZE = "base"
# NVIDIA NIM: endpoint OpenAI-compatible (/chat/completions), igual ao
# classificador de raciocínio livre já usa (core/intent_classifier.py).
# Gemini NÃO usa esse formato de endpoint -- não misturar os dois.
_SUMMARY_MODEL_ID = "nvidia_glm52"
_DEFAULT_TIMEOUT_S = 30.0


def transcribe_audio_file(audio_path: str, *, model_size: str = _DEFAULT_MODEL_SIZE) -> str | None:
    """Transcreve um arquivo de áudio local. None se o arquivo não existir
    ou faster-whisper não estiver disponível -- nunca inventa transcrição."""
    path = Path(audio_path)
    if not path.exists():
        return None

    try:
        from faster_whisper import WhisperModel
    except Exception:
        return None

    try:
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        segments, _info = model.transcribe(str(path), language="pt")
        return " ".join(segment.text.strip() for segment in segments).strip() or None
    except Exception:
        return None


def _resolve_model(model_id: str) -> Any | None:
    try:
        from core.model_router import get_model_config
    except Exception:
        return None
    config = get_model_config(model_id)
    if config is None:
        return None
    if not str(os.environ.get(config.api_key_env) or "").strip():
        return None
    return config


def summarize_transcript(
    transcript: str,
    *,
    focus: str = "pontos principais e tarefas combinadas",
    model_id: str = _SUMMARY_MODEL_ID,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> str | None:
    """Resume uma transcrição via LLM leve. None se não houver chave/rede/
    transcrição -- quem chamar decide como avisar que o resumo falhou."""
    text = str(transcript or "").strip()
    if not text:
        return None

    config = _resolve_model(model_id)
    if config is None:
        return None

    try:
        import httpx
    except Exception:
        return None

    prompt = (
        f"Resuma esta transcrição de reunião em português, focando em {focus}. "
        "Seja objetivo, use tópicos curtos.\n\n" + text[:8000]
    )
    try:
        response = httpx.post(
            f"{config.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {os.environ.get(config.api_key_env)}"},
            json={
                "model": config.api_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 600,
            },
            timeout=timeout_s,
        )
        if response.status_code != 200:
            return None
        return str(response.json()["choices"][0]["message"]["content"]).strip() or None
    except Exception:
        return None
