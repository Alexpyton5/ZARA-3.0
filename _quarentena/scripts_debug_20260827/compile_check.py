import py_compile
import sys
import os

py_files = []
for root, dirs, files in os.walk('core'):
    if '.venv' in root or '_quarentena' in root:
        continue
    for f in files:
        if f.endswith('.py'):
            py_files.append(os.path.join(root, f))

for f in py_files:
    try:
        py_compile.compile(f, doraise=True)
        print(f'OK: {f}')
    except py_compile.PyCompileError as e:
        print(f'ERROR: {f}: {e}')