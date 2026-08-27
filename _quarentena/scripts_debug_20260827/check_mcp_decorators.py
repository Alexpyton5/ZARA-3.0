import sys
sys.path.insert(0, '.')
import os
ACTIONS_DIR = os.path.join(os.path.dirname(__file__), 'core', 'actions')
print(f"Checking {ACTIONS_DIR} for MCP action decorators...")
for filename in os.listdir(ACTIONS_DIR):
    if not filename.endswith('.py') or filename == '__init__.py':
        continue
    filepath = os.path.join(ACTIONS_DIR, filename)
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        if '@action' in content and 'mcp_' in content:
            print(f"Found MCP actions in {filename}")
            # Show lines with @action
            lines = content.split('\n')
            for i, line in enumerate(lines):
                if '@action' in line:
                    print(f"  Line {i+1}: {line.strip()}")
                    # Show the function definition too
                    if i+1 < len(lines):
                        print(f"  Line {i+2}: {lines[i+1].strip()}")