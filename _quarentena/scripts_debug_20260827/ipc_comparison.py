import re
import sys

# Read frontend file
frontend_path = r"frontend/src/preload.ts"
with open(frontend_path, 'r', encoding='utf-8') as f:
    frontend_content = f.read()

# Extract ipcRenderer.invoke and ipcRenderer.send calls
invoke_pattern = re.compile(r"ipcRenderer\\.invoke\\s*\\(\\s*'([^']+)'")
send_pattern = re.compile(r"ipcRenderer\\.send\\s*\\(\\s*'([^']+)'")
frontend_invoke = set(invoke_pattern.findall(frontend_content))
frontend_send = set(send_pattern.findall(frontend_content))
frontend_calls = frontend_invoke.union(frontend_send)

# Read backend file
backend_path = r"core/ipc_handlers.py"
with open(backend_path, 'r', encoding='utf-8') as f:
    backend_content = f.read()

# Extract handler names: look for lines like "async def handle_<name>(self, msg: IPCMessage):"
handler_pattern = re.compile(r"^\\s*async def handle_(\\w+)\\(self, msg: IPCMessage\\):", re.MULTILINE)
backend_handlers = set(handler_pattern.findall(backend_content))

# Output results
print("=== FRONTEND IPC CALLS (invoke and send) ===")
for call in sorted(frontend_calls):
    print(f"  {call}")

print("\\n=== BACKEND HANDLER NAMES (after 'handle_') ===")
for handler in sorted(backend_handlers):
    print(f"  {handler}")

print("\\n=== MISSING IN BACKEND (frontend calls not handled) ===")
missing = frontend_calls - backend_handlers
if missing:
    for call in sorted(missing):
        print(f"  {call}")
else:
    print("  (none)")

print("\\n=== EXTRA IN BACKEND (handlers without frontend call) ===")
extra = backend_handlers - frontend_calls
if extra:
    for handler in sorted(extra):
        print(f"  {handler}")
else:
    print("  (none)")