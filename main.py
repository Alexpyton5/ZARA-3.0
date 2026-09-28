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
    """Run the IPC handler and optional NERVOS inbox monitor."""
    from core.ipc_handlers import main as ipc_main

    ronda = None
    status_task = None
    # Canary runs are isolated smoke checks.  Do not let a monitor that reads
    # the owner's live inbox leak into that environment or perturb its output.
    if os.environ.get("ZARA_SMOKE_TEST") != "1":
        try:
            from core.nervos_daemon import NervosRonda
            from core.paths import project_root

            inbox_dir = _resolve_nervos_inbox_dir(project_root())
            ronda = NervosRonda(inbox_dir=str(inbox_dir))
            ronda.iniciar()
            _emit_nervos_status(ronda)
            status_task = asyncio.create_task(
                _log_nervos_status_periodically(ronda),
                name="zara-nervos-status",
            )
        except Exception as exc:
            if ronda is not None:
                try:
                    ronda.parar()
                except Exception as stop_exc:
                    print(f"[NERVOS] monitor cleanup failed: {stop_exc}", flush=True)
            ronda = None
            print(f"[NERVOS] monitor unavailable; backend continues: {exc}", flush=True)

    try:
        await ipc_main()
    finally:
        if status_task is not None:
            status_task.cancel()
            await asyncio.gather(status_task, return_exceptions=True)
        if ronda is not None:
            try:
                ronda.parar()
                print("[NERVOS] monitor stopped", flush=True)
            except Exception as exc:
                print(f"[NERVOS] monitor shutdown failed: {exc}", flush=True)


def _resolve_nervos_inbox_dir(project_root: Path) -> Path:
    """Use a configured inbox, the source-tree inbox, or Alex's live workspace."""
    configured = os.environ.get("ZARA_ZOE_INBOX_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()

    project_inbox = project_root / "ZOE-INBOX"
    if not getattr(sys, "frozen", False):
        return project_inbox
    if (project_inbox / "heartbeat.json").is_file():
        return project_inbox

    workspace_inbox = (
        Path.home() / "Downloads" / "ZARA 3.0 CLEAN 002" / "ZOE-INBOX"
    )
    if (workspace_inbox / "heartbeat.json").is_file():
        return workspace_inbox
    return project_inbox


def _emit_nervos_status(ronda) -> None:
    """Expose the monitor's current read-only state through backend logs."""
    import json

    try:
        status = ronda.get_status()
        encoded = json.dumps(status, ensure_ascii=False, sort_keys=True)
        print(f"[NERVOS] status={encoded}", flush=True)
    except Exception as exc:
        print(f"[NERVOS] status unavailable: {exc}", flush=True)


async def _log_nervos_status_periodically(ronda, interval_seconds: float = 60.0) -> None:
    """Keep the monitor status observable without making it an app dependency."""
    while True:
        await asyncio.sleep(interval_seconds)
        _emit_nervos_status(ronda)


def main() -> int:
    """Main entry point."""
    configure_utf8_stdio()
    print("=" * 60)
    print("  ZARA 3.0 — NEURAL INTERFACE")
    print("  Python Sidecar Starting...")
    print("=" * 60)

    if os.environ.get("ZARA_SMOKE_TEST") == "1":
        from core.lab_v1.canary import allowed

        if not allowed("lab-v1-admit-operation"):
            print("[ERROR] Smoke mode requires a marked disposable ZARA3_HOME")
            return 1

    setup_environment()

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
    return 0


if __name__ == "__main__":
    # PyInstaller replaces this function at runtime so spawned workers execute
    # multiprocessing.spawn_main() instead of re-entering ZARA's IPC loop.
    # In normal source execution the standard-library implementation is a no-op.
    import multiprocessing

    multiprocessing.freeze_support()
    sys.exit(main())
