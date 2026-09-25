#!/usr/bin/env python3
"""Run a real ZARA Lab mission in the same canonical state shown by the UI.

This launcher exists so engineering/autonomy work can be watched inside the
real ZARA Lab.  It refuses disposable homes and refuses to run unless the
currently active packaged ZARA build is open.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _canonical_home() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        raise RuntimeError("LOCALAPPDATA indisponivel; nao e possivel provar o Lab canonico.")
    canonical = (Path(local) / "ZARA3").resolve()
    configured = os.environ.get("ZARA3_HOME")
    if configured and Path(configured).resolve() != canonical:
        raise RuntimeError(
            "ZARA3_HOME aponta para um perfil isolado. Missao real deve usar o Lab canonico."
        )
    # Source Python normally uses project/config. Pinning ZARA3_HOME to the
    # *canonical* app home makes data + config identical to the packaged app;
    # this is not an isolated profile.
    os.environ["ZARA3_HOME"] = str(canonical)
    return canonical


def _active_build() -> tuple[dict[str, Any], Path, Path]:
    manifest = ROOT / "ZARA_ACTIVE_BUILD.json"
    if not manifest.exists():
        raise RuntimeError("ZARA_ACTIVE_BUILD.json nao existe.")
    info = json.loads(manifest.read_text(encoding="utf-8-sig"))
    exe_raw = str(info.get("EXE_PATH") or "").strip()
    if not exe_raw:
        raise RuntimeError("EXE_PATH ausente em ZARA_ACTIVE_BUILD.json.")
    exe = Path(exe_raw).resolve()
    if not exe.exists():
        raise RuntimeError(f"Build ativo nao existe: {exe}")
    # .../<build>/win-unpacked/ZARA 3.0.exe
    build_root = exe.parent.parent.resolve()
    return info, exe, build_root


def _running_zara_processes() -> list[dict[str, Any]]:
    if os.name != "nt":
        raise RuntimeError("Launcher do Lab visivel requer Windows.")
    script = r"""
$rows = Get-CimInstance Win32_Process |
  Where-Object { $_.Name -in @('ZARA 3.0.exe','zara-backend.exe') } |
  Select-Object Name,ProcessId,ParentProcessId,ExecutablePath
if ($rows) { $rows | ConvertTo-Json -Compress }
"""
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError("Nao foi possivel verificar o processo da ZARA aberta.")
    raw = proc.stdout.strip()
    if not raw:
        return []
    decoded = json.loads(raw)
    return decoded if isinstance(decoded, list) else [decoded]


def _assert_active_app(exe: Path, build_root: Path) -> None:
    rows = _running_zara_processes()
    expected_exe = os.path.normcase(str(exe))
    expected_root = os.path.normcase(str(build_root)) + os.sep
    app_ok = False
    backend_ok = False
    for row in rows:
        path = str(row.get("ExecutablePath") or "")
        normalized = os.path.normcase(path)
        if row.get("Name") == "ZARA 3.0.exe" and normalized == expected_exe:
            app_ok = True
        if row.get("Name") == "zara-backend.exe" and normalized.startswith(expected_root):
            backend_ok = True
    if not app_ok or not backend_ok:
        raise RuntimeError(
            "O build ativo precisa estar aberto com o backend real antes de iniciar uma missao visivel."
        )


def _visible_snapshot(session_id: str) -> dict[str, Any]:
    from core.lab_v1.store import LabStore

    store = LabStore()
    store.initialize()
    session = store.get_session(session_id)
    if session is None:
        raise RuntimeError("A sessao nao apareceu no banco canonico do ZARA Lab.")
    return {
        "session_id": session.id,
        "state": getattr(session.state, "value", str(session.state)),
        "objective": session.objective,
        "messages": len(store.list_messages(session.id)),
        "tasks": len(store.list_tasks(session.id)),
        "runs": len(store.list_runs(session.id)),
        "artifacts": len(store.list_artifacts(session.id)),
        "db_path": str(store.db_path.resolve()),
    }


async def _run(objective: str) -> int:
    canonical = _canonical_home()
    info, exe, build_root = _active_build()
    _assert_active_app(exe, build_root)

    from core.lab_v1.service import LabV1Service
    from core.lab_v1.workforce_policy import WorkforcePolicy

    service = LabV1Service()
    blocked = await asyncio.to_thread(service._promotion_block)
    if blocked is not None:
        print(json.dumps(blocked, ensure_ascii=False))
        return 3
    if not WorkforcePolicy(service._get_supervisor().policy()).mission_entry_enabled:
        print(json.dumps(service.workforce_refusal(), ensure_ascii=False))
        return 4

    # Reconcile only the old, fully-settled empty-plan bug. This never touches
    # a mission with a live lease, active run, pending step or actual work left.
    autopilot = service._get_autopilot()
    await asyncio.to_thread(autopilot.controller.release_dead_leases)
    for session in await asyncio.to_thread(autopilot.store.list_sessions, None, 200):
        if getattr(session.state, "value", str(session.state)) in {
            "COMPLETED", "FAILED", "CANCELLED"
        }:
            continue
        if not await asyncio.to_thread(autopilot.store.mission_snapshot, session.id):
            # Old/plain chat sessions can legitimately exist without a Mission
            # Controller document. They are visible history, not ghost work.
            continue
        reconciled = await asyncio.to_thread(
            autopilot.controller.reconcile_verified_empty_plan, session.id
        )
        if reconciled:
            print(json.dumps({
                "event": "VISIBLE_LAB_GHOST_RECONCILED",
                "session_id": session.id,
                "state": "COMPLETED",
            }, ensure_ascii=False))
            sys.stdout.flush()

    # Deliberately use the canonical Autopilot without starting a second
    # scheduler/supervisor loop in this helper process. The packaged app stays
    # the visible owner of its own background runtime.
    started = await asyncio.to_thread(autopilot.start, objective)
    if not started.get("success"):
        print(json.dumps(started, ensure_ascii=False))
        return 5

    session_id = str(started["session_id"])
    visible = _visible_snapshot(session_id)
    print(json.dumps({
        "event": "VISIBLE_LAB_MISSION_STARTED",
        "build_id": info.get("BUILD_ID"),
        "canonical_home": str(canonical),
        **visible,
    }, ensure_ascii=False))
    sys.stdout.flush()

    result = await asyncio.to_thread(autopilot.run, session_id)
    final_visible = _visible_snapshot(session_id)
    print(json.dumps({
        "event": "VISIBLE_LAB_MISSION_SETTLED",
        "result": result,
        **final_visible,
    }, ensure_ascii=False, default=str))
    return 0 if result.get("success", True) else 6


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inicia uma missao real no mesmo ZARA Lab visivel no app."
    )
    parser.add_argument("objective", help="Objetivo que os agentes devem executar no Lab")
    args = parser.parse_args()
    objective = args.objective.strip()
    if not objective:
        parser.error("objective nao pode ser vazio")
    try:
        return asyncio.run(_run(objective))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
