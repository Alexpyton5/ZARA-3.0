import sys
sys.path.insert(0, '.')
from core.action_mapping import _ACTION_TO_MODULE
mcp_actions = {k: v for k, v in _ACTION_TO_MODULE.items() if k.startswith('mcp_')}
print('MCP actions in mapping:')
for action, module in sorted(mcp_actions.items()):
    print(f'  {action}: {module}')
print(f'Total: {len(mcp_actions)}')