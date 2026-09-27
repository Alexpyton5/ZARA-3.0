"""Real packaged Electron IPC/UI canary in disposable userdata. No product data mutations."""
import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_current import packaged_paths, digest, write_json


def inspect_entry_workspace(snapshot, database, disposable_home):
    """Independently verify the workspace reported by a packaged Lab snapshot."""
    policy = snapshot.get('autonomy_policy') or {}
    if policy.get('background_task_state') not in ('STOPPED', 'PAUSED'):
        raise RuntimeError('ENTRY_CANARY_SUPERVISOR_NOT_PAUSED')
    raw = policy.get('workspace')
    if not isinstance(raw, str) or not raw or not Path(raw).is_absolute():
        raise RuntimeError('PACKAGED_WORKSPACE_NOT_CONFIGURED')
    database = Path(database)
    if not database.is_file():
        raise RuntimeError('PACKAGED_WORKSPACE_NOT_PERSISTED')
    try:
        with closing(sqlite3.connect(database)) as conn:
            row = conn.execute('SELECT document FROM lab_autonomy_policy WHERE id=1').fetchone()
        persisted = json.loads(row[0]) if row else {}
    except (sqlite3.Error, ValueError, TypeError):
        raise RuntimeError('PACKAGED_WORKSPACE_NOT_PERSISTED') from None
    if not isinstance(persisted, dict) or persisted.get('workspace') != raw:
        raise RuntimeError('PACKAGED_WORKSPACE_NOT_PERSISTED')

    workspace = Path(raw).resolve()
    home = Path(disposable_home).resolve()
    if (not workspace.is_dir() or any(part.upper().startswith('_MEI') for part in workspace.parts)
            or workspace == home or home in workspace.parents):
        raise RuntimeError('PACKAGED_WORKSPACE_NOT_CONFIGURED')
    git_marker = workspace / '.git'
    try:
        valid_git = ((git_marker.is_dir() and (git_marker / 'HEAD').is_file())
                     or (git_marker.is_file() and git_marker.read_text(
                         encoding='utf-8', errors='replace').startswith('gitdir:')))
        valid_source = all((workspace / name).is_file() for name in (
            'tools/build_current.py', 'core/lab_v1/autopilot.py',
            'core/lab_v1/evolution.py'))
        with (workspace / 'pyproject.toml').open('rb') as stream:
            valid_project = tomllib.load(stream).get('project', {}).get('name') == 'zara-3.0'
    except (OSError, ValueError, tomllib.TOMLDecodeError):
        raise RuntimeError('PACKAGED_WORKSPACE_NOT_CONFIGURED') from None
    if not (valid_git and valid_source and valid_project):
        raise RuntimeError('PACKAGED_WORKSPACE_NOT_CONFIGURED')
    return workspace


def stop_owned(process):
    import psutil
    if process.poll() is not None: return
    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
        for child in reversed(children):
            try: child.kill()
            except psutil.NoSuchProcess: pass
        parent.kill()
        psutil.wait_procs(children + [parent], timeout=10)
    except psutil.NoSuchProcess: pass


def run_canary(package, output, *, live=True, entry_only=False):
    from playwright.sync_api import sync_playwright
    from core.paths import data_dir
    from core.lab_v1.providers.nvidia import NvidiaApiAdapter
    from core.lab_v1.providers.registry import default_registry
    from core.lab_v1.runtime import LabRuntime
    from core.lab_v1.store import LabStore
    from core.lab_v1.supervisor import AutonomySupervisor
    package, output = Path(package).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    home = Path(tempfile.gettempdir()) / 'zara-lab-canaries' / str(time.time_ns())
    home.mkdir(parents=True)
    (home / 'CANARY_ONLY').touch()
    (home / '.zara-smoke-runtime').touch()
    source_data = data_dir() / 'lab'
    dest = home / 'data/lab'
    dest.mkdir(parents=True)
    # Provider metadata is local evidence, not a credential.  Copy every
    # cached catalog used by the persisted Lab team so the isolated canary
    # measures the package instead of failing merely because its disposable
    # home has no discovery cache yet.
    copied = ['provider_health.json', 'nvidia_models.json', 'codex_models.json',
              'nine_router_models.json']
    # Entry canaries must start from a clean Lab database. Reusing a previous
    # owner/blocked mission makes admission fail with MISSION_BUSY and tests
    # the old fixture state instead of the packaged runtime.
    for name in copied:
        if (source_data / name).exists(): shutil.copy2(source_data / name, dest / name)
    credential = None if entry_only else NvidiaApiAdapter._load_credential(None)
    saved = {k: os.environ.get(k) for k in ('ZARA3_HOME', 'NVIDIA_API_KEY')}
    try:
        os.environ['ZARA3_HOME'] = str(home)
        if credential: os.environ['NVIDIA_API_KEY'] = credential
        if live:
            runtime = LabRuntime(LabStore(dest / 'zara_lab_v1.db'), default_registry(), memory_adapter=None)
            AutonomySupervisor(runtime).ensure_team()
    finally:
        for key, value in saved.items():
            if value is None: os.environ.pop(key, None)
            else: os.environ[key] = value
    env = dict(os.environ, ZARA_SMOKE_TEST='1', ZARA_LAB_LIVE_CANARY='1' if live else '0',
               ZARA_LAB_ENTRY_CANARY='1' if entry_only else '0', ZARA3_HOME=str(home))
    if entry_only: env.pop('NVIDIA_API_KEY', None)
    if credential: env['NVIDIA_API_KEY'] = credential
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    exe = packaged_paths(package)['EXE_SHA256']
    stdout_handle = (output / 'electron.stdout.log').open('wb')
    stderr_handle = (output / 'electron.stderr.log').open('wb')
    process = subprocess.Popen([str(exe), '--minimizada', '--remote-debugging-address=127.0.0.1',
        f'--remote-debugging-port={port}', f'--user-data-dir={home / "electron"}'],
        env=env, cwd=exe.parent, stdout=stdout_handle, stderr=stderr_handle,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    report = {'status': 'failed', 'live': live, 'entry_only': entry_only,
        'userdata': str(home), 'checks': {},
        'stage': 'STARTING_ELECTRON',
        'asar_sha256': digest(packaged_paths(package)['ASAR_SHA256']),
        'backend_sha256': digest(packaged_paths(package)['BACKEND_SHA256'])}
    if entry_only:
        report['autonomy_proven'] = False
        report['limitations'] = [
            'Supervisor paused by entry-only canary; autonomous mission execution is not proven.']
    page = None
    try:
        with sync_playwright() as pw:
            report['stage'] = 'CONNECTING_CDP'
            browser = None
            until = time.monotonic() + 90
            while time.monotonic() < until:
                if process.poll() is not None: raise RuntimeError('ELECTRON_EXITED_BEFORE_CDP')
                try:
                    browser = pw.chromium.connect_over_cdp(f'http://127.0.0.1:{port}', timeout=2000)
                    break
                except Exception: time.sleep(1)
            if browser is None: raise RuntimeError('CDP_TIMEOUT')
            page = browser.contexts[0].pages[0]
            report['stage'] = 'WAITING_PRELOAD'
            page.wait_for_function('!!window.zaraIPC?.labV1', timeout=90000)
            report['stage'] = 'WAITING_LAB_IPC'
            until = time.monotonic() + 90
            snap = {}
            while time.monotonic() < until:
                try:
                    snap = page.evaluate('window.zaraIPC.labV1.snapshot()')
                    if snap.get('success'): break
                except Exception: pass
                time.sleep(2)
            if not snap.get('success'): raise RuntimeError('PACKAGED_LAB_IPC_UNAVAILABLE')
            report['checks']['packaged_ipc'] = True
            if entry_only:
                report['stage'] = 'VERIFYING_PERSISTENT_WORKSPACE'
                policy = snap.get('autonomy_policy') or {}
                report['workspace'] = policy.get('workspace')
                report['supervisor_state'] = policy.get('background_task_state')
                workspace = inspect_entry_workspace(snap, dest / 'zara_lab_v1.db', home)
                report['workspace'] = str(workspace)
                report['checks'].update(workspace_persisted=True, workspace_valid=True,
                                        workspace_outside_mei=True, supervisor_paused=True)
            report['stage'] = 'OPENING_LAB_ROOM'
            page.locator('button').filter(has_text='ZARA Lab').first.click(timeout=30000)
            lab = page.get_by_role('dialog', name='ZARA Lab', exact=True)
            lab.wait_for(timeout=15000)
            report['stage'] = 'CAPTURING_LAB_ROOM'
            page.screenshot(path=str(output / 'lab-desktop.png'))
            report['checks']['lab_room_visible'] = True
            # The room existing is not sufficient: a fresh packaged runtime can
            # render the shell while a backend migration has already failed.
            # Fail closed on the concrete database error surface so a screenshot
            # cannot be promoted as a healthy Lab canary.
            if page.get_by_text('OperationalError:', exact=False).count():
                raise RuntimeError('PACKAGED_LAB_RUNTIME_ERROR')
            report['checks']['lab_runtime_healthy'] = True
            if live:
                report['stage'] = 'STARTING_REAL_MISSION'
                marker = 'ZARA_PACKAGED_AUTONOMY_OK'
                # Exercise the canonical renderer -> preload -> Electron -> IPC
                # path directly. The visual composer has two product entry
                # modes and can remain on the welcome shell in a fresh package;
                # using the exposed Lab autopilot API avoids making canary
                # success depend on a stale selector while still testing the
                # real frontend contract.
                started = page.evaluate(
                    "(objective) => window.zaraIPC.labV1.autopilot(objective)",
                    'Crie um documento de uma única linha contendo exatamente: ' + marker)
                if not started or started.get('success') is not True:
                    raise RuntimeError('PACKAGED_OWNER_ENTRY_NOT_ACCEPTED')
                until = time.monotonic() + (30 if entry_only else 330)
                report['stage'] = 'WAITING_REAL_MISSION'
                sid = None
                while time.monotonic() < until:
                    overview = page.evaluate('window.zaraIPC.labV1.snapshot()')
                    # The default snapshot represents one team. Owner missions may
                    # be created in another selected team, so inspect every room.
                    sessions = list(overview.get('sessions', []))
                    for team in overview.get('teams', []):
                        team_view = page.evaluate(
                            '(tid) => window.zaraIPC.labV1.snapshot(undefined, tid)', team['id'])
                        sessions.extend(team_view.get('sessions', []))
                    sid = next((s['id'] for s in sessions if marker in s['objective']), None)
                    if sid:
                        snap = page.evaluate('(sid) => window.zaraIPC.labV1.snapshot(sid)', sid)
                        state = (snap.get('session') or {}).get('state')
                        if entry_only or state in ('COMPLETED', 'BLOCKED', 'FAILED', 'CANCELLED'):
                            break
                    time.sleep(2)
                session = snap.get('session') or {}
                report['session_id'] = sid
                report['mission_state'] = session.get('state')
                report['runs'] = [{k: r.get(k) for k in ('id','provider_id','model','model_reported','state',
                    'input_tokens','output_tokens','duration_ms','cost_basis','provider_session_id')} for r in session.get('runs', [])]
                if entry_only:
                    # The entry canary pauses the consumer and supervisor. The
                    # accepted mission may remain queued or report a resource
                    # wait, but no provider Run may be created.
                    if not sid or session.get('state') not in ('QUEUED', 'WAITING_RESOURCE', 'BLOCKED'):
                        raise RuntimeError('PACKAGED_OWNER_ENTRY_NOT_QUEUED')
                    if session.get('runs'): raise RuntimeError('ENTRY_CANARY_PROVIDER_CALL_DETECTED')
                    cancelled = page.evaluate('(sid) => window.zaraIPC.labV1.cancelMission(sid)', sid)
                    if not cancelled.get('success'): raise RuntimeError('ENTRY_CANARY_CANCEL_FAILED')
                    report['checks'].update(owner_entry_queued=True, provider_calls_zero=True,
                                            owner_entry_cancelled=True)
                    report['mission_state'] = 'CANCELLED'
                    report['owner_touches'] = (session.get('autonomy') or {}).get('owner_touches')
                    page.screenshot(path=str(output / 'lab-entry-accepted.png'))
                else:
                    if session.get('state') != 'COMPLETED':
                        raise RuntimeError('PACKAGED_MISSION_NOT_COMPLETED')
                    mission = session.get('mission') or {}
                    if not all(s.get('verification', {}).get('verdict') == 'PASS' for s in mission.get('steps', [])):
                        raise RuntimeError('PACKAGED_VERIFICATION_MISSING')
                    store = LabStore(dest / 'zara_lab_v1.db')
                    with store._connect() as conn:
                        row = conn.execute('SELECT document FROM mission_action_requests WHERE session_id=?', (sid,)).fetchone()
                    request = json.loads(row[0])
                    target = Path(request['arguments']['path']).resolve()
                    if home.resolve() not in target.parents: raise RuntimeError('CANARY_SCOPE_ESCAPE')
                    content = target.read_text(encoding='utf-8')
                    if content.strip() != marker: raise RuntimeError('PACKAGED_DOCUMENT_CONTENT_MISMATCH')
                    report['checks'].update(real_team=True, hermes_write=True, independent_file_check=True)
                    report['file_sha256'] = hashlib.sha256(target.read_bytes()).hexdigest()
                    report['owner_touches'] = (session.get('autonomy') or {}).get('owner_touches')
                    page.screenshot(path=str(output / 'lab-completed.png'))
            lab.get_by_role('button', name='Ver participantes', exact=True).click()
            report['stage'] = 'CAPTURING_PARTICIPANTS'
            page.screenshot(path=str(output / 'lab-participants.png'))
            report['status'] = 'passed'
            report['stage'] = 'COMPLETE'
    except Exception as exc:
        # Provider output and credentials never enter error reports.
        report['error'] = type(exc).__name__ + ': ' + (str(exc) if str(exc).isupper() else 'CANARY_CHECK_FAILED')
    finally:
        if page is not None:
            try:
                page.screenshot(path=str(output / 'lab-failure.png'))
            except Exception:
                pass
        stop_owned(process)
        stdout_handle.close()
        stderr_handle.close()
        write_json(output / 'VALIDATION.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('package', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--read-only', action='store_true')
    parser.add_argument('--entry-only', action='store_true')
    args = parser.parse_args()
    result = run_canary(args.package, args.output, live=not args.read_only, entry_only=args.entry_only)
    print(json.dumps({'status': result['status'], 'error': result.get('error'), 'report': str(args.output / 'VALIDATION.json')}))
    raise SystemExit(0 if result['status'] == 'passed' else 1)
