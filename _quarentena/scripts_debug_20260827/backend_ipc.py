import re
import sys

backend_file = r"core/ipc_handlers.py"

with open(backend_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern for async def handle_<name>(self, msg: IPCMessage):
pattern = re.compile(r"^async def handle_(\w+)\\(self, msg: IPCMessage\\):", re.MULTILINE)
handler_names = set(pattern.findall(content))

print("Backend IPC handler names (without 'handle_'):")
for name in sorted(handler_names):
    print(name)
print(f"\nTotal backend handlers: {len(handler_names)}")