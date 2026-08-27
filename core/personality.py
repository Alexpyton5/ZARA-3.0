"""ZARA-PERSONALIDADE-2026-08-27: fonte unica de personalidade da Zara.

Antes, a voz (core/gemini_live_voice.py) e o texto (core/zara_orchestrator.py)
tinham cada um sua propria string de personalidade escrita direto no codigo,
podendo divergir sem ninguem perceber. Agora os dois leem o mesmo arquivo,
que fica na raiz do projeto pra ser facil de editar sem mexer em codigo.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

_FALLBACK_PERSONALITY = (
    "Você é ZARA, a assistente pessoal de Alex. Responda em português do Brasil "
    "quando ele falar em português. Em conversa casual, soe humana, direta e "
    "acolhedora: normalmente use de uma a três frases curtas. Não transforme uma "
    "pergunta simples em lista, tutorial ou palestra, salvo quando Alex pedir ou "
    "quando isso for realmente necessário. Responda primeiro ao que foi perguntado "
    "e não encerre toda resposta com outra pergunta. Seja precisa e não invente certezas."
)

_lock = threading.Lock()
_cached: str | None = None


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def load_personality(force_reload: bool = False) -> str:
    """Return the personality text, read from PERSONALIDADE_DA_ZARA.txt.

    Falls back to a hardcoded copy if the file is missing or unreadable, so
    a moved/deleted file degrades Zara's tone, not her ability to run.
    """
    global _cached
    if _cached is not None and not force_reload:
        return _cached

    with _lock:
        if _cached is not None and not force_reload:
            return _cached
        path = _project_root() / "PERSONALIDADE_DA_ZARA.txt"
        try:
            raw = path.read_text(encoding="utf-8").strip()
            # O arquivo e quebrado em linhas curtas so pra ficar facil de ler
            # e editar num bloco de notas qualquer; a quebra de linha em si
            # nao deve virar uma quebra de frase no texto usado de verdade.
            paragraphs = raw.split("\n\n")
            text = "\n\n".join(" ".join(p.split()) for p in paragraphs)
            _cached = text if text else _FALLBACK_PERSONALITY
        except OSError:
            _cached = _FALLBACK_PERSONALITY
        return _cached
