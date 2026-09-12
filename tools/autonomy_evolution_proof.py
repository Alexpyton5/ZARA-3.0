"""Run the reviewed memory repair through real Astra, Harness/NVIDIA and Hermes.

Uses an isolated Lab database but deliberately promotes the verified, narrowly
catalogued repair to this authorized workspace. Does not activate a package.
"""
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.paths import data_dir
from core.lab_v1.providers.registry import ProviderRegistry, default_registry
from core.lab_v1.runtime import LabRuntime
from core.lab_v1.store import LabStore
from core.lab_v1.supervisor import AutonomySupervisor
from core.lab_v1.evolution import EvolutionEngine


def main():
    folder = ROOT / 'artifacts/autonomy-one-shot' / ('evolution-proof-' + str(time.time_ns()))
    folder.mkdir(parents=True)
    (folder / 'health.json').write_bytes((data_dir() / 'lab/provider_health.json').read_bytes())
    registry = ProviderRegistry(folder / 'health.json')
    defaults = default_registry()
    for provider in defaults.list_providers(): registry.register(defaults.get(provider.id))
    store = LabStore(folder / 'lab.db')
    runtime = LabRuntime(store, registry, memory_adapter=None)
    AutonomySupervisor(runtime).ensure_team()
    engine = EvolutionEngine(runtime, ROOT)
    start = engine.observe_and_plan()
    if not start.get('session_id'):
        print(json.dumps(start)); return 1
    sid = start['session_id']
    (folder / 'START.json').write_text(json.dumps({'session_id': sid, 'state': 'PLANNED'}), encoding='utf-8')
    print(json.dumps({'session_id': sid, 'report_directory': str(folder)}), flush=True)
    result = engine.run(sid)
    result.update(runs=[r.to_dict() for r in store.list_runs(sid)],
        agents=[a.to_dict() for a in store.list_agents()], runtime_canary='NOT_RUN', package_activation='NOT_RUN')
    (folder / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'state': result['state'], 'blocker': result.get('blocker'), 'runs': len(result['runs']), 'report': str(folder / 'result.json')}))
    return 0 if result['success'] else 1


if __name__ == '__main__': raise SystemExit(main())
