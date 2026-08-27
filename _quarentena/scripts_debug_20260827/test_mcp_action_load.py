import sys
sys.path.insert(0, '.')
from core.capability_registry import load_capability, get_loaded_actions

print('Testing MCP action loading...')
action_to_test = 'mcp_list_servers'
print(f'Loading {action_to_test}...')
result = load_capability(action_to_test)
print(f'Result: {result}')
if result:
    print('Successfully loaded!')
    actions = get_loaded_actions()
    mcp_actions_found = [a for a in actions if a.startswith('mcp_')]
    print(f'Loaded MCP actions: {mcp_actions_found}')
else:
    print('Failed to load')
    # Try to see what's in the registry
    from core.action_registry import get_registry
    print(f'Registry actions: {get_registry().list_actions()}')
    
    # Let's also check if the os_ops module has the actions
    import core.actions.os_ops as ops_module
    import inspect
    actions_in_module = [name for name, obj in inspect.getmembers(ops_module) if inspect.iscoroutinefunction(obj) and name.endswith('_action')]
    mcp_actions_in_module = [name for name in actions_in_module if name.startswith('mcp_')]
    print(f'MCP actions in os_ops module: {mcp_actions_in_module}')