import re
import sys

backend_file = r"core/ipc_handlers.py"

with open(backend_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Find all async def handle_* methods
pattern = r"async def handle_([a-zA-Z_][a-zA-Z0-9_]*)\("
matches = re.findall(pattern, content)

backend_methods = set(matches)
print("Backend IPC handlers:")
for m in sorted(backend_methods):
    print(m)
print(f"Total: {len(backend_methods)}")