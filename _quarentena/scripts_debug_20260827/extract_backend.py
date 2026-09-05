import re
import sys

def extract_backend_handlers(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    handlers = set()
    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith('async def handle_'):
            # Extract the function name
            # Example: async def handle_voice_mic_chunk(self, msg: IPCMessage):
            # We want to get 'voice_mic_chunk'
            match = re.match(r'async def handle_([a-zA-Z0-9_]+)\s*\(', stripped)
            if match:
                func_name = match.group(1)
                # Convert to IPC string: replace underscores with hyphens
                ipc_string = func_name.replace('_', '-')
                handlers.add(ipc_string)
    return handlers

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python extract_backend.py <path_to_ipc_handlers.py>')
        sys.exit(1)
    handlers = extract_backend_handlers(sys.argv[1])
    for handler in sorted(handlers):
        print(handler)
EOF