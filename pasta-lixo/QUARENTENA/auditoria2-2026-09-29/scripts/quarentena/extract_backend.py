import re
import sys

backend_path = sys.argv[1]
with open(backend_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find all async def handle_* functions
# Pattern: async def handle_([a-zA-Z0-9_]+)\s*\(
pattern = r'async def handle_([a-zA-Z0-9_]+)\s*\('
matches = re.findall(pattern, content)
backend_handlers = set()
for match in matches:
    # Convert function name to IPC string: remove 'handle_', replace underscores with hyphens
    func_name = match[0]
    ipc_string = func_name.replace('handle_', '').replace('_', '-')
    backend_handlers.add(ipc_string)

print('Backend IPC handlers (derived from function names):')
for handler in sorted(backend_handlers):
    print(handler)
EOF