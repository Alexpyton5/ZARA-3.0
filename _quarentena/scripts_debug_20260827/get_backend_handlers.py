import re

backend_file = r"core/ipc_handlers.py"
with open(backend_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

handler_names = []
pattern = re.compile(r"^\s*async def handle_(\w+)\\(self, msg: IPCMessage\\):")

for line in lines:
    match = pattern.match(line)
    if match:
        handler_names.append(match.group(1))

print("Backend IPC handler names (after 'handle_'):")
for name in sorted(handler_names):
    print(f"  {name}")
print(f"\nTotal backend handlers: {len(handler_names)}")