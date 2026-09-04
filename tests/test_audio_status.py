from core.actions import os_ops
from core.pc_voice_intent import PcVoiceIntentDetector


def test_audio_status_voice_route_is_local():
    result = PcVoiceIntentDetector().detect("qual é o dispositivo de áudio")
    assert result.action == "audio_status"
    assert result.blocked is False


def test_audio_status_reports_backend_failure_honestly(monkeypatch):
    monkeypatch.setattr(os_ops.platform, "system", lambda: "Linux")
    result = os_ops.audio_status_action()
    assert result.success is False
