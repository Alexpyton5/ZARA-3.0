import re
import sys

with open(r"C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\frontend\src\preload.ts", "r", encoding="utf-8") as f:
    content = f.read()

# Find all ipcRenderer.invoke and ipcRenderer.send calls
pattern = r"ipcRenderer\.(invoke|send)\s*\(\s*['\"]([^'\"]+)['\"]"
matches = re.findall(pattern, content)
print("Frontend IPC calls:")
for call_type, name in matches:
    print(f"{call_type}: {name}")