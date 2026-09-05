import os
for root, dirs, files in os.walk('core'):
    if '.venv' in root or '_quarentena' in root:
        continue
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            size = os.path.getsize(path)
            if size > 10000:
                print(f'{size:>6} bytes: {os.path.relpath(path)}')