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
from pathlib import Path

# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_ROOT = Path(__file__).parent.absolute()
BUILD_DIR = PROJECT_ROOT / "build-sidecar"
DIST_DIR = PROJECT_ROOT / "dist-sidecar"

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
    "core.ipc_handlers",
    "core.voice_stt",
    "core.voice_tts",
    "core.gemini_live_voice",
    "core.token_tracker",
    "core.storage",
    "core.obsidian_bridge",
    "core.lab_coordinator",
    "core.lab_worker_runtime",
    "core.lab_mission",
    "core.lab_roles",
    "core.lab_research",
    "core.lab_patch_pipeline",
    "core.lab_bot_config",
    "core.lab_autonomy",
    "core.lab_ceo_gmail_bridge",
    "core.mentor_relay",
    "core.pc_voice_intent",
    "core.reminder_engine",
    "core.reminder_intent",
    "core.url_security",
    "core.realtime_web",
    # Memory
    "memory.memory_manager",
    "memory.episodic_memory",
    "memory.memory_context",
    "memory.project_memory",
    "memory.user_memory",
    # Hermes integration
    "integrations.hermes.integration",
    "integrations.hermes.bridge",
    "integrations.hermes.client",
    "integrations.hermes.ensure_gateway",
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
    "sounddevice",
    "PIL",          # Correcao: main.py exige PIL (find_spec); nao pode ser excluido
    "playwright",   # main.py testa com find_spec(); coletar como hidden import
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


def clean_sidecar_dirs():
    """Clean ONLY sidecar build artifacts (never touches Electron artifacts)."""
    print("[BUILD] Cleaning sidecar artifacts...")
    for dir_path in [BUILD_DIR, DIST_DIR, PROJECT_ROOT / "__pycache__"]:
        if dir_path.exists():
            shutil.rmtree(dir_path)
            print(f"[BUILD] Removed: {dir_path}")


def create_pyinstaller_spec() -> Path:
    """Create PyInstaller .spec file for the sidecar."""
    from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

    # datas: recursos do pvporcupine (keyword_files *.ppn) + kokoro_onnx (config.json, py.typed)
    # + language_tags (data/json/*.json — dependencia do kokoro_onnx)
    porcupine_datas = collect_data_files("pvporcupine")
    kokoro_datas = collect_data_files("kokoro_onnx")
    language_tags_datas = collect_data_files("language_tags")
    genai_datas = collect_data_files("google.genai")
    datas = porcupine_datas + kokoro_datas + language_tags_datas + genai_datas

    # google-genai has a broad async/live module tree; collect it explicitly so
    # PyInstaller cannot miss modules imported dynamically by the SDK.
    genai_hidden = collect_submodules("google.genai")
    all_hidden_imports = sorted(set(HIDDEN_IMPORTS + genai_hidden))

    # Bibliotecas nativas do vosk (libvosk.dll + deps) com destino dentro de vosk/
    vosk_binaries = collect_dynamic_libs("vosk")

    # Bibliotecas nativas do pvporcupine (se existirem — retornou 13 entradas)
    porcupine_binaries = collect_dynamic_libs("pvporcupine")
    binaries = vosk_binaries + porcupine_binaries

    # Icon: sidecar sem icone (console tool)
    icon_arg = "None"

    # Usar forward slashes para evitar erros de escape (\\U, \\u) no spec
    pathex_str = str(PROJECT_ROOT).replace("\\", "/")
    main_script_str = str(PROJECT_ROOT / MAIN_SCRIPT).replace("\\", "/")
    spec_content = f'''# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['{main_script_str}'],
    pathex=['{pathex_str}'],
    binaries={binaries},
    datas={datas},
    hiddenimports={all_hidden_imports},
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes={EXCLUDES},
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='{APP_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon={icon_arg},
)
'''

    spec_path = BUILD_DIR / "zara-backend.spec"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(spec_content, encoding="utf-8")
    print(f"[BUILD] Created spec: {spec_path}")
    return spec_path


def run_pyinstaller(spec_path: Path) -> bool:
    """Run PyInstaller (uses installed pyinstaller; does NOT pip install)."""
    print("[BUILD] Running PyInstaller...")

    # Verifica se pyinstaller existe; se nao, BLOCKED (nao instala sozinho)
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("[BUILD] STATUS: BLOCKED — PYINSTALLER AUSENTE")
        print("[BUILD] Nao instale por iniciativa propria; reporte ao Mentor.")
        return False

    result = run_cmd([
        sys.executable, "-m", "PyInstaller", "--clean", "--noconfirm",
        "--distpath", str(DIST_DIR),
        "--workpath", str(BUILD_DIR / "work"),
        str(spec_path),
    ])

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


def build() -> int:
    """Sidecar build entry (public function; used by pyproject zara-build)."""
    print("=" * 60)
    print("ZARA 3.0 SIDECAR BUILDER (zara-backend.exe)")
    print("=" * 60)

    # Valida entrypoint
    if not (PROJECT_ROOT / MAIN_SCRIPT).exists():
        print(f"ERROR: Main script not found: {MAIN_SCRIPT}")
        return 1

    # Clean ONLY sidecar dirs
    clean_sidecar_dirs()

    # Cria spec
    spec_path = create_pyinstaller_spec()

    # Roda PyInstaller (ja instalado; sem pip install automatico)
    if not run_pyinstaller(spec_path):
        return 1

    # Verifica
    if not verify_build():
        return 1

    print("=" * 60)
    print("SIDECAR BUILD COMPLETE!")
    print(f"Output: {DIST_DIR / f'{APP_NAME}.exe'}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(build())
