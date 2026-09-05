"""ZARA-SCREEN-UNDERSTANDING-001 (Alex, 2026-08-28). Peça isolada.

A ação `vision_screenshot` (core/actions/vision.py) já CAPTURA a tela; a
ação `vision_ocr` já extrai texto simples. O que falta -- e é o que este
módulo adiciona -- é ENTENDER a imagem (descrever um gráfico, apontar um
erro na tela, ler um layout) via modelo multimodal. Não recaptura a tela:
recebe o caminho de uma imagem já salva.

Mesma disciplina do classificador de raciocínio livre
(core/intent_classifier.py): falha fechada (sem chave/rede/erro -> None,
nunca inventa descrição), chamada HTTP própria e enxuta (não altera
core/model_router.py, só lê a config dele).
"""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

_DEFAULT_MODEL_ID = "gemini_36_flash"
_DEFAULT_TIMEOUT_S = 20.0
_MIME_BY_SUFFIX = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


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


def describe_screen(
    image_path: str,
    question: str = "Descreva o que está na tela, de forma objetiva.",
    *,
    model_id: str = _DEFAULT_MODEL_ID,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
) -> str | None:
    """Envia uma captura de tela já salva pra um modelo multimodal e
    devolve a resposta em texto. None quando não há como responder com
    segurança (sem chave, imagem ausente, formato não suportado, erro de
    rede) -- quem chamar deve tratar como 'não consegui olhar a tela'."""
    path = Path(image_path)
    if not path.exists():
        return None
    mime = _MIME_BY_SUFFIX.get(path.suffix.lower())
    if mime is None:
        return None

    config = _resolve_model(model_id)
    if config is None:
        return None

    try:
        image_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None

    try:
        import httpx
    except Exception:
        return None

    api_key = str(os.environ.get(config.api_key_env) or "").strip()
    url = f"{config.base_url}/models/{config.api_model}:generateContent?key={api_key}"
    payload = {
        "contents": [{
            "parts": [
                {"text": str(question or "").strip() or "Descreva a imagem."},
                {"inline_data": {"mime_type": mime, "data": image_b64}},
            ]
        }]
    }

    try:
        response = httpx.post(url, json=payload, timeout=timeout_s)
        if response.status_code != 200:
            return None
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts") or []
        text = "".join(str(part.get("text", "")) for part in parts).strip()
        return text or None
    except Exception:
        return None
