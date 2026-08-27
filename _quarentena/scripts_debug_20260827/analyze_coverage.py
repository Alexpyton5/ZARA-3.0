from pathlib import Path
from tools.quality_gate import read_baseline, collect_tests

root = Path('.')
baseline_ids = read_baseline(root / '.quality_gate_baseline.json')
current_exit, current_ids = collect_tests(root)

baseline_set = set(baseline_ids)
current_set = set(current_ids)

missing = sorted(baseline_set - current_set)
added = sorted(current_set - baseline_set)

print(f'Baseline: {len(baseline_ids)} tests')
print(f'Current: {len(current_ids)} tests')
print(f'Missing: {len(missing)} tests')
print(f'Added: {len(added)} tests')

# Show missing categories
if missing:
    # Group by test file prefix
    from collections import Counter
    prefixes = [m.split('/')[1].split('::')[0] for m in missing]
    file_counts = Counter(prefixes)
    print(f'\nMissing by file:')
    for k, v in file_counts.most_common(20):
        print(f'  {k}: {v}')

if added:
    from collections import Counter
    prefixes = [m.split('/')[1].split('::')[0] for m in added]
    file_counts = Counter(prefixes)
    print(f'\nAdded by file:')
    for k, v in file_counts.most_common(20):
        print(f'  {k}: {v}')