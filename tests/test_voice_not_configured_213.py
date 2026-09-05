"""213/214 — voz local: status honesto, sem download autonomo, sem microfone real."""
from __future__ import annotations

import pytest

from core import voice_stt, voice_tts
from core.voice_stt import VoiceConfig, VoiceNotConfiguredError, VoskSTT
from core.voice_tts import KokoroTTS, TTSConfig, TTSManager


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Any autonomous download attempt must fail the test loudly."""
    import urllib.request

    def _boom(*a, **k):  # pragma: no cover - must never run
        raise AssertionError(f"AUTONOMOUS DOWNLOAD ATTEMPTED: {a!r}")

    monkeypatch.setattr(urllib.request, "urlretrieve", _boom)


def test_stt_missing_backend_is_not_configured(monkeypatch):
    monkeypatch.setattr(voice_stt, "VOSK_AVAILABLE", False)
    with pytest.raises(VoiceNotConfiguredError) as exc:
        VoskSTT(VoiceConfig())
    assert "STT_BACKEND_NOT_CONFIGURED" in str(exc.value)


def test_stt_missing_weights_is_not_configured_and_never_downloads(monkeypatch, tmp_path):
    monkeypatch.setattr(voice_stt, "VOSK_AVAILABLE", True)
    monkeypatch.setattr(voice_stt, "user_data_dir", lambda: tmp_path)
    with pytest.raises(VoiceNotConfiguredError) as exc:
        VoskSTT(VoiceConfig(vosk_model_path=""))
    assert "STT_MODEL_NOT_CONFIGURED" in str(exc.value)


def test_stt_nonexistent_configured_path_falls_back_to_not_configured(monkeypatch, tmp_path):
    monkeypatch.setattr(voice_stt, "VOSK_AVAILABLE", True)
    monkeypatch.setattr(voice_stt, "user_data_dir", lambda: tmp_path)
    with pytest.raises(VoiceNotConfiguredError):
        VoskSTT(VoiceConfig(vosk_model_path=str(tmp_path / "__no_such_model__")))


def test_stt_valid_mock_backend_loads(monkeypatch, tmp_path):
    """A configured (fake but present) path uses the backend, no download."""
    model_dir = tmp_path / "models" / "vosk" / "vosk-model-small-pt-0.3"
    model_dir.mkdir(parents=True)
    loaded = {}

    class _FakeRec:
        def SetWords(self, v): loaded["words"] = v

    class _FakeVosk:
        Model = staticmethod(lambda p: loaded.setdefault("path", p))
        KaldiRecognizer = staticmethod(lambda m, sr: _FakeRec())

    monkeypatch.setattr(voice_stt, "VOSK_AVAILABLE", True)
    monkeypatch.setattr(voice_stt, "vosk", _FakeVosk)
    monkeypatch.setattr(voice_stt, "user_data_dir", lambda: tmp_path)

    VoskSTT(VoiceConfig())
    assert "vosk-model-small-pt-0.3" in loaded["path"]


def test_tts_missing_backend_is_not_configured(monkeypatch):
    monkeypatch.setattr(voice_tts, "KOKORO_AVAILABLE", False)
    with pytest.raises(VoiceNotConfiguredError) as exc:
        KokoroTTS(TTSConfig())
    assert "TTS_BACKEND_NOT_CONFIGURED" in str(exc.value)


def test_tts_missing_weights_is_not_configured_and_never_downloads(monkeypatch, tmp_path):
    monkeypatch.setattr(voice_tts, "KOKORO_AVAILABLE", True)
    monkeypatch.setattr(voice_tts, "user_data_dir", lambda: tmp_path)
    with pytest.raises(VoiceNotConfiguredError) as exc:
        KokoroTTS(TTSConfig())
    assert "TTS_MODEL_NOT_CONFIGURED" in str(exc.value)


def test_tts_manager_no_engine_fails_honestly_not_silently(monkeypatch, tmp_path):
    monkeypatch.setattr(voice_tts, "KOKORO_AVAILABLE", True)
    monkeypatch.setattr(voice_tts, "EDGE_TTS_AVAILABLE", False)
    monkeypatch.setattr(voice_tts, "user_data_dir", lambda: tmp_path)
    mgr = TTSManager(TTSConfig(prefer_local=True, gemini_api_key=""))
    with pytest.raises(RuntimeError):
        mgr.initialize()
    assert mgr.edge is None
    assert mgr.kokoro is None
    assert mgr.gemini is None
