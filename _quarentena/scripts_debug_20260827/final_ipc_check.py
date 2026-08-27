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

def extract_handler_map_keys():
    backend_file = r"core/ipc_handlers.py"
    with open(backend_file, 'r', encoding='utf-8') as f:
        content = f.read()
    pattern = r"'([^']+)':\s*self\.handle_"
    return set(re.findall(pattern, content))

def kebab_to_snake(s):
    return s.replace('-', '_')

frontend = extract_frontend_methods()
handler_map = extract_handler_map_keys()

frontend_snake = {kebab_to_snake(m) for m in frontend}

print("Frontend IPC calls (kebab-case):")
for m in sorted(frontend):
    print(f"  {m}")
print()

print("Frontend IPC calls (snake_case):")
for m in sorted(frontend_snake):
    print(f"  {m}")
print()

print("Handler map keys (snake_case):")
for m in sorted(handler_map):
    print(f"  {m}")
print()

print("Missing in handler map (frontend snake_case not in handler_map):")
missing = frontend_snake - handler_map
for m in sorted(missing):
    print(f"  {m}")
print()

print("Extra in handler map (not called by frontend):")
extra = handler_map - frontend_snake
for m in sorted(extra):
    print(f"  {m}")
print()

print(f"Summary:")
print(f"  Frontend total: {len(frontend)}")
print(f"  Handler map total: {len(handler_map)}")
print(f"  Missing: {len(missing)}")
print(f"  Extra: {len(extra)}")