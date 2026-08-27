import sys
# Clear any cached modules
for module in list(sys.modules.keys()):
    if module.startswith('core.actions'):
        del sys.modules[module]
    if module.startswith('core.capability_registry'):
        del sys.modules[module]
    if module.startswith('core.action_registry'):
        del sys.modules[module]
    if module.startswith('core.action_mapping'):
        del sys.modules[module]

# Now import fresh
from core.capability_registry import load_fundamentals, get_loaded_actions
from core.action_mapping import _ACTION_TO_MODULE

print('Loading fundamentals...')
load_fundamentals()
actions = get_loaded_actions()
print(f'Loaded {len(actions)} total actions')

# Check what MCP actions are in the mapping
mcp_actions_in_mapping = {k: v for k, v in _ACTION_TO_MODULE.items() if k.startswith('mcp_')}
print(f'MCP actions in mapping: {len(mcp_actions_in_mapping)}')
for action in sorted(mcp_actions_in_mapping.keys()):
    print(f'  {action}')

# Try to load some MCP actions
print('\nTrying to load MCP actions...')
from core.capability_registry import load_capability
mcp_actions_to_try = ['mcp_connect', 'mcp_list_servers', 'mcp_call_tool', 'mcp_file_list']
for action in mcp_actions_to_try:
    result = load_capability(action)
    print(f'  {action}: {"SUCCESS" if result else "FAILED"}')

# Check what's actually loaded
loaded_mcp = [a for a in actions if a.startswith('mcp_')]
print(f'\nActually loaded MCP actions: {len(loaded_mcp)}')
if loaded_mcp:
    for action in sorted(loaded_mcp):
        print(f'  {action}')
else:
    print('  None')