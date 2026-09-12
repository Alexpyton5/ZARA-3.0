"""Independent, bounded behavior checks against an explicitly supplied candidate file.

This runner is bundled as data for the external project Python. It never uses Alex's memory database.
"""
import importlib.util
import gc
import json
from pathlib import Path
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor


def check(source, workspace):
    sys.path.insert(0, str(workspace))
    spec = importlib.util.spec_from_file_location('zara_candidate_user_memory', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='zara-memory-canary-') as directory:
        db = Path(directory) / 'facts.db'
        first, second = module.UserMemoryCore(db), module.UserMemoryCore(db)
        original = first.add('Arquivo verificado', source='zara_lab', ref='lab:mission:evidence')
        replay = second.add('Arquivo verificado', source='zara_lab', ref='lab:mission:evidence')
        checks = {'crash_replay_idempotent': original['id'] == replay['id']}
        a = first.add('Preferencia manual'); b = second.add('Preferencia manual')
        checks['manual_behavior_preserved'] = a['id'] != b['id']
        def add(index):
            return (first if index % 2 else second).add('Procedimento verificado', source='zara_lab', ref='lab:concurrent:evidence')['id']
        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(add, range(6)))
        checks['concurrent_replay_idempotent'] = len(set(ids)) == 1
        # The legacy memory class uses SQLite transaction context managers;
        # collect their closed transactions before removing this disposable Windows database.
        del first, second
        gc.collect()
        return {'passed': all(checks.values()), 'checks': checks, 'database': 'DISPOSABLE'}


if __name__ == '__main__':
    result = check(Path(sys.argv[1]), Path(sys.argv[2]))
    print(json.dumps(result))
    raise SystemExit(0 if result['passed'] else 1)
