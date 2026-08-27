from core.capability_registry import get_loaded_actions
actions = get_loaded_actions()
mcp_actions = [a for a in actions if a.startswith('mcp_')]
print('MCP Actions loaded:')
for action in sorted(mcp_actions):
    print(f'  {action}')
print(f'Total: {len(mcp_actions)}')