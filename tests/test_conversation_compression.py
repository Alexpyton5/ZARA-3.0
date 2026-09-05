"""AUDITORIA_2026-08-27: conversa longa (horas) estourava o contexto porque
o historico crescia sem limite nenhum, reenviado inteiro a cada turno.
Ideia de "sliding-window compression" inspirada no Mark LI, codigo do zero."""
from __future__ import annotations

from core.conversation_compression import compress_history


def test_short_history_passes_through_unchanged():
    history = [{"role": "user", "content": "oi"}, {"role": "assistant", "content": "oi!"}]

    assert compress_history(history) == history


def test_none_and_empty_never_raise():
    assert compress_history(None) == []
    assert compress_history([]) == []


def test_long_history_keeps_recent_messages_and_summarizes_the_rest():
    history = [{"role": "user", "content": f"mensagem numero {i}"} for i in range(200)]

    result = compress_history(history, max_messages=10, max_chars=100_000)

    assert result[0]["role"] == "system"
    assert "mensagem(ns) mais antiga(s)" in result[0]["content"]
    assert len(result) == 11  # 1 resumo + 10 mensagens recentes
    assert result[-1]["content"] == "mensagem numero 199"
    assert result[1]["content"] == "mensagem numero 190"


def test_huge_single_messages_are_bounded_by_char_budget_too():
    history = [{"role": "user", "content": "x" * 5000} for _ in range(10)]

    result = compress_history(history, max_messages=1000, max_chars=12_000)

    total_chars = sum(len(m.get("content", "")) for m in result if m["role"] != "system")
    assert total_chars <= 12_000
    assert result[0]["role"] == "system"


def test_ignores_malformed_entries_instead_of_crashing():
    history = ["nao e um dict", 123, None, {"role": "user", "content": "valido"}]

    result = compress_history(history)

    assert result == [{"role": "user", "content": "valido"}]
