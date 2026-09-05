import re
import sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

# This pattern matches ipcRenderer.invoke or ipcRenderer.send followed by a string in quotes
pattern = r'ipcRenderer\.(invoke|send)\s*\(\s*[\'"]([^\'"]+)[\'"]'
matches = re.findall(pattern, content)
calls = set(match[1] for match in matches)

for call in sorted(calls):
    print(call)
EOF