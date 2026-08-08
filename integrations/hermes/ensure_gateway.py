"""Start and stop the Hermes gateway owned by this ZARA process.

An already-running gateway is never adopted: ZARA may use it, but must not
terminate a process that it did not create.  A gateway launched here keeps an
exact PID/create-time identity and is cleaned up on failed activation, toggle
OFF, stdin EOF, and normal application shutdown.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request
from dataclasses import dataclass

import psutil

GATEWAY_URL = "http://127.0.0.1:8642"
_START_TIMEOUT_SECONDS = 60.0
_STOP_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class _ProcessIdentity:
    pid: int
    create_time: float


@dataclass
class _OwnedGateway:
    process: subprocess.Popen[bytes]
    executable: str
    identity: _ProcessIdentity


_gateway_lock = threading.RLock()
_owned_gateway: _OwnedGateway | None = None


def _url_alive(url: str, timeout: float = 3.0) -> bool:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


def _gateway_alive(timeout: float = 3.0) -> bool:
    """Backward-compatible health helper for the default gateway URL."""
    return _url_alive(GATEWAY_URL, timeout)


def _resolve_hermes_binary() -> str | None:
    hermes_bin = shutil.which("hermes")
    if hermes_bin is None:
        candidates = [
            r"C:\Users\alexp\AppData\Local\hermes\hermes-agent\venv\Scripts\hermes.EXE",
        ]
        hermes_bin = next((candidate for candidate in candidates if os.path.isfile(candidate)), None)
    return os.path.realpath(hermes_bin) if hermes_bin else None


def _identity_for_pid(pid: int) -> _ProcessIdentity:
    return _ProcessIdentity(pid=pid, create_time=psutil.Process(pid).create_time())


def _same_process(identity: _ProcessIdentity) -> psutil.Process | None:
    """Return only the process that still has the recorded PID and birth time."""
    try:
        process = psutil.Process(identity.pid)
        if abs(process.create_time() - identity.create_time) > 0.001:
            return None
        return process
    except (psutil.Error, OSError):
        return None


def _terminate_exact_process_tree(owned: _OwnedGateway, timeout: float) -> bool:
    root = _same_process(owned.identity)
    if root is None:
        return owned.process.poll() is not None

    # Verify the executable before using PID-based descendant operations.  If
    # Windows refuses inspection, Popen still owns a safe root handle, but we
    # deliberately avoid touching any PID that cannot be proven to be ours.
    try:
        observed_executable = os.path.realpath(root.exe())
    except (psutil.Error, OSError):
        return False
    if os.path.normcase(observed_executable) != os.path.normcase(owned.executable):
        return False

    descendants: list[tuple[psutil.Process, _ProcessIdentity]] = []
    try:
        for process in root.children(recursive=True):
            try:
                descendants.append(
                    (process, _ProcessIdentity(process.pid, process.create_time()))
                )
            except (psutil.Error, OSError):
                continue
    except (psutil.Error, OSError):
        pass

    verified = [process for process, identity in descendants if _same_process(identity) is not None]
    # Children first prevents a launcher from leaving its server child behind.
    for process in reversed(verified):
        try:
            process.terminate()
        except (psutil.Error, OSError):
            pass
    try:
        owned.process.terminate()  # Uses Popen's process handle, not a rediscovered PID.
    except (OSError, ProcessLookupError):
        pass

    _, alive = psutil.wait_procs([*verified, root], timeout=timeout)
    for process in alive:
        try:
            identity = next(
                (
                    recorded
                    for candidate, recorded in descendants
                    if candidate.pid == process.pid
                ),
                owned.identity if process.pid == owned.identity.pid else None,
            )
            if identity is not None and _same_process(identity) is not None:
                process.kill()
        except (psutil.Error, OSError):
            pass
    if alive:
        psutil.wait_procs(alive, timeout=timeout)
    identities = [owned.identity, *(identity for _, identity in descendants)]
    return all(_same_process(identity) is None for identity in identities)


def owned_gateway_pid() -> int | None:
    """Expose only ZARA's currently tracked gateway PID for diagnostics/tests."""
    with _gateway_lock:
        if _owned_gateway is None or _same_process(_owned_gateway.identity) is None:
            return None
        return _owned_gateway.identity.pid


def stop_gateway(timeout: float = _STOP_TIMEOUT_SECONDS) -> bool:
    """Stop only the gateway process tree created by this ZARA instance."""
    global _owned_gateway

    with _gateway_lock:
        owned = _owned_gateway
        _owned_gateway = None
    if owned is None:
        return True
    stopped = _terminate_exact_process_tree(owned, timeout=max(0.0, timeout))
    if not stopped and _same_process(owned.identity) is not None:
        # Preserve exact ownership so a later OFF/shutdown retry still knows
        # which process is ours.  Never replace a newer tracked launch.
        with _gateway_lock:
            if _owned_gateway is None:
                _owned_gateway = owned
    return stopped


def start_gateway(base_url: str | None = None) -> bool:
    global _owned_gateway

    url = (base_url or GATEWAY_URL).rstrip("/")
    if _url_alive(url):
        # It may belong to Hermes Desktop or another session.  Do not adopt it.
        return True

    hermes_bin = _resolve_hermes_binary()
    if hermes_bin is None:
        return False

    with _gateway_lock:
        if _owned_gateway is not None and _same_process(_owned_gateway.identity) is not None:
            owned = _owned_gateway
        else:
            env = os.environ.copy()
            env.pop("PYTHONPATH", None)
            flags = 0
            if sys.platform == "win32":
                flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
            process: subprocess.Popen[bytes] | None = None
            try:
                process = subprocess.Popen(
                    [hermes_bin, "gateway", "run"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL,
                    env=env,
                    creationflags=flags,
                    close_fds=True,
                )
                owned = _OwnedGateway(
                    process=process,
                    executable=hermes_bin,
                    identity=_identity_for_pid(process.pid),
                )
            except Exception:  # noqa: BLE001
                if process is not None and process.poll() is None:
                    try:
                        process.terminate()
                        process.wait(timeout=_STOP_TIMEOUT_SECONDS)
                    except Exception:  # noqa: BLE001
                        try:
                            process.kill()
                        except Exception:  # noqa: BLE001
                            pass
                return False
            _owned_gateway = owned

    deadline = time.monotonic() + _START_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if owned.process.poll() is not None:
            break
        if _url_alive(url):
            return True
        time.sleep(1.5)

    # Activation never succeeded.  Do not leave the attempted gateway behind.
    stop_gateway()
    return False


if __name__ == "__main__":
    ok = start_gateway()
    print("gateway ok" if ok else "gateway FAIL")
    sys.exit(0 if ok else 1)
