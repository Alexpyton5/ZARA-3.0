"""Diagnóstico da cadeia de voz por estágios (Mic -> VAD -> STT -> LLM -> TTS -> Speakers).

Ideia roubada do voice_kusaka (item 27 de PESQUISA-CONCORRENTES.md): quando a
voz falha, o diagnóstico diz ONDE quebrou em vez de "não funciona".

Somente leitura: não abre microfone, não sintetiza áudio, não faz rede.
O relatório é sanitizado — nunca contém chave, URL, áudio ou transcript.

Uso (na raiz do projeto, no PC do Alex):
    python -m core.voice_diagnostics
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


# ---------------------------------------------------------------------------
# Hierarquia de exceções: cada erro carrega o estágio onde nasceu (item 27).
# Exceção -> Estágio -> "primeiro check" (tabela VOICE_STAGES abaixo).
# ---------------------------------------------------------------------------

class VoicePipelineError(Exception):
    """Base; todo erro da cadeia de voz carrega o estágio onde nasceu."""

    stage = "pipeline"


class AudioError(VoicePipelineError):
    """Microfone / alto-falante / captura de áudio."""

    stage = "mic"


class VADError(VoicePipelineError):
    """Detecção de atividade de voz."""

    stage = "vad"


class STTError(VoicePipelineError):
    """Fala -> texto."""

    stage = "stt"


class LLMError(VoicePipelineError):
    """Cérebro / provedor de linguagem."""

    stage = "llm"


class TTSError(VoicePipelineError):
    """Texto -> fala."""

    stage = "tts"


def stage_of(exc: BaseException) -> str:
    """Devolve o estágio dono da exceção ('pipeline' se não for da cadeia)."""
    return str(getattr(exc, "stage", "pipeline") or "pipeline")


# Códigos conhecidos do código atual -> classe da hierarquia.
_KNOWN_CODES: tuple[tuple[str, type[VoicePipelineError]], ...] = (
    ("STT_MODEL_NOT_CONFIGURED", STTError),
    ("STT_BACKEND_NOT_CONFIGURED", STTError),
    ("AUDIO_INPUT_FAILED", AudioError),
)


def classify_code(code: str) -> type[VoicePipelineError]:
    """Classifica um código de erro conhecido (ex.: 'STT_MODEL_NOT_CONFIGURED')."""
    for prefix, cls in _KNOWN_CODES:
        if str(code).startswith(prefix):
            return cls
    return VoicePipelineError


# ---------------------------------------------------------------------------
# Mapa de estágios: nome, título, "primeiro check" (linguagem simples) e
# arquivos-fonte de cada estágio (item 27: logger + arquivo-fonte + config).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Stage:
    name: str
    title: str
    first_check: str
    sources: tuple[str, ...]


VOICE_STAGES: tuple[Stage, ...] = (
    Stage(
        "backend",
        "Backend ligado",
        "O app está aberto? Sem o backend rodando (zara-backend.exe), voz e "
        "use-computer ficam mudos — foi o que aconteceu em 29/09 ~05:25.",
        ("main.py", "frontend/src/main.ts"),
    ),
    Stage(
        "ipc-wiring",
        "Fiação botão -> backend",
        "A mensagem está registrada no handler_map de core/ipc_handlers.py? "
        "Tipo sem registro cai em 'Unknown message type' e o pedido trava "
        "até o timeout (Manual da ZARA, seção 8).",
        ("core/ipc_handlers.py", "frontend/src/preload.ts", "frontend/src/main.ts"),
    ),
    Stage(
        "mic",
        "Microfone",
        "O microfone está plugado e escolhido como entrada padrão do Windows?",
        ("core/voice_stt.py",),
    ),
    Stage(
        "vad",
        "Detecção de voz (VAD)",
        "Fala sendo ignorada ou barulho virando 'fala'? Checar vad_threshold "
        "e vad_silence_chunks em core/voice_stt.py (VoiceConfig).",
        ("core/voice_stt.py",),
    ),
    Stage(
        "stt",
        "Fala -> texto (STT)",
        "O modelo Vosk pt-BR está instalado na pasta de dados do usuário "
        "(models/vosk)? Sem modelo, o STT levanta STT_MODEL_NOT_CONFIGURED.",
        ("core/voice_stt.py",),
    ),
    Stage(
        "llm",
        "Cérebro (LLM)",
        "Há provedor configurado (chave) e com cota? Sem cérebro, a fala não "
        "vira resposta.",
        ("core/lab_v1/providers/",),
    ),
    Stage(
        "tts",
        "Texto -> fala (TTS)",
        "Qual motor da cascata está ativo? Ordem oficial: kore -> edge -> kokoro (core/voice_engine_policy.py). A ZARA nunca "
        "pode ficar muda: se um motor falha, o próximo assume.",
        ("core/voice_tts.py", "core/voice_engine_policy.py", "core/voice_fallback.py"),
    ),
    Stage(
        "speakers",
        "Alto-falantes",
        "O dispositivo de saída está certo e com volume? O áudio chega à "
        "tela como evento voice-output-audio (PCM).",
        ("core/voice_tts.py",),
    ),
)

_STAGE_BY_NAME = {s.name: s for s in VOICE_STAGES}

# Mensagens IPC que a cadeia de voz precisa ter registradas (Manual §8).
_WIRED_MESSAGES = ("zoe-voice-speak", "supercerebro-toggle", "supercerebro-status")


# ---------------------------------------------------------------------------
# Sanitizador: o relatório nunca vaza segredo (item 28: diagnóstico
# sanitizado — sem credenciais, URLs, áudio ou transcripts).
# ---------------------------------------------------------------------------

_REDACT_KEY_PARTS = (
    "key", "token", "secret", "password", "passwd", "auth",
    "credential", "bearer", "session",
)

_VALUE_PATTERNS = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"nvapi-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{8,}"),
    re.compile(r"(?i)\b(api[_-]?key|access[_-]?key)\b\s*[:=]\s*\S+"),
)


def _redact_string(value: str) -> str:
    redacted = value
    for pattern in _VALUE_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def _looks_secret_key(key: str) -> bool:
    lowered = str(key).casefold()
    return any(part in lowered for part in _REDACT_KEY_PARTS)


def sanitize(node):
    """Devolve cópia do relatório com segredos redigidos. Nunca vaza chave."""
    if isinstance(node, dict):
        return {
            key: ("[REDACTED]" if _looks_secret_key(key) else sanitize(value))
            for key, value in node.items()
        }
    if isinstance(node, (list, tuple)):
        return [sanitize(item) for item in node]
    if isinstance(node, str):
        return _redact_string(node)
    return node


# ---------------------------------------------------------------------------
# Checks por estágio (todos somente leitura).
# ---------------------------------------------------------------------------

def _installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def check_engines() -> dict:
    """Disponibilidade dos motores (booleans — nunca valores de chave)."""
    return {
        "vosk": _installed("vosk"),
        "sounddevice": _installed("sounddevice"),
        "porcupine": _installed("pvporcupine"),
        "edge_tts": _installed("edge_tts"),
        "kokoro_onnx": _installed("kokoro_onnx"),
        # Chaves: só "existe / não existe", o valor nunca entra no relatório.
        "gemini_key_set": bool(os.environ.get("GEMINI_API_KEY")),
        "anthropic_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "nvidia_key_set": bool(os.environ.get("NVIDIA_API_KEY")),
    }


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def check_ipc_wiring(ipc_path: Path | None = None) -> dict:
    """Confere se as mensagens da voz estão registradas no handler_map.

    Codifica em check vivo os achados do Manual §8.1/§8.2: handler existe mas
    sem registro = 'warn'; mensagem registrada = 'ok'; nada = 'error'.
    """
    path = ipc_path or (_project_root() / "core" / "ipc_handlers.py")
    result: dict = {"file": str(path), "messages": {}}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        result["status"] = "error"
        result["detail"] = f"não consegui ler {path}: {exc}"
        return result

    code_lines = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped.startswith("#"):
            code_lines.append(line.split("#")[0] if "#" in line else line)
    code = "\n".join(code_lines)

    worst = "ok"
    for message in _WIRED_MESSAGES:
        registered = re.search(
            r"""['"]""" + re.escape(message) + r"""['"]\s*:""", code
        ) is not None
        handler_name = "handle_" + message.replace("-", "_")
        handler_exists = f"def {handler_name}" in code
        if registered:
            status, detail = "ok", f"'{message}' registrado no handler_map"
        elif handler_exists:
            status = "warn"
            detail = (
                f"'{message}' tem {handler_name}() mas NÃO está no handler_map "
                "(Manual §8: cai em 'Unknown message type')"
            )
        else:
            status = "error"
            detail = f"'{message}' sem handler e sem registro"
        result["messages"][message] = {"status": status, "detail": detail}
        if status == "error":
            worst = "error"
        elif status == "warn" and worst == "ok":
            worst = "warn"
    result["status"] = worst
    return result


def check_backend(process_names: "list[str] | None" = None) -> dict:
    """Backend empacotado rodando? (zara-backend.exe — TOOLS.md)."""
    names: list[str]
    if process_names is None:
        names = []
        if sys.platform == "win32":
            try:
                out = subprocess.run(
                    ["tasklist", "/FI", "IMAGENAME eq zara-backend.exe", "/FO", "CSV"],
                    capture_output=True, text=True, timeout=15,
                )
                for line in out.stdout.splitlines()[1:]:
                    first = line.split('","')[0].strip('"').casefold()
                    if first:
                        names.append(first)
            except (OSError, subprocess.SubprocessError):
                pass
    else:
        names = [n.casefold() for n in process_names]

    running = "zara-backend.exe" in names
    return {
        "status": "ok" if running else "warn",
        "running": running,
        "detail": (
            "zara-backend.exe rodando"
            if running
            else "zara-backend.exe não encontrado (em modo dev, confira o "
                 "sidecar pela janela; sem backend, voz e use-computer mudam)"
        ),
    }


def check_stt_model() -> dict:
    """Modelo Vosk instalado? (nunca baixa sozinho — regra do voice_stt)."""
    try:
        from core.paths import user_data_dir  # lazy: só leitura de caminho
        model_dir = user_data_dir() / "models" / "vosk"
        found = [p.name for p in model_dir.iterdir()] if model_dir.is_dir() else []
    except Exception as exc:  # noqa: BLE001 - diagnóstico não pode quebrar
        return {"status": "warn", "detail": f"não consegui checar modelos: {exc}"}
    has_pt = any("pt" in name for name in found)
    if has_pt:
        return {"status": "ok", "detail": f"modelo pt-BR presente ({found[0]})"}
    if found:
        return {"status": "warn", "detail": f"só há modelo(s) {found} — sem pt-BR"}
    return {
        "status": "warn",
        "detail": "nenhum modelo Vosk instalado (STT levanta "
                 "STT_MODEL_NOT_CONFIGURED; a ZARA nunca baixa sozinha)",
    }


def check_vad_config() -> dict:
    """Sanidade da config do VAD (só leitura dos defaults)."""
    try:
        from core.voice_stt import VoiceConfig  # lazy: imports opcionais ok
        cfg = VoiceConfig()
        problems = []
        if not (0.0 < cfg.vad_threshold < 1.0):
            problems.append(f"vad_threshold={cfg.vad_threshold} fora de (0,1)")
        if cfg.vad_silence_chunks <= 0:
            problems.append("vad_silence_chunks<=0 (nunca detecta fim de fala)")
        if problems:
            return {"status": "error", "detail": "; ".join(problems)}
        return {
            "status": "ok",
            "detail": f"vad_threshold={cfg.vad_threshold}, "
                      f"vad_silence_chunks={cfg.vad_silence_chunks}",
        }
    except Exception as exc:  # noqa: BLE001 - diagnóstico não pode quebrar
        return {"status": "warn", "detail": f"não consegui ler VoiceConfig: {exc}"}


def check_tts_cascade(engines: dict | None = None) -> dict:
    """Ordem real da cascata usando a política oficial (voice_engine_policy)."""
    eng = engines if engines is not None else check_engines()
    try:
        from core.voice_engine_policy import voice_output_order  # leve, sem deps
        order = voice_output_order(
            "kore",
            kore_ready=bool(eng.get("gemini_key_set")),
            edge_ready=bool(eng.get("edge_tts")),
            kokoro_ready=bool(eng.get("kokoro_onnx")),
        )
    except Exception as exc:  # noqa: BLE001
        return {"status": "error", "detail": f"política de voz ilegível: {exc}"}
    if not order:
        return {
            "status": "error",
            "order": [],
            "detail": "nenhum motor de TTS disponível — a ZARA ficaria muda",
        }
    return {
        "status": "ok" if len(order) > 1 else "warn",
        "order": list(order),
        "detail": f"cascata ativa: {' -> '.join(order)}",
    }


def check_audio_devices() -> dict:
    """Conta dispositivos de entrada/saída (somente leitura)."""
    if not _installed("sounddevice"):
        return {"status": "warn", "detail": "sounddevice não instalado"}
    try:
        import sounddevice as sd  # type: ignore
        devices = sd.query_devices()
        inputs = sum(1 for d in devices if d.get("max_input_channels", 0) > 0)
        outputs = sum(1 for d in devices if d.get("max_output_channels", 0) > 0)
    except Exception as exc:  # noqa: BLE001 - PortAudio pode estar quebrado
        return {"status": "error", "detail": f"sounddevice instalado mas falhou: {exc}"}
    status = "ok" if inputs and outputs else "warn"
    return {
        "status": status,
        "inputs": inputs,
        "outputs": outputs,
        "detail": f"{inputs} entrada(s), {outputs} saída(s)",
    }


def check_llm(engines: dict | None = None) -> dict:
    """Algum provedor de cérebro configurado? (só booleans, sem valores)."""
    eng = engines if engines is not None else check_engines()
    providers = [
        name for name, flag in (
            ("gemini", eng.get("gemini_key_set")),
            ("anthropic", eng.get("anthropic_key_set")),
            ("nvidia", eng.get("nvidia_key_set")),
        ) if flag
    ]
    if providers:
        return {"status": "ok", "detail": f"provedor(es): {', '.join(providers)}"}
    return {
        "status": "warn",
        "detail": "nenhuma chave de provedor no ambiente (voz local ainda "
                 "fala, mas sem cérebro não há resposta)",
    }


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------

def _stage_entry(name: str, check: dict) -> dict:
    stage = _STAGE_BY_NAME[name]
    detail = check.get("detail", "")
    extra = check.get("messages")
    if isinstance(extra, dict) and extra:
        detail = "; ".join(
            f"{message}={info.get('status')}" for message, info in extra.items()
        )
    return {
        "stage": name,
        "title": stage.title,
        "status": check.get("status", "warn"),
        "detail": detail,
        "first_check": stage.first_check,
        "sources": list(stage.sources),
    }


def diagnose(
    *,
    engines: dict | None = None,
    wiring: dict | None = None,
    backend: dict | None = None,
    stt: dict | None = None,
    vad: dict | None = None,
    llm: dict | None = None,
    tts: dict | None = None,
    audio: dict | None = None,
) -> dict:
    """Roda todos os checks e devolve o relatório (já sanitizado)."""
    eng = engines if engines is not None else check_engines()
    entries = [
        _stage_entry("backend", backend or check_backend()),
        _stage_entry("ipc-wiring", wiring or check_ipc_wiring()),
        _stage_entry("mic", audio or check_audio_devices()),
        _stage_entry("vad", vad or check_vad_config()),
        _stage_entry("stt", stt or check_stt_model()),
        _stage_entry("llm", llm or check_llm(eng)),
        _stage_entry("tts", tts or check_tts_cascade(eng)),
        _stage_entry("speakers", audio or check_audio_devices()),
    ]
    report = {
        "ok": all(e["status"] != "error" for e in entries),
        "stages": entries,
        "generated_by": "core.voice_diagnostics",
    }
    return sanitize(report)


def main(argv: "list[str] | None" = None) -> int:
    """CLI: imprime o relatório em JSON. Exit 1 se algum estágio em erro."""
    report = diagnose()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
