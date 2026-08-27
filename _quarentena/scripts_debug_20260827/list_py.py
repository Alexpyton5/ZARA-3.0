import os

py_files = []
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ('.venv', '.git', '__pycache__', '_quarentena', 'lixo')]
    for f in files:
        if f.endswith('.py'):
            full = os.path.join(root, f)
            rel = os.path.relpath(full, '.')
            try:
                size = os.path.getsize(full)
                py_files.append((size, rel))
            except:
                pass

py_files.sort(reverse=True)
print(f"Total .py files: {len(py_files)}")
print("\nTop 20 largest files:")
for size, f in py_files[:20]:
    print(f"  {size:>6} {f}")