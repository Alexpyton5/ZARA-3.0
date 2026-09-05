import re
with open(r"C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\core\ipc_handlers.py", "r", encoding="utf-8") as f:
    lines = f.readlines()
handlers = []
for line in lines:
    if line.strip().startswith("async def handle_"):
        # extract the function name
        # line example: "    async def handle_voice_mic_chunk(self, msg: IPCMessage):"
        # we want the part after "handle_"
        match = re.search(r"async def handle_([a-z_]+)\s*\(", line)
        if match:
            handlers.append(match.group(1))
print("Backend IPC handlers:")
for h in handlers:
    print(f"handle: {h}")