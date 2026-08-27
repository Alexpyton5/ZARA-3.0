import re
import sys

def extract_frontend_keys():
    frontend_preload = r"frontend/src/preload.ts"
    with open(frontend_preload, 'r', encoding='utf-8') as f:
        content = f.read()
    # Pattern for ipcRenderer.invoke('key') and ipcRenderer.send('key')
    invoke_pattern = r"ipcRenderer\.invoke\(['\"]([^'\"]+)['\"]"
    send_pattern = r"ipcRenderer\.send\(['\"]([^'\"]+)['\"]"
    invoke_matches = re.findall(invoke_pattern, content)
    send_matches = re.findall(send_pattern, content)
    return set(invoke_matches + send_matches)

def extract_handler_map_keys():
    backend_file = r"core/ipc_handlers.py"
    with open(backend_file, 'r', encoding='utf-8') as f:
        content = f.read()
    # We look for the handler_map dictionary in the handle_message function.
    # The pattern: 'key': self.handle_...
    pattern = r"'([^']+)':\s*self\.handle_"
    return set(re.findall(pattern, content))

frontend_keys = extract_frontend_keys()
handler_keys = extract_handler_map_keys()

print("FRONTEND IPC KEYS (from preload.ts):")
for key in sorted(frontend_keys):
    print(f"  {key}")
print()

print("BACKEND HANDLER MAP KEYS (from ipc_handlers.py):")
for key in sorted(handler_keys):
    print(f"  {key}")
print()

missing_in_backend = frontend_keys - handler_keys
extra_in_backend = handler_keys - frontend_keys

print("MISSING IN BACKEND (frontend keys not handled):")
if missing_in_backend:
    for key in sorted(missing_in_backend):
        print(f"  {key}")
else:
    print("  (none)")
print()

print("EXTRA IN BACKEND (handler keys not called by frontend):")
if extra_in_backend:
    for key in sorted(extra_in_backend):
        print(f"  {key}")
else:
    print("  (none)")
print()

print(f"SUMMARY:")
print(f"  Frontend keys: {len(frontend_keys)}")
print(f"  Backend handler keys: {len(handler_keys)}")
print(f"  Missing in backend: {len(missing_in_backend)}")
print(f"  Extra in backend: {len(extra_in_backend)}")