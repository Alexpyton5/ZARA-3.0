import re
import sys

def main():
    with open(r"C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\core\ipc_handlers.py", "r", encoding="utf-8") as f:
        content = f.read()
    # Find all handle_* functions
    pattern = r'def (handle_[a-z_]+)\s*\\(\s*self,\s*msg: IPCMessage\s*\\):'
    matches = re.findall(pattern, content)
    print('Backend IPC handlers:')
    for m in matches:
        name = m.replace('handle_', '')
        print(f'handle: {name}')

if __name__ == '__main__':
    main()