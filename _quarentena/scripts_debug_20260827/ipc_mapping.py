import re

def extract_frontend_methods():
    frontend_preload = r"frontend/src/preload.ts"
    with open(frontend_preload, 'r', encoding='utf-8') as f:
        content = f.read()
    invoke_pattern = r"ipcRenderer\.invoke\(['\"]([^'\"]+)['\"]"
    send_pattern = r"ipcRenderer\.send\(['\"]([^'\"]+)['\"]"
    invoke_matches = re.findall(invoke_pattern, content)
    send_matches = re.findall(send_pattern, content)
    return set(invoke_matches + send_matches)

def extract_backend_methods():
    backend_file = r"core/ipc_handlers.py"
    with open(backend_file, 'r', encoding='utf-8') as f:
        content = f.read()
    pattern = r"async def handle_([a-zA-Z_][a-zA-Z0-9_]*)\("
    matches = re.findall(pattern, content)
    return set(matches)

def kebab_to_snake(s):
    return s.replace('-', '_')

frontend = extract_frontend_methods()
backend = extract_backend_methods()

frontend_snake = {kebab_to_snake(m) for m in frontend}

print("Frontend methods (kebab-case):")
for m in sorted(frontend):
    print(f"  {m}")
print()

print("Frontend methods (snake_case):")
for m in sorted(frontend_snake):
    print(f"  {m}")
print()

print("Backend handlers (snake_case):")
for m in sorted(backend):
    print(f"  {m}")
print()

print("Missing in backend (frontend snake_case not in backend):")
missing = frontend_snake - backend
for m in sorted(missing):
    print(f"  {m}")
print()

print("Extra in backend (not called by frontend):")
extra = backend - frontend_snake
for m in sorted(extra):
    print(f"  {m}")
print()

print(f"Summary:")
print(f"  Frontend total: {len(frontend)}")
print(f"  Backend total: {len(backend)}")
print(f"  Missing in backend: {len(missing)}")
print(f"  Extra in backend: {len(extra)}")