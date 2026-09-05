import os

# Check model_router.py for config reads
with open('core/model_router.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()
    lines = content.split('\n')

print("=== api_keys.json references in model_router.py ===")
for i, line in enumerate(lines, 1):
    if 'api_keys' in line.lower():
        print(f"L{i}: {line.strip()[:120]}")

print("\n=== Synchronous HTTP patterns in model_router.py ===")
for i, line in enumerate(lines, 1):
    if ('urllib' in line.lower() or 'requests' in line.lower()) and 'async' not in line.lower():
        print(f"L{i}: {line.strip()[:120]}")