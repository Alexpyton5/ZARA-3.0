import re
import sys

frontend_file = r"frontend/src/preload.ts"

with open(frontend_file, 'r', encoding='utf-8') as f:
    content = f.read()

# Patterns for ipcRenderer.invoke and ipcRenderer.send
invoke_pattern = re.compile(r"ipcRenderer\.invoke\s*\(\s*'([^']+)'")
send_pattern = re.compile(r"ipcRenderer\.send\s*\(\s*'([^']+)'")

invocations = set(invoke_pattern.findall(content))
sends = set(send_pattern.findall(content))

frontend_calls = set()
frontend_calls.update(invocations)
frontend_calls.update(sends)

print("Frontend IPC calls (invoke and send):")
for call in sorted(frontend_calls):
    print(call)