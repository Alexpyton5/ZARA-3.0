"""Install the optional free OmniVoice runtime outside the app/repository."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


MODEL_ID = "k2-fsa/OmniVoice"
MIN_FREE_BYTES = 8 * 1024**3


def _safe_environment(data_root: Path) -> dict[str, str]:
    allowed = (
        "SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "USERPROFILE",
        "APPDATA", "LOCALAPPDATA",
    )
    result = {key: os.environ[key] for key in allowed if os.environ.get(key)}
    result.update({
        "PYTHONIOENCODING": "utf-8",
        "HF_HOME": str(data_root / "models" / "omnivoice" / "hub"),
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "TOKENIZERS_PARALLELISM": "false",
    })
    return result


def _run(command: list[str], environment: dict[str, str], timeout: int = 1800) -> None:
    subprocess.run(command, check=True, env=environment, timeout=timeout)


def _smoke(python: Path, environment: dict[str, str]) -> str:
    script = (
        "import torch; from omnivoice import OmniVoice; "
        "device='cuda:0' if torch.cuda.is_available() else 'cpu'; "
        "dtype=torch.float16 if device.startswith('cuda') else torch.float32; "
        "model=OmniVoice.from_pretrained('k2-fsa/OmniVoice', device_map=device, dtype=dtype); "
        "model.eval(); audio=model.generate(text='Teste local da voz da Zara.', "
        "language_id='pt', num_step=8); "
        "assert audio and len(audio[0]) > 0; print('OMNIVOICE_LOCAL_SMOKE_OK')"
    )
    result = subprocess.run(
        [str(python), "-c", script], check=True, env=environment,
        timeout=900, capture_output=True, text=True, encoding="utf-8",
        errors="replace",
    )
    if "OMNIVOICE_LOCAL_SMOKE_OK" not in result.stdout:
        raise RuntimeError("OmniVoice smoke não confirmou o áudio local.")
    return "cuda" if "device='cuda:0'" in script else "cpu"


def install() -> Path:
    if os.name != "nt":
        raise RuntimeError("Este instalador de runtime está delimitado a Windows.")
    local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
    data_root = Path(os.environ.get("ZARA3_HOME") or local / "ZARA3")
    drive = shutil.disk_usage(data_root.anchor or local.anchor)
    if drive.free < MIN_FREE_BYTES:
        raise RuntimeError("Espaço livre abaixo do mínimo seguro de 8 GiB; nada foi instalado.")

    runtime_root = data_root / "runtimes" / "omnivoice"
    python = runtime_root / "venv" / "Scripts" / "python.exe"
    model_root = data_root / "models" / "omnivoice"
    hf_home = model_root / "hub"
    runtime_root.mkdir(parents=True, exist_ok=True)
    hf_home.mkdir(parents=True, exist_ok=True)
    environment = _safe_environment(data_root)

    if not python.is_file():
        _run([sys.executable, "-m", "venv", str(runtime_root / "venv")], environment)
    _run([
        str(python), "-m", "pip", "install", "--no-cache-dir",
        "torch==2.8.0+cu128", "torchaudio==2.8.0+cu128",
        "--extra-index-url", "https://download.pytorch.org/whl/cu128",
    ], environment)
    _run([str(python), "-m", "pip", "install", "--no-cache-dir", "omnivoice==0.2.1"], environment)
    device = _smoke(python, environment)

    marker = model_root / "ready.json"
    temporary = marker.with_suffix(".json.tmp")
    temporary.write_text(json.dumps({"ready": True, "model": MODEL_ID, "device": device}), encoding="utf-8")
    os.replace(temporary, marker)
    return marker


if __name__ == "__main__":
    try:
        print(f"OMNIVOICE_RUNTIME_READY: {install()}")
    except Exception as exc:
        print(f"OMNIVOICE_RUNTIME_FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
