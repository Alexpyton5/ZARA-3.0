"""Test local wake word detection using Vosk gate when activated via api_keys.json."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from core.ipc_handlers import IPCHandler


def test_wake_word_local_disabled_by_default():
    """By default, wake word mode is disabled (transcription-based)."""
    cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")
    assert cfg.wake_word_enabled is False


def test_wake_word_local_enabled_via_api_keys(tmp_path, monkeypatch):
    """Setting \"wake_word_mode\": \"local\" in api_keys.json enables the local Vosk gate."""
    api_keys_file = tmp_path / "api_keys.json"
    api_keys_file.write_text(json.dumps({"wake_word_mode": "local"}), encoding="utf-8")
    monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)

    cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")
    assert cfg.wake_word_enabled is True


def test_wake_word_local_detection_via_mock_vosk(tmp_path, monkeypatch):
    """
    Simulate audio with the word \"zara\" and verify detection by the mocked Vosk gate.
    We mock vosk.Model and vosk.KaldiRecognizer to avoid needing the actual model files.

    The recognizer is mocked, and an isolated placeholder model directory
    satisfies the gate's path-existence check without requiring owner assets.
    """
    # Arrange: enable local wake word mode
    api_keys_file = tmp_path / "api_keys.json"
    api_keys_file.write_text(json.dumps({"wake_word_mode": "local"}), encoding="utf-8")
    monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)

    # `_ensure_wake_detector` checks the model path before constructing the
    # mocked Vosk model. Keep this unit test independent of local model assets.
    isolated_home = tmp_path / "zara-home"
    (isolated_home / "models" / "vosk" / "vosk-model-small-pt-0.3").mkdir(parents=True)
    monkeypatch.setattr("core.paths.user_data_dir", lambda: isolated_home)

    # Mock Vosk imports and classes
    mock_vosk = MagicMock()
    mock_model = MagicMock()
    mock_recognizer = MagicMock()
    mock_vosk.Model.return_value = mock_model
    mock_vosk.KaldiRecognizer.return_value = mock_recognizer

    # Configure the recognizer to return a partial result containing "zara"
    mock_recognizer.PartialResult.return_value = '{"partial": "zara"}'

    with patch.dict("sys.modules", {"vosk": mock_vosk}):
        # Import inside the patch to ensure our mock is used
        from core.gemini_live_voice import GeminiLiveVoice

        # Build the config (will have wake_word_enabled=True)
        cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")
        # Create GeminiLiveVoice instance (we don't need a real loop or callbacks for this test)
        voice = GeminiLiveVoice(config=cfg)

        # Act: trigger the lazy initialization of the wake detector
        voice._ensure_wake_detector()

        # Assert: the Vosk model and recognizer were created with expected parameters
        mock_vosk.Model.assert_called_once()
        mock_vosk.KaldiRecognizer.assert_called_once_with(mock_model, cfg.input_sample_rate)
        # The grammar should be set to the wake words list
        mock_recognizer.SetGrammar.assert_called_once_with(json.dumps(list(cfg.wake_words)))

        # Now test the detection: feed some dummy audio bytes
        # The _check_wake_word method uses a rolling buffer and calls AcceptWaveform and PartialResult
        # We'll call it twice: first to build up the buffer, second to trigger the partial result
        # Since we mocked PartialResult to always return {"partial": "zara"}, any call should work.
        result = voice._check_wake_word(b"\x00\x00" * 100)  # dummy audio data
        assert result is True

        # Also test that when the wake word is not in the partial result, it returns False
        mock_recognizer.PartialResult.return_value = '{"partial": "outra palavra"}'
        result = voice._check_wake_word(b"\x00\x00" * 100)
        assert result is False


def test_wake_word_local_not_activated_when_mode_not_local(tmp_path, monkeypatch):
    """If wake_word_mode is not \"local\", the gate should remain disabled."""
    api_keys_file = tmp_path / "api_keys.json"
    api_keys_file.write_text(json.dumps({"wake_word_mode": "server"}), encoding="utf-8")
    monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)

    cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")
    assert cfg.wake_word_enabled is False

    # Even if we try to create the voice, the gate should not be initialized
    from core.gemini_live_voice import GeminiLiveVoice
    voice = GeminiLiveVoice(config=cfg)
    voice._ensure_wake_detector()
    # The wake detector should remain None because wake_word_enabled is False
    assert voice._wake_detector is None


def test_wake_word_local_handles_invalid_json_gracefully(tmp_path, monkeypatch):
    """If api_keys.json contains invalid JSON, we fall back to default (disabled)."""
    api_keys_file = tmp_path / "api_keys.json"
    api_keys_file.write_text("not json", encoding="utf-8")
    monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)

    cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")
    assert cfg.wake_word_enabled is False  # default


def test_wake_word_local_handles_missing_key_gracefully(tmp_path, monkeypatch):
    """If wake_word_mode key is missing, we fall back to default (disabled)."""
    api_keys_file = tmp_path / "api_keys.json"
    api_keys_file.write_text(json.dumps({"other_key": "value"}), encoding="utf-8")
    monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)

    cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")
    assert cfg.wake_word_enabled is False  # default
