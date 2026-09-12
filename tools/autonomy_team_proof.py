"""One real intent through the service, two NVIDIA calls, governed Hermes effect.

Uses a new proof database and copied health metadata. No production memory,
configuration, team or historical acceptance artifact is changed.
"""
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.lab_v1.autopilot import Autopilot
from core.lab_v1.providers.nvidia import NvidiaApiAdapter
from core.lab_v1.providers.registry import ProviderRegistry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.service import LabV1Service
from core.lab_v1.store import LabStore
from core.paths import data_dir


async def main():
    target = ROOT / 'artifacts' / 'autonomy-one-shot' / ('team-proof-' + str(time.time_ns()))
    target.mkdir(parents=True)
    health = data_dir() / 'lab' / 'provider_health.json'
    (target / 'health.json').write_bytes(health.read_bytes())
    registry = ProviderRegistry(target / 'health.json')
    registry.register(NvidiaApiAdapter())
    store = LabStore(target / 'lab.db')
    runtime = LabRuntime(store, registry, memory_adapter=None)
    engine = Autopilot(runtime, root=target / 'missions')
    service = LabV1Service()
    service._runtime, service._store, service._autopilot = runtime, store, engine
    started = await service.start_autopilot('Produza um documento curto explicando verificacao independente de arquivos. Inclua a frase ZARA_AUTOPILOT_OK.')
    if not started.get('success'):
        (target / 'result.json').write_text(json.dumps(started, indent=2))
        print(json.dumps({'state': 'BLOCKED', 'report': str(target / 'result.json')}))
        return 1
    sid = started['session_id']
    result = await service.run_autopilot(sid)
    runs = [run.to_dict() for run in store.list_runs(sid)]
    result.update(runs=runs, database=str(store.db_path), agents=[a.to_dict() for a in store.list_agents()],
                  real_call_count=len(runs), memory_adapter=None, packaged_electron='NOT_TESTED')
    with store._connect() as conn:
        result['actions'] = [json.loads(row[0]) for row in conn.execute('SELECT document FROM mission_action_results')]
    result['literal_marker_verified'] = False
    metrics = engine.metrics(sid)
    artifact = Path(metrics['target'])
    if artifact.is_file():
        content = artifact.read_bytes()
        result['artifact_sha256'] = hashlib.sha256(content).hexdigest()
        result['literal_marker_verified'] = b'ZARA_AUTOPILOT_OK' in content
    (target / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'state': result.get('state'), 'calls': len(runs),
                      'marker': result['literal_marker_verified'], 'report': str(target / 'result.json')}))
    return 0 if result.get('success') and result['literal_marker_verified'] else 1


if __name__ == '__main__':
    raise SystemExit(asyncio.run(main()))
