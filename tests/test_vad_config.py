"""Test VAD configuration loading from api_keys.json and application to Gemini Live session."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

from core.gemini_live_voice import GeminiLiveVoice, GeminiLiveVoiceConfig
from core.ipc_handlers import IPCHandler


def test_vad_config_defaults():
    """Default values are set correctly."""
    cfg = GeminiLiveVoiceConfig(api_key="test")
    assert cfg.vad_silencio_ms == 300
    assert cfg.vad_padding_ms == 100
    assert cfg.vad_fim_sensivel is True


def test_vad_config_reads_from_api_keys_json(tmp_path, monkeypatch):
    """Values are read from api_keys.json and applied."""
    # Set up temporary config dir
    config_data = {
        "vad_silencio_ms": 200,
        "vad_padding_ms": 150,
        "vad_fim_sensivel": False,
        "audio_transport": "local",
    }
    api_keys_file = tmp_path / "api_keys.json"
    api_keys_file.write_text(json.dumps(config_data), encoding="utf-8")
    monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)

    # Build config via IPCHandler (which reads the file)
    cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")

    assert cfg.vad_silencio_ms == 200
    assert cfg.vad_padding_ms == 150
    assert cfg.vad_fim_sensivel is False
    assert cfg.audio_transport == "local"


def test_vad_config_silencio_ms_clamped(tmp_path, monkeypatch):
    """vad_silencio_ms is clamped to [150, 2000] range."""
    for value, expected in [
        (0, 150),      # below min -> clamped to min
        (100, 150),    # below min -> clamped
        (150, 150),    # at min
        (300, 300),    # within range
        (1000, 1000),  # within range
        (2000, 2000),  # at max
        (2500, 2000),  # above max -> clamped
        (9999, 2000),  # way above -> clamped
    ]:
        api_keys_file = tmp_path / "api_keys.json"
        api_keys_file.write_text(json.dumps({"vad_silencio_ms": value}), encoding="utf-8")
        monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)
        cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")
        assert cfg.vad_silencio_ms == expected, f"Failed for input {value}"


def test_vad_config_padding_ms_clamped(tmp_path, monkeypatch):
    """vad_padding_ms is clamped to [0, 2000] range."""
    for value, expected in [
        (-5, 0),       # below min -> clamped to min
        (0, 0),        # at min
        (50, 50),      # within range
        (100, 100),    # within range
        (150, 150),    # within range
        (2000, 2000),  # at max
        (2500, 2000),  # above max -> clamped
        (9999, 2000),  # way above -> clamped
    ]:
        api_keys_file = tmp_path / "api_keys.json"
        api_keys_file.write_text(json.dumps({"vad_padding_ms": value}), encoding="utf-8")
        monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)
        cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")
        assert cfg.vad_padding_ms == expected, f"Failed for input {value}"


def test_vad_config_fim_sensivel_bool(tmp_path, monkeypatch):
    """vad_fim_sensivel is read as boolean."""
    test_cases = [
        (True, True),
        (False, False),
        ("true", True),
        ("false", False),
        ("True", True),   # uppercase
        ("False", False), # uppercase
        (1, True),        # int 1
        (0, False),       # int 0
    ]
    for value, expected in test_cases:
        api_keys_file = tmp_path / "api_keys.json"
        api_keys_file.write_text(json.dumps({"vad_fim_sensivel": value}), encoding="utf-8")
        monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)
        cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")
        assert cfg.vad_fim_sensivel == expected, f"Failed for input {value}"


def test_vad_config_missing_keys_use_defaults(tmp_path, monkeypatch):
    """Missing keys fall back to defaults."""
    api_keys_file = tmp_path / "api_keys.json"
    api_keys_file.write_text(json.dumps({}), encoding="utf-8")  # empty object
    monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)
    cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")
    # Currently the IPCHandler sets defaults: silencio_ms=450, padding_ms=100, fim_sensivel=True, transporte="renderer"
    assert cfg.vad_silencio_ms == 450  # current implementation default
    assert cfg.vad_padding_ms == 100   # default we set
    assert cfg.vad_fim_sensivel is True  # default we set
    assert cfg.audio_transport == "renderer"  # default


def test_vad_config_audio_transport_reads_from_api_keys_json(tmp_path, monkeypatch):
    """audio_transport is read from api_keys.json."""
    api_keys_file = tmp_path / "api_keys.json"
    api_keys_file.write_text(json.dumps({"audio_transport": "local"}), encoding="utf-8")
    monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)
    cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")
    assert cfg.audio_transport == "local"

    api_keys_file.write_text(json.dumps({"audio_transport": "renderer"}), encoding="utf-8")
    cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")
    assert cfg.audio_transport == "renderer"


def test_vad_config_audio_transport_invalid_values_safe_fallback(tmp_path, monkeypatch):
    """Invalid audio_transport values fall back to default (renderer)."""
    api_keys_file = tmp_path / "api_keys.json"
    # Invalid value
    api_keys_file.write_text(json.dumps({"audio_transport": "invalid"}), encoding="utf-8")
    monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)
    cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")
    assert cfg.audio_transport == "renderer"  # fallback to default
    # Empty string
    api_keys_file.write_text(json.dumps({"audio_transport": ""}), encoding="utf-8")
    cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")
    assert cfg.audio_transport == "renderer"  # fallback to default


def test_vad_config_invalid_values_safe_fallback(tmp_path, monkeypatch):
    """Invalid values fall back to defaults."""
    # Test invalid silencio_ms (non-numeric string)
    api_keys_file = tmp_path / "api_keys.json"
    api_keys_file.write_text(json.dumps({"vad_silencio_ms": "invalid"}), encoding="utf-8")
    monkeypatch.setattr("core.paths.config_dir", lambda: tmp_path)
    cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")
    assert cfg.vad_silencio_ms == 450  # fallback to default (450 from initialization)

    # Test invalid padding_ms
    api_keys_file.write_text(json.dumps({"vad_padding_ms": "invalid"}), encoding="utf-8")
    cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")
    assert cfg.vad_padding_ms == 100  # fallback to default

    # Test invalid fim_sensivel
    api_keys_file.write_text(json.dumps({"vad_fim_sensivel": "invalid"}), encoding="utf-8")
    cfg = IPCHandler.__new__(IPCHandler)._build_gemini_live_config("test-key")
    assert cfg.vad_fim_sensivel is True  # fallback to default


def test_connect_session_passes_vad_values_to_supported_live_sdk():
    """The three persisted VAD values configure Gemini's activity detection."""
    connect = Mock(return_value=object())
    client = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect)))

    class _LiveConnectConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _RealtimeInputConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _AutomaticActivityDetection:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    types = SimpleNamespace(
        LiveConnectConfig=_LiveConnectConfig,
        RealtimeInputConfig=_RealtimeInputConfig,
        AutomaticActivityDetection=_AutomaticActivityDetection,
        EndSensitivity=SimpleNamespace(
            END_SENSITIVITY_HIGH="high",
            END_SENSITIVITY_LOW="low",
        ),
    )
    voice = GeminiLiveVoice(
        GeminiLiveVoiceConfig(
            api_key="test",
            vad_silencio_ms=420,
            vad_padding_ms=160,
            vad_fim_sensivel=False,
        )
    )

    voice._connect_session(SimpleNamespace(Client=Mock(return_value=client)), types)

    config = connect.call_args.kwargs["config"]
    vad = config.kwargs["realtime_input_config"].kwargs["automatic_activity_detection"]
    assert vad.kwargs == {
        "silence_duration_ms": 420,
        "prefix_padding_ms": 160,
        "end_of_speech_sensitivity": "low",
    }


def test_connect_session_omits_vad_for_old_live_sdk_without_activity_types():
    """An SDK without activity types still starts a baseline live connection."""
    connect = Mock(return_value=object())
    client = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect)))

    class _OldLiveConnectConfig:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    voice = GeminiLiveVoice(GeminiLiveVoiceConfig(api_key="test"))
    voice._connect_session(
        SimpleNamespace(Client=Mock(return_value=client)),
        SimpleNamespace(LiveConnectConfig=_OldLiveConnectConfig),
    )

    config = connect.call_args.kwargs["config"]
    assert "realtime_input_config" not in config.kwargs


def test_connect_session_builds_vad_with_installed_google_genai_types():
    """The installed SDK accepts the VAD object that reaches live.connect."""
    from google.genai import types

    connect = Mock(return_value=object())
    client = SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=connect)))
    voice = GeminiLiveVoice(
        GeminiLiveVoiceConfig(
            api_key="test",
            vad_silencio_ms=420,
            vad_padding_ms=160,
            vad_fim_sensivel=False,
        )
    )

    voice._connect_session(SimpleNamespace(Client=Mock(return_value=client)), types)

    activity = (
        connect.call_args.kwargs["config"]
        .realtime_input_config.automatic_activity_detection
    )
    assert activity.silence_duration_ms == 420
    assert activity.prefix_padding_ms == 160
    assert activity.end_of_speech_sensitivity == types.EndSensitivity.END_SENSITIVITY_LOW
