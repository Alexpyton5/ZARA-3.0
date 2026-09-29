"""Degrau Ollama na escada padrao dos assentos (infra do coordenador, 28/09/2026).

A escada tem que ser: modelo do assento -> gratis barato (NVIDIA nano) ->
FreeLLMAPI "auto" -> Ollama local (qwen3:8b) -> Luna (cota paga, ULTIMA).
Gratis primeiro, pago por ultimo — sempre, sem duplicados.
"""
from core.lab_v1.fixed_seats import FIXED_SEATS
from core.lab_v1.seat_engines import (
    CODEX_CLI,
    FREELLMAPI,
    NVIDIA,
    OLLAMA,
    default_ladder_for,
    engine_for,
)


def _providers(ladder):
    return [(rung.provider_id, rung.model) for rung in ladder]


def test_ladder_order_free_first_paid_last():
    ladder = _providers(default_ladder_for("CEO"))
    assert ladder[0] == (NVIDIA, "nvidia/nemotron-3-ultra-550b-a55b")
    assert ladder[1] == (NVIDIA, "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
    assert ladder[2] == (FREELLMAPI, "auto")
    assert ladder[3] == (OLLAMA, "qwen3:8b")
    assert ladder[4] == (CODEX_CLI, "gpt-5.6-luna")
    assert len(ladder) == 5


def test_ladder_no_duplicates_for_any_seat():
    for role in FIXED_SEATS:
        ladder = _providers(default_ladder_for(role))
        assert len(ladder) == len(set(ladder)), role


def test_ollama_rung_present_and_luna_last_for_every_seat():
    for role in FIXED_SEATS:
        ladder = _providers(default_ladder_for(role))
        assert (OLLAMA, "qwen3:8b") in ladder, role
        # Luna continua sendo o ULTIMO degrau (nunca o padrao).
        assert ladder[-1] == (CODEX_CLI, "gpt-5.6-luna"), role


def test_engine_for_unknown_role_falls_back_to_cheap():
    assert engine_for("FANTASMA") == (
        NVIDIA, "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning")
