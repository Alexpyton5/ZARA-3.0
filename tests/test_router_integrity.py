"""Router integrity proofs (ZARA-NIGHT-SHIFT 049-050 / 054).

049 found a real orphan route: the voice intent detector mapped "role a tela para
baixo" to an unregistered action. P1-B resolves it with the registered,
readback-verified browser_scroll action.
execute_action() raised ValueError, the generic except swallowed it and returned
None, so the request fell through to the LLM — which can happily answer as if the
screen had scrolled. That is exactly the false-success class this shift must kill.

050 fixes it with the smallest honest patch: a detected PC intent whose action is
not registered returns an explicit unsupported message instead of falling through.
"""
from __future__ import annotations

import asyncio

import pytest

import core.actions  # noqa: F401  (registers all actions)
from core.action_registry import execute_action, get_registry
from core.ipc_handlers import IPCHandler
from core.pc_voice_intent import PcVoiceIntentDetector


def _detector(**kw):
    kw.setdefault("pc_control_allowed", True)
    return PcVoiceIntentDetector(**kw)


def _handler():
    h = IPCHandler.__new__(IPCHandler)
    h.supercerebro_active = True
    h._last_volume_level = 40
    h._last_window_hwnd = None
    h._last_safe_folder = None
    h._last_brightness_level = None
    h._operational_context_turns = 0
    h._context_fresh = lambda _kind: False  # type: ignore[method-assign]
    h._set_operational_context = lambda *a, **k: None  # type: ignore[method-assign]
    h._clear_operational_context = lambda: None  # type: ignore[method-assign]
    return h


# ---------- 049 diagnostico ----------
def test_049_every_registered_action_name_is_unique():
    specs = get_registry()._specs
    assert len(specs) == len(set(specs))


def test_049_scroll_intent_is_detected():
    res = _detector().detect("role para baixo")
    assert res.is_pc_intent is True
    assert res.action == "browser_scroll"


def test_049_scroll_action_is_registered():
    assert "browser_scroll" in get_registry()._specs


def test_049_executing_an_unknown_action_still_raises():
    with pytest.raises(ValueError):
        asyncio.run(execute_action("scroll", direction="down"))


# ---------- 050 correcao ----------
@pytest.mark.asyncio
async def test_050_unsupported_intent_returns_honest_message_not_none():
    """Scroll reaches its executor and reports runtime failure honestly."""
    reply = await _handler()._try_pc_intent("role para baixo")
    assert reply is not None, "nao pode cair no LLM"
    assert "não consegui" in reply.lower()


@pytest.mark.asyncio
async def test_050_unsupported_intent_never_claims_success():
    reply = await _handler()._try_pc_intent("role para cima")
    lowered = reply.lower()
    for lie in ("pronto", "feito", "rolei", "concluído", "concluido"):
        assert lie not in lowered


@pytest.mark.asyncio
async def test_050_non_pc_message_still_falls_through_to_llm():
    assert await _handler()._try_pc_intent("me explica o que é um relay") is None


@pytest.mark.asyncio
async def test_050_open_ended_browser_intent_still_asks_for_supercerebro():
    h = _handler()
    h.supercerebro_active = False
    reply = await h._try_pc_intent("abra o site da openai")
    assert reply is not None
    assert "supercérebro" in reply.lower()


@pytest.mark.parametrize(
    "text,expected_action",
    [
        ("abra a calculadora", "os_app"),
        ("volume em 30", "os_volume"),
        ("abra downloads", "os_open"),
        ("mute", "audio_mute"),
        ("minimize a janela", "window_minimize"),
        ("ative a luz noturna", "os_night_light_on"),
    ],
)
def test_050_core_routes_point_to_registered_actions(text, expected_action):
    res = _detector().detect(text)
    assert res.action == expected_action
    assert expected_action in get_registry()._specs, f"rota orfa: {expected_action}"


def test_050_all_intent_actions_except_known_gap_are_registered():
    """Rede de seguranca: nenhuma rota orfa NOVA pode ser introduzida."""
    import inspect
    import re

    src = inspect.getsource(PcVoiceIntentDetector)
    referenced = set(re.findall(r'"([a-z_]+)",\s*(?:"[^"]*"|None)\)', src))
    referenced |= set(re.findall(r'action="([a-z_]+)"', src))
    registered = set(get_registry()._specs)
    assert not (referenced - registered)
