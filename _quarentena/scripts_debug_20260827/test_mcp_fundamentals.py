import sys
sys.path.insert(0, '.')
from core.capability_registry import load_fundamentals, get_loaded_actions
print('Loading fundamentals...')
load_fundamentals()
actions = get_loaded_actions()
print(f'Loaded {len(actions)} fundamental actions')
mcp_actions = [a for a in actions if a.startswith('mcp_')]
print(f'MCP actions: {len(mcp_actions)}')
if mcp_actions:
    print('MCP actions loaded:', ', '.join(sorted(mcp_actions)))