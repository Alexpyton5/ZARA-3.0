import re

# Read the backend file
with open(r'core/ipc_handlers.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find all lines that start with optional whitespace, then 'async def handle_', then capture the handler name
# The pattern: ^\s*async def handle_(\w+)\\(self, msg: IPCMessage\\):
pattern = re.compile(r'^\s*async def handle_(\w+)\\(self, msg: IPCMessage\\):', re.MULTILINE)
handler_names = pattern.findall(content)

print("Backend handler names (after 'handle_'):")
for name in sorted(handler_names):
    print(f"  {name}")
print(f"\nTotal backend handlers: {len(handler_names)}")