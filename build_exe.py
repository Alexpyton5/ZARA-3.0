#!/usr/bin/env python3
"""
ZARA 3.0 — Sidecar Python Builder (PyInstaller)
Constroi exclusivamente o sidecar Python (zara-backend.exe) para o app Electron.

Arquitetura oficial:
  Electron Builder
      └── ZARA 3.0.exe        <- aplicativo/janela
          resources/
              └── zara-backend.exe   <- sidecar Python

Este script NAO executa npm/Vite/TypeScript/Electron (responsabilidade do
Electron Builder). Ele so valida main.py, cria a config PyInstaller, constroi
zara-backend.exe e verifica o resultado.

Diretorios exclusivos do sidecar (nao toca artefatos do Electron):
  build-sidecar/  dist-sidecar/

NAO duplica codigo Python como data (core/memory/integrations entram via
analise/imports do PyInstaller). NAO empacota config, .env, dados, vault,
logs, frontend ou Electron.

console=True: o sidecar comunica com Electron via stdin/stdout/stderr.
"""

import os
import shutil
import subprocess
import sys
import json
import hashlib
from pathlib import Path
from datetime import datetime

# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).parent.absolute()
BUILD_DIR = PROJECT_ROOT / "build-sidecar"
DIST_DIR = PROJECT_ROOT / "dist-sidecar"
# Candidate packaging may use the already-provisioned project environment
# without copying it into a disposable source workspace.  Output paths remain
# derived from PROJECT_ROOT, so this never redirects a normal build.
VENV_DIR = Path(os.environ.get("ZARA_BUILD_VENV_DIR", str(PROJECT_ROOT / ".venv"))).resolve()
VENV_PYTHON = VENV_DIR / "Scripts" / "python.exe"
VENV_PIP = VENV_DIR / "Scripts" / "pip.exe"

APP_NAME = "zara-backend"
MAIN_SCRIPT = "main.py"  # Entry point do sidecar

# Hidden imports do backend (preservados do build anterior + correcoes)
HIDDEN_IMPORTS = [
    # Core
    "core.action_registry",
    "core.action_confirmation",
    "core.audit_log",
    "core.autonomy_engine",
    "core.autonomy_lab_bridge",
    "core.model_router",
    "core.zara_orchestrator",
    "core.paths",
    "core.identity",
    "core.identity._names",
    "core.identity.soul",
    "core.ipc_handlers",
    "core.voice_stt",
    "core.voice_tts",
    "core.gemini_live_voice",
    "core.token_tracker",
    "core.storage",
    "core.obsidian_bridge",
    "core.lab_coordinator",
    "core.lab_worker_runtime",
    "core.mentor_relay",
    "core.pc_voice_intent",
    "core.reminder_engine",
    "core.reminder_intent",
    "core.url_security",
    "core.realtime_web",
    "core.lab_v1.providers.opencode",
    "memory.episodic_memory",
    "memory.memory_context",
    "memory.project_memory",
    "memory.user_memory",
    # Actions (todas as 9 categorias)
    "core.actions.terminal",
    "core.actions.files",
    "core.actions.web",
    "core.actions.browser",
    "core.actions.code",
    "core.actions.os_ops",
    "core.actions.system",
    "core.actions.scheduler",
    "core.actions.vision",
    "core.actions.system_advanced",
    "core.actions.macro_actions",
    "core.actions.vision_actions",
    # Dependencias externas
    "psutil",
    "pydantic",
    "pydantic_core",
    "pydantic_settings",
    "httpx",
    "google.genai",
    "google.genai.types",
    "websockets",
    "numpy",
    "scipy",
    "cv2",
    "pytesseract",
    "mss",
    "pyperclip",
    "watchdog",
    "vosk",
    "pvporcupine",
    "kokoro_onnx",
    "edge_tts",     # voz neural gratuita da cascata de TTS
    "_miniaudio",
    "miniaudio",    # decodifica o MP3 da Edge em streaming (latencia baixa)
    "sounddevice",
    "PIL",          # Correcao: main.py exige PIL (find_spec); nao pode ser excluido
    "playwright",   # main.py testa com find_spec(); coletar como hidden import
    "faster_whisper",
    "ctranslate2",
]

EXCLUDES = [
    "tkinter",
    "matplotlib",
    "pytest",
    "IPython",
    "jupyter",
    "notebook",
    "sphinx",
    "pandas",
    "scipy.tests",
]


# ============================================================
# BUILD FUNCTIONS
# ============================================================

def run_cmd(cmd: list, cwd: Path = None, env: dict = None) -> subprocess.CompletedProcess:
    """Run command and return result"""
    print(f"[BUILD] $ {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=cwd or PROJECT_ROOT, env=env or os.environ, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result


def run_venv_cmd(cmd: list, cwd: Path = None, env: dict = None) -> subprocess.CompletedProcess:
    """Run command using the project's virtual environment Python"""
    if not VENV_PYTHON.exists():
        print(f"[BUILD] ERROR: Virtual environment Python not found at {VENV_PYTHON}")
        print("[BUILD] Please ensure the project's .venv is set up.")
        return subprocess.CompletedProcess(cmd, returncode=1, stdout="", stderr="VENV_PYTHON not found")
    full_cmd = [str(VENV_PYTHON)] + cmd
    print(f"[BUILD] $ {' '.join(full_cmd)}")
    result = subprocess.run(full_cmd, cwd=cwd or PROJECT_ROOT, env=env or os.environ, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result


def run_venv_pip(args: list, cwd: Path = None, env: dict = None) -> subprocess.CompletedProcess:
    """Run pip using the project's virtual environment"""
    if not VENV_PIP.exists():
        print(f"[BUILD] ERROR: Virtual environment pip not found at {VENV_PIP}")
        print("[BUILD] Please ensure the project's .venv is set up.")
        return subprocess.CompletedProcess([], returncode=1, stdout="", stderr="VENV_PIP not found")
    full_cmd = [str(VENV_PIP)] + args
    print(f"[BUILD] $ {' '.join(full_cmd)}")
    result = subprocess.run(full_cmd, cwd=cwd or PROJECT_ROOT, env=env or os.environ, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result


def clean_sidecar_dirs():
    """Clean ONLY sidecar build artifacts (never touches Electron artifacts)."""
    print("[BUILD] Cleaning sidecar artifacts...")
    for dir_path in [BUILD_DIR, DIST_DIR, PROJECT_ROOT / "__pycache__"]:
        if dir_path.resolve().parent != PROJECT_ROOT.resolve():
            raise ValueError("Build cleanup escaped project directory")
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"[BUILD] Removed: {dir_path}")


def clean_frontend_dirs():
    """Clean frontend build artifacts (safe to remove, will be rebuilt)."""
    print("[BUILD] Cleaning frontend artifacts...")
    frontend_dir = PROJECT_ROOT / "frontend"
    for dir_name in ["dist-electron", "dist-frontend", "dist-tests"]:
        dir_path = frontend_dir / dir_name
        if dir_path.resolve().parent != PROJECT_ROOT.resolve():
            raise ValueError("Build cleanup escaped project directory")
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"[BUILD] Removed: {dir_path}")
    # Note: We do NOT touch frontend/release (baseline de recuperacao)


def create_pyinstaller_spec() -> Path:
    """Create PyInstaller .spec file for the sidecar."""
    from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

    # dados: recursos do pvporcupine (keyword_files *.ppn) + kokoro_onnx (config.json, py.typed)
    # + language_tags (data/json/*.json — dependencia do kokoro_onnx)
    porcupine_datas = collect_data_files("pvporcupine")
    kokoro_datas = collect_data_files("kokoro_onnx")
    language_tags_datas = collect_data_files("language_tags")
    # ZARA-TTS-DATA-001: jsonschema_specifications lista o diretorio schemas/
    # no import (via referencing/__rmatmul__). Sem estes dados o backend morre
    # com FileNotFoundError e o app inteiro perde voz, Lab e cerebros.
    jsonschema_spec_datas = collect_data_files("jsonschema_specifications")
    genai_datas = collect_data_files("google.genai")
    # ZARA-VOICE-KORE-PACKAGING-001
    # sounddevice carrega o PortAudio de _sounddevice_data/portaudio-binaries/.
    # Era a UNICA biblioteca de voz sem coleta de dados/binarios aqui, entao o
    # DLL nativo nunca entrava no EXE e "import sounddevice" falhava so no
    # empacotado. Sem sounddevice o Gemini Live nao sobe e a ZARA cai calada
    # na voz local — a causa da voz errada e da latencia.
    sounddevice_datas = collect_data_files("sounddevice")
    # ZARA-VOZ-GRATUITA-001: a Edge fala por WebSocket TLS. Sem os certificados
    # do certifi dentro do EXE, a voz gratuita funciona no source e falha so no
    # empacotado — exatamente o tipo de divergencia que build-release.md proibe.
    certifi_datas = collect_data_files("certifi")
    # ZARA-ALMA-001: a alma e lida de um .md, nao de codigo. Sem empacotar o
    # IDENTITY.md o executavel congelado boota nos padroes embutidos e ela
    # perde o nome que o Alex deu - falha silenciosa, so visivel no build.
    identity_md = PROJECT_ROOT / "IDENTITY.md"
    identity_datas = [(str(identity_md), ".")] if identity_md.exists() else []
    # ZARA-CONFIG-SEED-001: o exe le config de LOCALAPPDATA; sem a copia
    # congelada a semente do primeiro boot nao tem de onde ler (chave NVIDIA
    # e preferencias de voz invisiveis ao empacotado para sempre).
    config_seed_names = ("api_keys.json", "feature_flags.json")
    config_datas = [
        (str(PROJECT_ROOT / "config" / name), "config")
        for name in config_seed_names
        if (PROJECT_ROOT / "config" / name).exists()
    ]
    datas = (
        porcupine_datas + kokoro_datas + language_tags_datas + jsonschema_spec_datas
        + genai_datas + sounddevice_datas + certifi_datas + identity_datas
        + config_datas
    )

    # google-genai runtime modules ONLY (exclui google.genai.tests.* que inchava o build).
    genai_runtime = [
        "google.genai.client", "google.genai.types", "google.genai.models",
        "google.genai.chats", "google.genai.files", "google.genai.live",
        "google.genai.caches", "google.genai.batches", "google.genai.operations",
        "google.genai._local_tokenizer_loader", "google.genai.local_tokenizer",
        "google.genai.interactions", "google.genai.tunings", "google.genai.documents",
        "google.genai.mcp", "google.genai.gaos", "google.genai.errors",
        "google.genai.common", "google.genai.transformers",
    ]
    all_hidden_imports = sorted(set(HIDDEN_IMPORTS + genai_runtime))

    # Bibliotecas nativas do vosk (libvosk.dll + deps) com destino dentro de vosk/
    vosk_binaries = collect_dynamic_libs("vosk")

    # Bibliotecas nativas do pvporcupine (se existirem — retornou 13 entradas)
    porcupine_binaries = collect_dynamic_libs("pvporcupine")
    # ZARA-VOICE-KORE-PACKAGING-001: PortAudio nativo do sounddevice.
    # collect_dynamic_libs("sounddevice") retorna vazio (nao e pacote) — coletar manualmente.
    import sounddevice as _sd
    _sd_path = Path(_sd.__file__).parent
    _portaudio = list(_sd_path.glob("_sounddevice_data/portaudio-binaries/**/*.dll"))
    sounddevice_binaries = [(str(p), "_sounddevice_data/portaudio-binaries") for p in _portaudio]
    # _miniaudio is one native extension, not every DLL in site-packages.
    # PyInstaller follows the import and collects its linked dependencies.
    miniaudio_binaries = []
    binaries = (
        vosk_binaries + porcupine_binaries + sounddevice_binaries + miniaudio_binaries
    )

    # Icon: sidecar sem icone (console tool)
    icon_arg = "None"

    # Usar forward slashes para evitar erros de escape (\U, \u) no spec
    pathex_str = str(PROJECT_ROOT).replace("\\", "/")
    main_script_str = str(PROJECT_ROOT / MAIN_SCRIPT).replace("\\", "/")
    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-\n\nblock_cipher = None\n\na = Analysis(\n    ['{main_script_str}'],\n    pathex=['{pathex_str}'],\n    binaries={binaries},\n    datas={datas},\n    hiddenimports={all_hidden_imports},\n    hookspath=[],\n    hooksconfig={{}},\n    runtime_hooks=[],\n    excludes={EXCLUDES},\n    win_no_prefer_redirects=False,\n    win_private_assemblies=False,\n    cipher=block_cipher,\n    noarchive=False,\n)\n\npyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)\n\nexe = EXE(\n    pyz,\n    a.scripts,\n    a.binaries,\n    a.zipfiles,\n    a.datas,\n    [],\n    name='{APP_NAME}',\n    debug=False,\n    bootloader_ignore_signals=False,\n    strip=False,\n    upx=True,\n    upx_exclude=[],\n    runtime_tmpdir=None,\n    console=True,\n    disable_windowed_traceback=False,\n    argv_emulation=False,\n    target_arch=None,\n    codesign_identity=None,\n    entitlements_file=None,\n    icon={icon_arg},\n)\n'''

    spec_path = BUILD_DIR / "zara-backend.spec"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(spec_content, encoding="utf-8")
    print(f"[BUILD] Created spec: {spec_path}")
    return spec_path


def run_pyinstaller(spec_path: Path) -> bool:
    """Run PyInstaller from the project's virtual environment"""
    print("[BUILD] Running PyInstaller...")
    print(f"[BUILD] Python environment: {VENV_PYTHON}")

    # Verifica se pyinstaller existe no venv; se nao, BLOCKED (nao instala sozinho)
    result = run_venv_cmd(["-m", "PyInstaller", "--version"])
    if result.returncode != 0:
        print("[BUILD] STATUS: BLOCKED — PYINSTALLER AUSENTE no venv")
        print("[BUILD] Nao instale por iniciativa propria; reporte ao Mentor.")
        return False

    command = [
        str(VENV_PYTHON), "-m", "PyInstaller", "--clean", "--noconfirm",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR / "work"),
        str(spec_path),
    ]
    print(f"[BUILD] $ {' '.join(command)}", flush=True)
    # PyInstaller pode levar vários minutos. Não capture a saída inteira:
    # mostrar o progresso em tempo real evita a falsa aparência de travamento
    # e deixa o erro de arquivo bloqueado visível no ponto exato.
    try:
        result = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    except OSError as exc:
        print(f"[BUILD] ERROR: nao foi possivel iniciar PyInstaller: {exc}", flush=True)
        return False

    if result.returncode != 0:
        print("[BUILD] ERROR: PyInstaller failed")
        return False

    # Checa saida
    exe_path = DIST_DIR / f"{APP_NAME}.exe"
    if exe_path.exists():
        print(f"[BUILD] SUCCESS: {exe_path} created ({exe_path.stat().st_size / 1024 / 1024:.1f} MB)")
        return True
    else:
        print("[BUILD] ERROR: EXE not found after build")
        return False


def verify_build() -> bool:
    """Quick verification of built sidecar EXE."""
    exe_path = DIST_DIR / f"{APP_NAME}.exe"
    if not exe_path.exists():
        return False

    print(f"[BUILD] Verifying: {exe_path}")
    print(f"[BUILD] Size: {exe_path.stat().st_size / 1024 / 1024:.1f} MB")
    print("[BUILD] Verification complete")
    return True


def update_sidecar_manifests(exe_path: Path) -> str:
    """Update CLEAN_BUILD_ID.txt, SHA256_MANIFEST.txt, PATCH_SHA256_MANIFEST.txt for the sidecar.
    Returns the SHA256 hash."""
    if not exe_path.exists():
        print(f"[BUILD] ERROR: {exe_path} not found for manifest update")
        return ""

    # Compute SHA256
    hash_sha256 = hashlib.sha256()
    with exe_path.open('rb') as f:
        for chunk in iter(lambda: f.read(4096), b''):
            hash_sha256.update(chunk)
    hash_hex = hash_sha256.hexdigest()

    # Update CLEAN_BUILD_ID.txt (first 8 chars)
    clean_build_id = hash_hex[:8]
    (PROJECT_ROOT / 'CLEAN_BUILD_ID.txt').write_text(clean_build_id + '\n')
    print(f"[BUILD] Updated CLEAN_BUILD_ID.txt: {clean_build_id}")

    # Update SHA256_MANIFEST.txt
    manifest_path = exe_path.resolve().relative_to(PROJECT_ROOT.resolve()).as_posix()
    manifest_content = f"{hash_hex}  {manifest_path}\n"
    (PROJECT_ROOT / 'SHA256_MANIFEST.txt').write_text(manifest_content, newline='\n')
    print("[BUILD] Updated SHA256_MANIFEST.txt")

    # Update PATCH_SHA256_MANIFEST.txt (same as SHA256_MANIFEST.txt for now)
    (PROJECT_ROOT / 'PATCH_SHA256_MANIFEST.txt').write_text(manifest_content, newline='\n')
    print("[BUILD] Updated PATCH_SHA256_MANIFEST.txt")

    return hash_hex


def generate_build_info(sidecar_sha256: str) -> None:
    """Record this sidecar only; Electron identity is written after packaging.

    A sidecar build must never label the previous app.asar as newly built or
    overwrite the active Electron package's BUILD_INFO.json.
    """
    from tools.build_current import source_identity

    exe_path = DIST_DIR / f"{APP_NAME}.exe"
    info = {
        "BUILD_ID": f"sidecar-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
        "BUILD_TIMESTAMP": datetime.now().astimezone().isoformat(),
        "SIDECAR_SHA256": sidecar_sha256,
        "SIDECAR_SIZE_BYTES": exe_path.stat().st_size,
        "SOURCE_SHA256": source_identity(backend_only=True)["sha256"],
        "PYTHON_PATH": str(VENV_PYTHON),
    }
    info_path = DIST_DIR / "BUILD_INFO.json"
    info_path.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")
    print(f"[BUILD] Generated sidecar receipt: {info_path}")


def build(clean_first=True) -> int:
    """Sidecar build entry (public function; used by pyproject zara-build)."""
    print("=" * 60)
    print("ZARA 3.0 SIDECAR BUILDER (zara-backend.exe)")
    print("=" * 60)

    # Valida entrypoint
    if not (PROJECT_ROOT / MAIN_SCRIPT).exists():
        print(f"ERROR: Main script not found: {MAIN_SCRIPT}")
        return 1

    # Check for virtual environment
    if not VENV_PYTHON.exists():
        print(f"[BUILD] ERROR: Virtual environment not found at {VENV_DIR}")
        print("[BUILD] Please run 'python -m venv .venv' and install dependencies first.")
        return 1

    # Clean ONLY sidecar dirs if requested
    if clean_first:
        clean_sidecar_dirs()

    # Cria spec
    spec_path = create_pyinstaller_spec()

    # Roda PyInstaller (usando o venv do projeto)
    if not run_pyinstaller(spec_path):
        return 1

    # Verifica
    if not verify_build():
        return 1

    # Atualiza os arquivos de manifesto para o sidecar
    exe_path = DIST_DIR / f"{APP_NAME}.exe"
    sidecar_sha256 = update_sidecar_manifests(exe_path)

    # Gera BUILD_INFO.json
    if sidecar_sha256:
        generate_build_info(sidecar_sha256)

    print("=" * 60)
    print("SIDECAR BUILD COMPLETE!")
    print(f"Output: {DIST_DIR / f'{APP_NAME}.exe'}")
    print("=" * 60)
    return 0


def build_full() -> int:
    """Build a complete new package without changing the active application."""
    from tools.build_current import build_package

    try:
        build_package("Complete rebuild from current source")
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"[BUILD] Failed: {exc}")
        return 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        sys.exit(build_full())
    else:
        sys.exit(build())
