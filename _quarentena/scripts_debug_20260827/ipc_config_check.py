import os

# Check IPC handlers for config file re-read patterns
with open('core/ipc_handlers.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()
    lines = content.split('\n')

# Look for config file reads
print("=== Config file reads in ipc_handlers.py ===")
for i, line in enumerate(lines, 1):
    if 'config' in line.lower() and 'json' in line.lower() and 'read' in line.lower():
        print(f"L{i}: {line.strip()[:120]}")

print("\n=== api_keys.json references ===")
for i, line in enumerate(lines, 1):
    if 'api_keys' in line.lower():
        print(f"L{i}: {line.strip()[:120]}")

print("\n=== Synchronous HTTP patterns ===")
for i, line in enumerate(lines, 1):
    if ('urllib' in line.lower() or 'requests' in line.lower()) and 'async' not in line.lower():
        print(f"L{i}: {line.strip()[:120]}")