import re
import sys

frontend_preload = r"frontend/src/preload.ts"

with open(frontend_preload, 'r', encoding='utf-8') as f:
    content = f.read()

# Find all ipcRenderer.invoke('method', ...) and ipcRenderer.send('method', ...)
invoke_pattern = r"ipcRenderer\.invoke\(['\"]([^'\"]+)['\"]"
send_pattern = r"ipcRenderer\.send\(['\"]([^'\"]+)['\"]"

invoke_matches = re.findall(invoke_pattern, content)
send_matches = re.findall(send_pattern, content)

frontend_methods = set(invoke_matches + send_matches)
print("Frontend IPC methods:")
for m in sorted(frontend_methods):
    print(m)
print(f"Total: {len(frontend_methods)}")