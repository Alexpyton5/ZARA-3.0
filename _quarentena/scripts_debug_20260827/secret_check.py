import os, re

patterns = ['api_key', 'secret', 'password', 'token', 'key']

for pattern in patterns:
    count = 0
    matches = []
    for root, dirs, files in os.walk('core'):
        if '.venv' in root or '_quarentena' in root:
            continue
        for f in files:
            if f.endswith('.py'):
                try:
                    with open(os.path.join(root, f), 'r', encoding='utf-8', errors='ignore') as fh:
                        for i, line in enumerate(fh, 1):
                            if pattern.lower() in line.lower():
                                count += 1
                                if len(matches) < 5:
                                    matches.append(f'{os.path.relpath(os.path.join(root, f), "core")}:{i}:{line.strip()[:80]}')
                except:
                    pass
    print(f'{pattern}: {count} files with matches')
    for m in matches[:3]:
        print(f'  {m}')