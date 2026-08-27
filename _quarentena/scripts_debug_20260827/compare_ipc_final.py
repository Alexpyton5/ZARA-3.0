import re
import subprocess
import sys

def get_frontend_calls():
    frontend_file = r"frontend/src/preload.ts"
    with open(frontend_file, 'r', encoding='utf-8') as f:
        content = f.read()
    invoke_pattern = re.compile(r"ipcRenderer\.invoke\s*\(\s*'([^']+)'")
    send_pattern = re.compile(r"ipcRenderer\.send\s*\(\s*'([^']+)'")
    invokes = set(invoke_pattern.findall(content))
    sends = set(send_pattern.findall(content))
    return invokes.union(sends)

def get_backend_handlers():
    backend_file = r"core/ipc_handlers.py"
    with open(backend_file, 'r', encoding='utf-8') as f:
        content = f.read()
    pattern = re.compile(r"^async def handle_(\w+)\\(self, msg: IPCMessage\\):", re.MULTILINE)
    return set(pattern.findall(content))

frontend_calls = get_frontend_calls()
backend_handlers = get_backend_handlers()

missing_in_backend = frontend_calls - backend_handlers
extra_in_backend = backend_handlers - frontend_calls

print("=== FRONTEND IPC CALLS (invoke and send) ===")
for call in sorted(frontend_calls):
    print(f"  {call}")

print("\n=== BACKEND HANDLER NAMES (after 'handle_') ===")
for handler in sorted(backend_handlers):
    print(f"  {handler}")

print("\n=== MISSING IN BACKEND (frontend calls not handled) ===")
if missing_in_backend:
    for call in sorted(missing_in_backend):
        print(f"  {call}")
else:
    print("  (none)")

print("\n=== EXTRA IN BACKEND (handlers without frontend call) ===")
if extra_in_backend:
    for handler in sorted(extra_in_backend):
        print(f"  {handler}")
else:
    print("  (none)")