"""Auto-start do gateway Hermes quando a ZARA inicia (se ativo)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.request

GATEWAY_URL = "http://127.0.0.1:8642"


def _gateway_alive(timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(
            GATEWAY_URL + "/health", timeout=timeout
        ) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


def start_gateway(base_url: str | None = None) -> bool:
    url = (base_url or GATEWAY_URL).rstrip("/")
    try:
        with urllib.request.urlopen(url + "/health", timeout=3.0) as resp:
            if resp.status == 200:
                return True
    except Exception:  # noqa: BLE001
        pass

    hermes_bin = shutil.which("hermes")
    if hermes_bin is None:
        candidates = [
            r"C:\Users\alexp\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.EXE",
        ]
        hermes_bin = next((c for c in candidates if os.path.isfile(c)), None)
    if hermes_bin is None:
        return False

    env = os.environ.copy()
    env.pop("PYTHONPATH", None)  # nunca vazar outro venv para o filho
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
    subprocess.Popen(
        [hermes_bin, "gateway", "run"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        env=env,
        creationflags=flags,
        close_fds=True,
    )
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url + "/health", timeout=3.0) as resp:
                if resp.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            pass
        time.sleep(1.5)
    return False


if __name__ == "__main__":
    ok = start_gateway()
    print("gateway ok" if ok else "gateway FAIL")
    sys.exit(0 if ok else 1)
