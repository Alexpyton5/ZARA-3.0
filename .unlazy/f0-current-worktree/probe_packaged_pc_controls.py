from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
QUARANTINE_ROOT = ROOT / "_quarentena" / "organizacao-2026-09-23" / "pc-controls-probes"
sys.path.insert(0, str(ROOT))

import psutil
from playwright.sync_api import sync_playwright

from core.actions import os_ops


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def brightness_read() -> int | None:
    value = os_ops._read_windows_brightness()
    return value if value is not None else os_ops._wmi_read_brightness()


def original_state() -> dict[str, int | bool | None]:
    volume = os_ops._read_windows_volume()
    muted = os_ops._read_windows_mute()
    brightness = brightness_read()
    if volume is None or muted is None:
        raise RuntimeError("Cannot safely read original Windows volume and mute state; no PC mutation started.")
    return {"volume": int(volume), "muted": bool(muted), "brightness": brightness}


def wait_for_readback(reader, expected, *, tolerance: int = 0, timeout: float = 15.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = reader()
        if last is not None and abs(last - expected) <= tolerance:
            return last
        time.sleep(0.12)
    return last


def restore_direct(state: dict[str, int | bool | None]) -> dict:
    result = {"volume": None, "mute": None, "brightness": None}
    try:
        target = int(state["volume"])
        if os_ops._read_windows_volume() != target:
            wrote = bool(os_ops._set_windows_volume(target))
            observed = wait_for_readback(os_ops._read_windows_volume, target, timeout=10)
            result["volume"] = {"write": wrote, "observed": observed, "restored": observed == target}
        else:
            result["volume"] = {"observed": target, "restored": True, "needed": False}
    except Exception as exc:
        result["volume"] = {"restored": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        target = bool(state["muted"])
        if os_ops._read_windows_mute() is not target:
            wrote = bool(os_ops._set_windows_mute(target))
            observed = os_ops._read_windows_mute()
            result["mute"] = {"write": wrote, "observed": observed, "restored": observed is target}
        else:
            result["mute"] = {"observed": target, "restored": True, "needed": False}
    except Exception as exc:
        result["mute"] = {"restored": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        target = state["brightness"]
        if target is None:
            result["brightness"] = {"restored": True, "status": "UNSUPPORTED_BY_CURRENT_DISPLAY"}
        else:
            observed_before = brightness_read()
            if observed_before is not None and abs(observed_before - int(target)) <= 2:
                result["brightness"] = {"observed": observed_before, "restored": True, "needed": False}
            else:
                action = os_ops._brightness_action(int(target))
                observed = wait_for_readback(brightness_read, int(target), tolerance=2, timeout=20)
                result["brightness"] = {
                    "action_success": bool(getattr(action, "success", False)),
                    "observed": observed,
                    "restored": observed is not None and abs(observed - int(target)) <= 2,
                }
    except Exception as exc:
        result["brightness"] = {"restored": False, "error": f"{type(exc).__name__}: {exc}"}
    return result


def _result(value):
    if isinstance(value, dict) and isinstance(value.get("result"), dict):
        return value["result"]
    return value if isinstance(value, dict) else {}


def main() -> int:
    pointer = json.loads((ROOT / "ZARA_ACTIVE_BUILD.json").read_text(encoding="utf-8"))
    exe = Path(pointer["EXE_PATH"])
    exe_hash = sha256(exe)
    if exe_hash != str(pointer["EXE_SHA256"]).upper():
        raise RuntimeError("EXE_SHA256_MISMATCH")
    build_info = json.loads((exe.parent / "BUILD_INFO.json").read_text(encoding="utf-8"))
    if build_info.get("BUILD_ID") != pointer.get("BUILD_ID"):
        raise RuntimeError("BUILD_ID_MISMATCH")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = QUARANTINE_ROOT / f"{stamp}-{os.getpid()}"
    run_dir.mkdir(parents=True, exist_ok=False)
    zara_home = run_dir / "zara-data"
    electron_home = run_dir / "electron-profile"
    zara_home.mkdir()
    electron_home.mkdir()
    (electron_home / "inicio-automatico-decidido").touch()
    manifest_path = run_dir / "MANIFEST.json"
    manifest = {
        "status": "IN_PROGRESS",
        "created_at": datetime.now().astimezone().isoformat(),
        "purpose": "Isolated packaged text-to-PC-control probe with independent Windows readback.",
        "build_id": pointer["BUILD_ID"],
        "exe_path": str(exe),
        "exe_sha256": exe_hash,
        "profile_paths": [str(zara_home), str(electron_home)],
        "audio_recording_saved": False,
        "cleanup": "none; runtime evidence and profiles remain preserved here",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    stdout_path = run_dir / "electron.stdout.log"
    stderr_path = run_dir / "electron.stderr.log"
    report = {
        "evidence": "PACKAGED_RUNTIME",
        "build_id": pointer["BUILD_ID"],
        "exe_path": str(exe),
        "exe_sha256": exe_hash,
        "source_commit": pointer.get("GIT_COMMIT"),
        "profile": str(run_dir),
        "status": "ERROR",
        "original_state": None,
        "volume": {},
        "mute": {},
        "brightness": {},
        "restoration": {},
        "shutdown": "pending",
    }
    state = None
    proc = None
    page = None
    browser = None
    stdout_handle = None
    stderr_handle = None

    try:
        state = original_state()
        report["original_state"] = state

        os.environ["ZARA3_HOME"] = str(zara_home)
        from core.lab_v1.providers.registry import default_registry
        from core.lab_v1.runtime import LabRuntime
        from core.lab_v1.store import LabStore
        from core.lab_v1.supervisor import AutonomySupervisor

        store = LabStore()
        store.initialize()
        supervisor = AutonomySupervisor(LabRuntime(store, default_registry(), memory_adapter=None))
        supervisor.configure(enabled=False)
        supervisor._save(background_enabled=False, scheduler_enabled=False)
        with store._connect() as conn:
            policy = json.loads(conn.execute("SELECT document FROM lab_autonomy_policy WHERE id=1").fetchone()[0])
        report["lab_policy"] = policy
        if any(policy.get(key) is not False for key in ("enabled", "background_enabled", "scheduler_enabled")):
            raise RuntimeError("ISOLATED_LAB_NOT_PAUSED")

        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        env = os.environ.copy()
        env["ZARA3_HOME"] = str(zara_home)
        env.pop("ZARA_SMOKE_TEST", None)
        env.pop("ZARA_LAB_SCHEDULER_ENABLED", None)
        for key in list(env):
            if any(marker in key.upper() for marker in (
                "API_KEY", "TOKEN", "TELEGRAM", "NVIDIA", "GEMINI", "GOOGLE",
                "OPENAI", "ANTHROPIC", "OPENROUTER", "OPENCODE", "AZURE",
            )):
                env.pop(key, None)

        stdout_handle = stdout_path.open("wb")
        stderr_handle = stderr_path.open("wb")
        proc = subprocess.Popen(
            [str(exe), "--minimizada", "--remote-debugging-address=127.0.0.1",
             f"--remote-debugging-port={port}", f"--user-data-dir={electron_home}"],
            cwd=str(exe.parent), env=env, stdout=stdout_handle, stderr=stderr_handle,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        with sync_playwright() as playwright:
            deadline = time.monotonic() + 90
            while browser is None and time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError(f"PACKAGED_EXE_EXITED_{proc.returncode}")
                try:
                    browser = playwright.chromium.connect_over_cdp(
                        f"http://127.0.0.1:{port}", timeout=2000
                    )
                except Exception:
                    time.sleep(0.4)
            if browser is None:
                raise RuntimeError("CDP_CONNECT_TIMEOUT")
            page = browser.contexts[0].pages[0]
            page.wait_for_function(
                "!!window.zaraIPC?.action?.execute && !!window.zaraIPC?.message?.send",
                timeout=30000,
            )
            page.wait_for_function(
                """async()=>{try{return !!(await window.zaraIPC.action.execute('audio_status',{}))}catch{return false}}""",
                timeout=60000,
            )

            def read_action(action):
                return page.evaluate("async action=>await window.zaraIPC.action.execute(action,{})", action)

            def send_text(command):
                start = time.perf_counter()
                response = page.evaluate(
                    """async payload=>await Promise.race([
                        window.zaraIPC.message.send({message:payload.message,engine:'Luna',history:[]}),
                        new Promise((_,reject)=>setTimeout(()=>reject(new Error('IPC_TIMEOUT')),payload.timeoutMs))
                    ])""",
                    {"message": command, "timeoutMs": 60000},
                )
                return response, round((time.perf_counter() - start) * 1000, 1)

            volume_ipc = read_action("audio_status")
            report["volume"]["initial_ipc"] = volume_ipc
            volume_before = int(state["volume"])
            volume_target = volume_before - 10 if volume_before >= 10 else volume_before + 10
            volume_command = "diminua o volume" if volume_before >= 10 else "aumente o volume"
            response, latency = send_text(volume_command)
            observed = wait_for_readback(os_ops._read_windows_volume, volume_target)
            report["volume"].update({
                "before": volume_before, "command": volume_command, "target": volume_target,
                "response": response, "command_round_trip_ms": latency, "windows_after": observed,
                "changed_and_verified": observed == volume_target and response.get("engine") == "pc_control",
            })
            restore_response, restore_latency = send_text(f"coloque o volume em {volume_before}%")
            restored = wait_for_readback(os_ops._read_windows_volume, volume_before)
            report["volume"].update({
                "restore_response": restore_response, "restore_round_trip_ms": restore_latency,
                "restored_to_original": restored == volume_before, "windows_final": restored,
            })

            mute_before = bool(state["muted"])
            mute_command = "volta o som" if mute_before else "muta"
            mute_response, mute_latency = send_text(mute_command)
            mute_after = None
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                mute_after = os_ops._read_windows_mute()
                if mute_after is (not mute_before):
                    break
                time.sleep(0.12)
            report["mute"].update({
                "before": mute_before, "command": mute_command, "target": not mute_before,
                "response": mute_response, "command_round_trip_ms": mute_latency,
                "windows_after": mute_after,
                "changed_and_verified": mute_after is (not mute_before) and mute_response.get("engine") == "pc_control",
            })
            mute_restore_command = "muta" if mute_before else "volta o som"
            mute_restore_response, mute_restore_latency = send_text(mute_restore_command)
            deadline = time.monotonic() + 15
            mute_final = None
            while time.monotonic() < deadline:
                mute_final = os_ops._read_windows_mute()
                if mute_final is mute_before:
                    break
                time.sleep(0.12)
            report["mute"].update({
                "restore_response": mute_restore_response,
                "restore_round_trip_ms": mute_restore_latency,
                "restored_to_original": mute_final is mute_before,
                "windows_final": mute_final,
            })

            brightness_before = state["brightness"]
            if brightness_before is None:
                report["brightness"] = {"status": "UNSUPPORTED_BY_CURRENT_DISPLAY"}
            else:
                brightness_before = int(brightness_before)
                brightness_target = brightness_before - 5 if brightness_before >= 95 else brightness_before + 5
                brightness_response, brightness_latency = send_text(
                    f"coloque o brilho em {brightness_target}%"
                )
                brightness_after = wait_for_readback(
                    brightness_read, brightness_target, tolerance=2
                )
                report["brightness"].update({
                    "before": brightness_before, "target": brightness_target,
                    "response": brightness_response, "command_round_trip_ms": brightness_latency,
                    "windows_after": brightness_after,
                    "changed_and_verified": brightness_after is not None
                    and abs(brightness_after - brightness_target) <= 2
                    and abs(brightness_after - brightness_before) >= 2
                    and brightness_response.get("engine") == "pc_control",
                })
                brightness_restore, brightness_restore_latency = send_text(
                    f"coloque o brilho em {brightness_before}%"
                )
                brightness_final = wait_for_readback(
                    brightness_read, brightness_before, tolerance=2
                )
                report["brightness"].update({
                    "restore_response": brightness_restore,
                    "restore_round_trip_ms": brightness_restore_latency,
                    "restored_to_original": brightness_final is not None
                    and abs(brightness_final - brightness_before) <= 2,
                    "windows_final": brightness_final,
                })

            report["status"] = "PASS" if (
                report["volume"].get("changed_and_verified")
                and report["volume"].get("restored_to_original")
                and report["mute"].get("changed_and_verified")
                and report["mute"].get("restored_to_original")
                and (
                    report["brightness"].get("status") == "UNSUPPORTED_BY_CURRENT_DISPLAY"
                    or (report["brightness"].get("changed_and_verified")
                        and report["brightness"].get("restored_to_original"))
                )
            ) else "FAIL"
            try:
                browser.close()
            except Exception:
                pass
            browser = None
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if state is not None:
            report["restoration_fallback"] = restore_direct(state)
            final_state = {
                "volume": os_ops._read_windows_volume(),
                "muted": os_ops._read_windows_mute(),
                "brightness": brightness_read(),
            }
            report["final_state"] = final_state
            report["state_restored"] = (
                final_state["volume"] == state["volume"]
                and final_state["muted"] is state["muted"]
                and (
                    state["brightness"] is None
                    or (final_state["brightness"] is not None
                        and abs(final_state["brightness"] - int(state["brightness"])) <= 2)
                )
            )
            if not report["state_restored"]:
                report["status"] = "RESTORE_FAILED"
        if proc is not None:
            try:
                root_process = psutil.Process(proc.pid)
                children = root_process.children(recursive=True)
                for child in reversed(children):
                    try:
                        child.terminate()
                    except psutil.Error:
                        pass
                try:
                    root_process.terminate()
                except psutil.Error:
                    pass
                _, alive = psutil.wait_procs(children + [root_process], timeout=8)
                for item in alive:
                    try:
                        item.kill()
                    except psutil.Error:
                        pass
                report["shutdown"] = "isolated packaged process and children stopped"
            except psutil.Error:
                report["shutdown"] = "process already exited"
        else:
            report["shutdown"] = "app was not launched"
        if stdout_handle:
            stdout_handle.close()
        if stderr_handle:
            stderr_handle.close()
        report["runtime_logs"] = {"stdout": str(stdout_path), "stderr": str(stderr_path)}
        report["manifest"] = str(manifest_path)
        report_path = run_dir / "REPORT.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        manifest.update({
            "status": report["status"],
            "completed_at": datetime.now().astimezone().isoformat(),
            "report": str(report_path),
            "logs": [str(stdout_path), str(stderr_path)],
            "state_restored": report.get("state_restored"),
        })
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print("PC_CONTROL_PROBE_PASS" if report.get("status") == "PASS" and report.get("state_restored") else "PC_CONTROL_PROBE_FAIL")
    return 0 if report.get("status") == "PASS" and report.get("state_restored") else 1


if __name__ == "__main__":
    raise SystemExit(main())
