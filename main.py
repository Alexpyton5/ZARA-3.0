#!/usr/bin/env python3
"""
ZARA 3.0 — Neural Interface Entry Point
Python sidecar for Electron frontend. Handles IPC via stdin/stdout.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Force local venv isolation
os.environ.pop("PYTHONPATH", None)


def configure_utf8_stdio() -> None:
    """Match Electron's UTF-8 pipes on Windows and other supported platforms."""
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def setup_environment():
    """Create only user-writable runtime directories."""
    from core.paths import config_dir, data_dir, logs_dir, memory_dir, user_data_dir

    user_data_dir()
    config_dir()
    data_dir()
    logs_dir()
    memory_dir()

    # Advisory single-writer guard: warn (never kill) if another live ZARA
    # process already owns this data dir. Fail-open by design.
    try:
        from core.single_writer import acquire_writer_lock

        lock = acquire_writer_lock(data_dir())
        if lock.blocked:
            print(
                "[ZARA][WARN] Outro processo ZARA (PID "
                f"{lock.conflict_pid}) ja usa este data dir: {data_dir()}. "
                "Risco de dois writers no mesmo SQLite/WAL. "
                "Use ZARA3_HOME para isolar um runtime de teste."
            )
        return lock
    except Exception:
        return None


def check_dependencies() -> bool:
    """Check essential dependencies and report optional capabilities separately."""
    import importlib.util

    essential = [
        "httpx", "pydantic", "pydantic_settings", "psutil",
    ]
    optional = [
        "cv2", "mss", "PIL", "pytesseract", "vosk", "pvporcupine",
        "kokoro_onnx", "sounddevice", "numpy", "scipy", "playwright",
        "pyperclip", "watchdog",
    ]

    missing_essential = [pkg for pkg in essential if importlib.util.find_spec(pkg) is None]
    missing_optional = [pkg for pkg in optional if importlib.util.find_spec(pkg) is None]

    if missing_optional:
        print(f"[ZARA] Optional capabilities unavailable: {', '.join(missing_optional)}")
    if missing_essential:
        print(f"[ERROR] Missing essential dependencies: {', '.join(missing_essential)}")
        print("Run: uv pip install -r requirements.txt")
        return False
    return True


async def run_ipc_handler():
    """Run the IPC handler (main entry point for Python sidecar)"""
    from core.ipc_handlers import main as ipc_main
    await ipc_main()


def main() -> int:
    """Main entry point."""
    configure_utf8_stdio()
    print("=" * 60)
    print("  ZARA 3.0 — NEURAL INTERFACE")
    print("  Python Sidecar Starting...")
    print("=" * 60)

    writer_lock = setup_environment()

    if not check_dependencies():
        return 1

    try:
        asyncio.run(run_ipc_handler())
    except KeyboardInterrupt:
        print("\n[ZARA] Shutdown requested")
    except Exception as e:
        print(f"[ERROR] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    print("[ZARA] Goodbye")
    if writer_lock is not None:
        writer_lock.release()
    return 0


if __name__ == "__main__":
    # PyInstaller replaces this function at runtime so spawned workers execute
    # multiprocessing.spawn_main() instead of re-entering ZARA's IPC loop.
    # In normal source execution the standard-library implementation is a no-op.
    import multiprocessing

    multiprocessing.freeze_support()
    sys.exit(main())
