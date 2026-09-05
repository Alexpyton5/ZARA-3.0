import re
import sys

def extract_frontend_calls(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Pattern to match ipcRenderer.invoke or ipcRenderer.send with a string argument
    # We capture the string inside the quotes (either single or double)
    pattern = r'ipcRenderer\.(invoke|send)\s*\(\s*[\'"]([^\'"]+)[\'"]'
    matches = re.findall(pattern, content)
    calls = set()
    for match in matches:
        calls.add(match[1])  # match[1] is the string inside the quotes
    return calls

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('Usage: python extract_frontend.py <path_to_preload.ts>')
        sys.exit(1)
    calls = extract_frontend_calls(sys.argv[1])
    for call in sorted(calls):
        print(call)
