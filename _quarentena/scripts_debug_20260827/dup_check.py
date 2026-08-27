import os
import re
from collections import defaultdict

# Get all .py files in core/actions/
action_files = []
for root, dirs, files in os.walk('core/actions'):
    if '.venv' in root or '_quarentena' in root:
        continue
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            rel = os.path.relpath(path, 'core/actions')
            action_files.append((rel, path))

# Read each file and extract first 100 lines as a "fingerprint"
patterns = defaultdict(list)
for rel, path in action_files:
    try:
        with open(path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()[:30]  # first 30 lines
            key = ''.join(lines).lower().strip()[:100]
            if key:
                patterns[key].append(rel)
    except:
        pass

# Find groups with same pattern
dupes = {k: v for k, v in patterns.items() if len(v) > 1}
print(f"Files: {len(action_files)}, Unique patterns: {len(patterns)}, Duplicated patterns: {len(dupes)}")
for pattern, files in list(dupes.items())[:10]:
    print(f"\nShared pattern (first 100 chars lowercased):")
    print(f"  {pattern[:80]}...")
    print(f"  Files: {files}")