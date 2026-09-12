"""Real packaged Electron IPC/UI canary in disposable userdata. No product data mutations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.build_current import packaged_paths, digest, write_json


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
    copied = ['provider_health.json', 'nvidia_models.json', 'codex_models.json']
    if entry_only: copied.append('zara_lab_v1.db')
    for name in copied:
        if (source_data / name).exists(): shutil.copy2(source_data / name, dest / name)
    credential = NvidiaApiAdapter._load_credential(None)
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
    if credential: env['NVIDIA_API_KEY'] = credential
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
    exe = packaged_paths(package)['EXE_SHA256']
    process = subprocess.Popen([str(exe), '--minimizada', '--remote-debugging-address=127.0.0.1',
        f'--remote-debugging-port={port}', f'--user-data-dir={home / "electron"}'],
        env=env, cwd=exe.parent, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    report = {'status': 'failed', 'live': live, 'userdata': str(home), 'checks': {},
        'stage': 'STARTING_ELECTRON',
        'asar_sha256': digest(packaged_paths(package)['ASAR_SHA256']),
        'backend_sha256': digest(packaged_paths(package)['BACKEND_SHA256'])}
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
            report['stage'] = 'OPENING_LAB_ROOM'
            page.locator('button').filter(has_text='ZARA Lab').first.click(timeout=30000)
            lab = page.get_by_role('dialog', name='ZARA Lab', exact=True)
            lab.wait_for(timeout=15000)
            report['stage'] = 'CAPTURING_LAB_ROOM'
            page.screenshot(path=str(output / 'lab-desktop.png'))
            report['checks']['lab_room_visible'] = True
            if live:
                report['stage'] = 'STARTING_REAL_MISSION'
                lab.get_by_role('button', name='Nova missão', exact=True).click()
                marker = 'ZARA_PACKAGED_AUTONOMY_OK'
                lab.get_by_role('textbox', name='Mensagem para a equipe').fill(
                    'Crie um documento de uma única linha contendo exatamente: ' + marker)
                lab.get_by_role('button', name='Enviar mensagem', exact=True).click()
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
                    if not sid or session.get('state') != 'QUEUED':
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
        stop_owned(process)
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
