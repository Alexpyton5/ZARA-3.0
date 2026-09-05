from pathlib import Path
from tools.quality_gate import read_baseline, collect_tests
from collections import Counter

root = Path('.')
baseline_ids = read_baseline(root / '.quality_gate_baseline.json')
current_exit, current_ids = collect_tests(root)

baseline_set = set(baseline_ids)
current_set = set(current_ids)

missing = sorted(baseline_set - current_set)
added = sorted(current_set - baseline_set)

# Group baseline tests by prefix
baseline_prefixes = Counter()
for test in baseline_ids:
    prefix = test.split('/')[1] if '/' in test else test
    baseline_prefixes[prefix] += 1

current_prefixes = Counter()
for test in current_ids:
    prefix = test.split('/')[1] if '/' in test else test
    current_prefixes[prefix] += 1

print("Baseline test counts by file (top 20):")
for k, v in baseline_prefixes.most_common(20):
    print(f"  {k}: {v}")

print("\nCurrent test counts by file (top 20):")
for k, v in current_prefixes.most_common(20):
    print(f"  {k}: {v}")

# Check IPC specifically
ipc_baseline = [t for t in baseline_ids if 'ipc' in t.lower() or 'IPC' in t]
ipc_current = [t for t in current_ids if 'ipc' in t.lower() or 'IPC' in t]

print(f"\nIPC tests in baseline: {len(ipc_baseline)}")
print(f"IPC tests in current: {len(ipc_current)}")

if ipc_baseline:
    print("IPC baseline tests:")
    for t in ipc_baseline[:10]:
        print(f"  - {t}")
    if len(ipc_baseline) > 10:
        print(f"  ... and {len(ipc_baseline)-10} more")

if ipc_current:
    print("IPC current tests:")
    for t in ipc_current[:10]:
        print(f"  - {t}")
    if len(ipc_current) > 10:
        print(f"  ... and {len(ipc_current)-10} more")