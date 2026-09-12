"""One objective via the real public Lab facade, then read-only observation.

No fake adapter, worker output injection, or manual step execution. User data is
copied with SQLite backup so acceptance does not consume the owner's missions.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except AttributeError:
    pass

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OBJECTIVE = (
    'Corrija no source candidato da ZARA o problema real em core/lab_v1/feedback_inbox.py: '
    'looks_like_product_criticism registra elogios como "A ZARA está sem erro e sem falha." '
    'e "A ZARA não está lenta, está funcionando bem." como críticas. Isso cria trabalho desnecessário. '
    'Investigue a causa, implemente uma correção pequena preservando reclamações reais e frases mistas, '
    'execute testes reais antes/depois, obtenha revisão independente e construa a candidata testada. '
    'Trabalhe somente na cópia isolada, preserve CURRENT e rollback.'
)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding='utf-8')


def prepare(output, runtime_root):
    from core.paths import data_dir
    source = data_dir() / 'lab'
    runtime_root = Path(runtime_root).resolve()
    runtime_root.mkdir(parents=True, exist_ok=True)
    if not runtime_root.is_dir() or runtime_root.is_symlink():
        raise RuntimeError('RUNTIME_ROOT_INVALID')
    home = Path(tempfile.mkdtemp(prefix='zara-real-source-', dir=runtime_root))
    target = home / 'data/lab'
    target.mkdir(parents=True)
    with sqlite3.connect(f'file:{(source / "zara_lab_v1.db").as_posix()}?mode=ro', uri=True) as src:
        with sqlite3.connect(target / 'zara_lab_v1.db') as dst:
            src.backup(dst)
    for name in ('provider_health.json', 'codex_models.json', 'nvidia_models.json'):
        if (source / name).is_file():
            shutil.copy2(source / name, target / name)
    with sqlite3.connect(target / 'zara_lab_v1.db') as conn:
        policy = json.loads(conn.execute('SELECT document FROM lab_autonomy_policy WHERE id=1').fetchone()[0])
        # Run this one requested mission; don't initiate unrelated paid model work
        # while this disposable acceptance process is alive.
        policy.update(enabled=False, background_enabled=True, mission_entry_enabled=True, workspace=str(ROOT))
        conn.execute('UPDATE lab_autonomy_policy SET document=? WHERE id=1', (json.dumps(policy),))
    record = {'home': str(home), 'runtime_root': str(runtime_root), 'output': str(output),
              'public_entry': 'LabV1Service.start_autopilot',
              'objective': OBJECTIVE, 'state': 'PREPARED', 'provider_calls': 0}
    write(output / 'PROOF_SESSION.json', record)
    return record


async def run(record):
    runtime_root = Path(record['runtime_root']).resolve(strict=True)
    home = Path(record['home']).resolve(strict=True)
    try:
        home.relative_to(runtime_root)
    except ValueError as exc:
        raise RuntimeError('PREPARED_HOME_OUTSIDE_RUNTIME_ROOT') from exc
    process_temp = home / 'process-tmp'
    process_temp.mkdir(exist_ok=True)
    os.environ['ZARA3_HOME'] = record['home']
    os.environ['TEMP'] = str(process_temp)
    os.environ['TMP'] = str(process_temp)
    from core.lab_v1.service import LabV1Service
    from core.lab_v1.store import LabStore
    from core.lab_v1.real_work_contract import validate_production_proof
    from core.lab_v1.providers.registry import default_registry
    service = LabV1Service()
    store = LabStore(Path(record['home']) / 'data/lab/zara_lab_v1.db')
    output = Path(record['output'])
    if record.get('resume_existing'):
        sid = record.get('session_id')
        if not sid:
            raise RuntimeError('RESUME_SESSION_ID_REQUIRED')
        started = await service.resume_source_autopilot(sid)
    else:
        # Public cancellations affect only pre-existing missions in the disposable DB.
        with store._connect() as conn:
            previous = [json.loads(row[0]) for row in conn.execute('SELECT document FROM mission_controls')]
        for item in previous:
            if item['state'] not in ('COMPLETED', 'FAILED', 'CANCELLED'):
                await service.cancel_autopilot(item['session_id'])
        started = await service.start_autopilot(record['objective'])
    record.update(entry_result=started, session_id=started.get('session_id', record.get('session_id')), state=started.get('state'))
    write(output / 'PROOF_SESSION.json', record)
    print(json.dumps(started, ensure_ascii=False), flush=True)
    if not started.get('success'):
        raise RuntimeError('PUBLIC_ENTRY_FAILED: ' + str(started))
    sid = started['session_id']
    until = time.monotonic() + 2400
    last = None
    try:
        while time.monotonic() < until:
            # Read evidence; supervisor alone advances the mission.
            with store._connect() as conn:
                mission = json.loads(conn.execute('SELECT document FROM mission_controls WHERE session_id=?', (sid,)).fetchone()[0])
                metrics = json.loads(conn.execute('SELECT document FROM mission_autonomy WHERE session_id=?', (sid,)).fetchone()[0])
            runs = store.list_runs(sid)
            current = (mission['state'], tuple((s['id'], s['status']) for s in mission['steps']), len(runs))
            if current != last:
                last = current
                print(json.dumps({'state': current[0], 'steps': current[1], 'runs': len(runs)}, ensure_ascii=False), flush=True)
                record.update(state=mission['state'], provider_calls=len(runs), mission=mission, autonomy=metrics,
                              runs=[r.to_dict() for r in runs])
                write(output / 'PROOF_SESSION.json', record)
            if mission['state'] in ('COMPLETED', 'FAILED', 'CANCELLED', 'BLOCKED_NEEDS_OWNER'):
                if mission['state'] != 'COMPLETED':
                    raise RuntimeError('MISSION_NOT_COMPLETED: ' + str(mission.get('blocker')))
                if not metrics.get('final_report_automatic'):
                    await asyncio.sleep(1)
                    continue
                proof = json.loads(Path(metrics['proof_path']).read_text(encoding='utf-8'))
                if any(p.get('status') == 'NOT_PROVEN' for p in proof['production_evidence']):
                    raise RuntimeError('REAL_PROVIDER_EVIDENCE_NOT_PROVEN')
                if proof['owner_touches'] != 1 or len({r.agent_id for r in runs}) < 3:
                    raise RuntimeError('REAL_TEAM_OR_AUTONOMY_MISSING')
                candidate = proof.get('source_work', {}).get('candidate_build', {})
                source_work = proof.get('source_work', {})
                preservation = source_work.get('review_preservation_evidence', {})
                preservation_receipts = [artifact for artifact in store.list_artifacts(sid)
                                         if artifact.kind == 'LOCAL_PRESERVATION']
                if (preservation.get('status') != 'NO_PROMOTION'
                        or preservation.get('matches') is not True
                        or len(preservation_receipts) < 2
                        or not source_work.get('review_preservation_receipt_id')):
                    raise RuntimeError('LOCAL_PRESERVATION_PROOF_MISSING')
                required_files = ('package', 'exe_path', 'asar_path', 'backend_path', 'canary_report')
                if (candidate.get('status') != 'PACKAGED_RUNTIME_CANDIDATE'
                        or candidate.get('candidate_status') != 'VERIFIED_AWAITING_APPROVAL'
                        or candidate.get('desktop_package') is not True
                        or candidate.get('activation') != 'FORBIDDEN_UNTIL_CANONICAL_SOURCE_PROMOTION_AND_REBUILD'
                        or any(not Path(candidate.get(key, '')).exists() for key in required_files)):
                    raise RuntimeError('DESKTOP_CANDIDATE_PROOF_MISSING')
                source_builds = [artifact for artifact in store.list_artifacts(sid)
                                 if artifact.kind == 'SOURCE_BUILD']
                if len(source_builds) != 1 or json.loads(source_builds[0].body) != candidate:
                    raise RuntimeError('DESKTOP_CANDIDATE_RECEIPT_UNBOUND')
                registry = default_registry()
                for provider in {r.provider_id for r in runs}:
                    completed = [r for r in runs if r.provider_id == provider and r.state.value == 'COMPLETED']
                    validate_production_proof({'run_ids': [r.id for r in completed]}, runs=completed, adapter=registry.get(provider))
                write(output / 'REAL_WORK_PROOF.json', proof)
                record.update(state='PASSED', proof_path=str(output / 'REAL_WORK_PROOF.json'))
                write(output / 'PROOF_SESSION.json', record)
                print('REAL_SOURCE_MISSION_PASSED', flush=True)
                return
            await asyncio.sleep(3)
        raise TimeoutError('REAL_MISSION_DEADLINE')
    finally:
        await service.stop_background()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--prepared', type=Path)
    parser.add_argument('--resume-existing', action='store_true')
    parser.add_argument('--runtime-root', type=Path, default=Path('D:/ZARA-LAB-WORK'))
    args = parser.parse_args()
    record = (json.loads(args.prepared.read_text(encoding='utf-8')) if args.prepared
              else prepare(args.output.resolve(), args.runtime_root))
    if args.resume_existing:
        record['resume_existing'] = True
    if args.prepare_only:
        print(json.dumps(record, ensure_ascii=False)); return
    asyncio.run(run(record))


if __name__ == '__main__':
    main()
