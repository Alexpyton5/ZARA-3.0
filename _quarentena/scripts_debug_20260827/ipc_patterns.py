import re
with open('core/ipc_handlers.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()
# Count occurrences of common patterns
for pattern in ['def ', 'import ', 'api_key', 'token ', 'secret']:
    count = content.lower().count(pattern.lower())
    print(f'{pattern}: {count}')