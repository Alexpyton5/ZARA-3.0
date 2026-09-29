"""Testes do diagnóstico da cadeia de voz por estágios.

core.voice_diagnostics — item 27 do PESQUISA-CONCORRENTES.md.
Todos herméticos: sem microfone, sem rede, sem hardware real.
"""

import json

import pytest

from core import voice_diagnostics as vd


# --- mapa de estágios --------------------------------------------------------

def test_stage_map_covers_full_chain():
    names = [s.name for s in vd.VOICE_STAGES]
    assert names == [
        "backend", "ipc-wiring", "mic", "vad", "stt", "llm", "tts", "speakers",
    ]
    for stage in vd.VOICE_STAGES:
        assert stage.title, f"{stage.name} sem título"
        assert stage.first_check, f"{stage.name} sem 'primeiro check'"
        assert stage.sources, f"{stage.name} sem arquivo-fonte"


def test_stage_names_unique():
    names = [s.name for s in vd.VOICE_STAGES]
    assert len(names) == len(set(names))


# --- hierarquia de exceções ---------------------------------------------------

@pytest.mark.parametrize(
    "exc_cls, expected_stage",
    [
        (vd.VoicePipelineError, "pipeline"),
        (vd.AudioError, "mic"),
        (vd.VADError, "vad"),
        (vd.STTError, "stt"),
        (vd.LLMError, "llm"),
        (vd.TTSError, "tts"),
    ],
)
def test_stage_of_maps_exception_to_stage(exc_cls, expected_stage):
    assert vd.stage_of(exc_cls("x")) == expected_stage


def test_stage_of_unknown_exception_is_pipeline():
    assert vd.stage_of(RuntimeError("boom")) == "pipeline"


def test_hierarchy_inherits_base():
    for cls in (vd.AudioError, vd.VADError, vd.STTError, vd.LLMError, vd.TTSError):
        assert issubclass(cls, vd.VoicePipelineError)


@pytest.mark.parametrize(
    "code, expected",
    [
        ("STT_MODEL_NOT_CONFIGURED: sem modelo", vd.STTError),
        ("STT_BACKEND_NOT_CONFIGURED: sem vosk", vd.STTError),
        ("AUDIO_INPUT_FAILED: xyz permanent=True", vd.AudioError),
        ("SOMETHING_ELSE", vd.VoicePipelineError),
    ],
)
def test_classify_code(code, expected):
    assert vd.classify_code(code) is expected


# --- sanitizador: nunca vaza segredo ------------------------------------------

def test_sanitize_redacts_secret_keys_and_values():
    report = {
        "gemini_api_key": "AIzaSy-FAKEKEY1234567890",
        "nested": {"NVIDIA_API_KEY": "nvapi-fake-key-1234567890"},
        "note": "chave sk-ant-fake-key-1234567890 no texto",
        "stage": "tts",
    }
    clean = vd.sanitize(report)
    dumped = json.dumps(clean)
    assert "AIzaSy-FAKEKEY1234567890" not in dumped
    assert "nvapi-fake-key-1234567890" not in dumped
    assert "sk-ant-fake-key-1234567890" not in dumped
    assert "[REDACTED]" in dumped
    assert clean["stage"] == "tts"  # dado inocente sobrevive


def test_sanitize_keeps_structure():
    report = {"stages": [{"stage": "mic", "status": "ok"}], "ok": True}
    assert vd.sanitize(report) == report


# --- wiring IPC (Manual §8) ----------------------------------------------------

def test_check_ipc_wiring_detects_registered(tmp_path):
    ipc = tmp_path / "ipc_handlers.py"
    ipc.write_text(
        'handler_map = {\n'
        '    "zoe-voice-speak": self.handle_zoe_voice_speak,\n'
        '}\n'
        'def handle_zoe_voice_speak(self): ...\n',
        encoding="utf-8",
    )
    result = vd.check_ipc_wiring(ipc)
    assert result["messages"]["zoe-voice-speak"]["status"] == "ok"


def test_check_ipc_wiring_warns_on_handler_without_route(tmp_path):
    # O caso real do Manual §8.2: handler existe, registro não.
    ipc = tmp_path / "ipc_handlers.py"
    ipc.write_text(
        "def handle_zoe_voice_speak(self): ...\n",
        encoding="utf-8",
    )
    result = vd.check_ipc_wiring(ipc)
    entry = result["messages"]["zoe-voice-speak"]
    assert entry["status"] == "warn"
    assert "Unknown message type" in entry["detail"]


def test_check_ipc_wiring_errors_on_missing(tmp_path):
    ipc = tmp_path / "ipc_handlers.py"
    ipc.write_text("x = 1\n", encoding="utf-8")
    result = vd.check_ipc_wiring(ipc)
    assert result["messages"]["supercerebro-toggle"]["status"] == "error"
    assert result["status"] == "error"


# --- cascata TTS reusa a política oficial --------------------------------------

def test_tts_cascade_uses_official_policy():
    engines = {
        "gemini_key_set": True, "omnivoice_module": True,
        "edge_tts": True, "kokoro_onnx": True,
    }
    result = vd.check_tts_cascade(engines)
    assert result["order"] == ["kore", "omnivoice", "edge", "kokoro"]
    assert result["status"] == "ok"


def test_tts_cascade_empty_is_error():
    result = vd.check_tts_cascade({
        "gemini_key_set": False, "omnivoice_module": False,
        "edge_tts": False, "kokoro_onnx": False,
    })
    assert result["status"] == "error"
    assert result["order"] == []


# --- diagnose() orquestra e sanitiza -------------------------------------------

def _ok(detail="ok"):
    return {"status": "ok", "detail": detail}


def test_diagnose_all_ok_with_injected_checks():
    report = vd.diagnose(
        engines={"gemini_key_set": True},
        wiring={"status": "ok", "messages": {
            "zoe-voice-speak": {"status": "ok", "detail": "registrado"},
        }},
        backend=_ok(), stt=_ok(), vad=_ok(), llm=_ok(),
        tts=_ok(), audio=_ok(),
    )
    assert report["ok"] is True
    assert [s["stage"] for s in report["stages"]] == [
        "backend", "ipc-wiring", "mic", "vad", "stt", "llm", "tts", "speakers",
    ]
    for entry in report["stages"]:
        assert entry["first_check"], f'{entry["stage"]} sem first_check'
    wiring_entry = next(s for s in report["stages"] if s["stage"] == "ipc-wiring")
    assert "zoe-voice-speak=ok" in wiring_entry["detail"]


def test_diagnose_flags_error_stage():
    report = vd.diagnose(
        engines={}, wiring={"status": "ok", "messages": {}},
        backend=_ok(), stt=_ok(), vad=_ok(), llm=_ok(),
        tts={"status": "error", "detail": "muda"}, audio=_ok(),
    )
    assert report["ok"] is False
    tts = next(s for s in report["stages"] if s["stage"] == "tts")
    assert tts["status"] == "error"


def test_diagnose_never_leaks_env_values(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSy-LEAK-TEST-1234567890")
    monkeypatch.setenv("NVIDIA_API_KEY", "nvapi-LEAK-TEST-1234567890")
    report = vd.diagnose(
        wiring={"status": "ok", "messages": {}},
        backend=_ok(), stt=_ok(), vad=_ok(), llm=_ok(),
        tts=_ok(), audio=_ok(),
    )
    dumped = json.dumps(report)
    assert "LEAK-TEST" not in dumped


# --- backend check --------------------------------------------------------------

def test_check_backend_detects_running():
    result = vd.check_backend(["zara-backend.exe", "explorer.exe"])
    assert result["status"] == "ok"
    assert result["running"] is True


def test_check_backend_warns_when_absent():
    result = vd.check_backend(["explorer.exe"])
    assert result["status"] == "warn"
    assert result["running"] is False


# --- CLI ------------------------------------------------------------------------

def test_main_exit_zero_when_healthy(monkeypatch, capsys):
    monkeypatch.setattr(vd, "diagnose", lambda **kw: {"ok": True, "stages": []})
    assert vd.main([]) == 0
    json.loads(capsys.readouterr().out)  # saída é JSON válido


def test_main_exit_one_on_error(monkeypatch, capsys):
    monkeypatch.setattr(vd, "diagnose", lambda **kw: {"ok": False, "stages": []})
    assert vd.main([]) == 1
    json.loads(capsys.readouterr().out)
