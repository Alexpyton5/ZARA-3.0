from unittest.mock import AsyncMock

import pytest

from core.actions import os_ops
from core.ipc_handlers import IPCHandler
from core.pc_voice_intent import PcVoiceIntentDetector


@pytest.mark.parametrize(
    ("phrase", "expected_action"),
    [
        ("pause a música", "youtube_pause"),
        ("pause", "youtube_pause"),
        ("pausa", "youtube_pause"),
        ("continue a música", "youtube_resume"),
        ("continue", "youtube_resume"),
        ("play", "youtube_resume"),
        ("próxima música", "youtube_next"),
        ("próxima", "youtube_next"),
        ("pule essa", "youtube_next"),
        ("música anterior", "media_previous"),
        ("anterior", "media_previous"),
        ("volta a música", "media_previous"),
        ("volte a faixa", "media_previous"),
        ("mute", "audio_mute"),
        ("tire do mudo", "audio_unmute"),
        ("tira do mudo", "audio_unmute"),
    ],
)
def test_media_phrases_map_to_closed_actions(phrase, expected_action):
    result = PcVoiceIntentDetector(pc_control_allowed=True).detect(phrase)

    assert result.is_pc_intent is True
    assert result.action == expected_action
    assert result.blocked is False


@pytest.mark.parametrize(
    "phrase",
    [
        "faça uma pausa no projeto",
        "continue o relatório",
        "qual é a próxima música do álbum?",
        "execute media_next && powershell",
        "mute o microfone do aplicativo",
    ],
)
def test_media_patterns_do_not_trigger_media_for_common_or_arbitrary_text(phrase):
    result = PcVoiceIntentDetector(pc_control_allowed=True).detect(phrase)

    assert result.action not in {
        "media_play_pause",
        "media_next",
        "media_previous",
        "audio_mute",
        "audio_unmute",
    }
    assert result.physical_effect == 0


def test_native_media_action_uses_only_fixed_windows_command(monkeypatch):
    calls = []
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_send_windows_media_command", calls.append)

    result = os_ops.media_next_action()

    # Tarefa 054 / Regra #11: comando emitido mas estado NAO verificado ->
    # nao alegar sucesso. Espera NOT_PROVEN honesto.
    assert result.success is False
    assert result.error == "MEDIA_COMMAND_SENT_NOT_PROVEN"
    assert calls == ["media_next"]
    # 217: o adapter semantico acrescenta campos de readback; o contrato
    # essencial (nao provado) permanece.
    assert result.data["action"] == "media_next"
    assert result.data["transport"] == "WM_APPCOMMAND"
    assert result.data["state_verified"] is False
    assert result.data["readback"] in {"UNAVAILABLE", "NO_SEMANTIC_CHANGE"}


@pytest.mark.parametrize(("desired", "reply"), [(True, "Mudo ativado."), (False, "Mudo desativado.")])
def test_mute_action_requires_post_action_state_verification(monkeypatch, desired, reply):
    states = iter((not desired, desired))
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_read_windows_mute", lambda: next(states))
    writes = []
    monkeypatch.setattr(os_ops, "_set_windows_mute", lambda value: writes.append(value) or True)

    result = os_ops._audio_mute_action(desired)

    assert result.success is True
    assert result.output == reply
    assert writes == [desired]
    assert result.data["verified_muted"] is desired


def test_mute_action_does_not_claim_success_without_verified_state(monkeypatch):
    states = iter((False, False))
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Windows")
    monkeypatch.setattr(os_ops, "_read_windows_mute", lambda: next(states))
    monkeypatch.setattr(os_ops, "_set_windows_mute", lambda value: True)

    result = os_ops.audio_mute_action()

    assert result.success is False
    assert "não pôde ser confirmado" in result.error


@pytest.mark.asyncio
async def test_local_media_dispatch_works_without_superbrain(monkeypatch):
    execute = AsyncMock(
        return_value=type(
            "Result", (),
            {
                "success": False,
                "error": "MEDIA_COMMAND_SENT_NOT_PROVEN",
                "output": "Comando de próxima faixa enviado.",
            },
        )()
    )
    handler = IPCHandler(AsyncMock())
    monkeypatch.setattr("core.action_registry.execute_action", execute)

    reply = await handler._try_pc_intent("próxima música")

    assert "MEDIA_COMMAND_SENT_NOT_PROVEN" in reply
    execute.assert_awaited_once_with("youtube_next")


@pytest.mark.asyncio
async def test_ipc_routes_media_action_when_capability_is_on(monkeypatch):
    calls = []

    async def fake_execute_action(action, **params):
        calls.append((action, params))
        return type("Result", (), {"success": True, "error": "", "output": "Comando play/pause enviado."})()

    handler = IPCHandler(AsyncMock())
    handler._set_supercerebro_state(True)
    monkeypatch.setattr("core.action_registry.execute_action", fake_execute_action)

    reply = await handler._try_pc_intent("pause a música")

    assert calls == [("youtube_pause", {})]
    assert reply == "Comando play/pause enviado."
