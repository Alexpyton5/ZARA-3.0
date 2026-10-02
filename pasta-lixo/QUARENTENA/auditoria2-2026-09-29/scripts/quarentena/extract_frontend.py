import re
import sys

frontend_path = sys.argv[1]
with open(frontend_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find all ipcRenderer.invoke and ipcRenderer.send calls
# Pattern: ipcRenderer.(invoke|send)('method', ...) or ipcRenderer.(invoke|send)("method", ...)
pattern = r'ipcRenderer\.(invoke|send)\s*\(\s*[\'"]([^\'"]+)[\'"]'
matches = re.findall(pattern, content)
frontend_calls = set()
for match in matches:
    frontend_calls.add(match[1])

print('Frontend IPC calls:')
for call in sorted(frontend_calls):
    print(call)
EOF