import sys
sys.path.insert(0, '.')

def test_mcp_loading():
    from core.capability_registry import load_capability, get_loaded_actions
    print('Testing direct loading of mcp_list_servers...')
    result = load_capability('mcp_list_servers')
    print(f'Load result: {result}')
    actions = get_loaded_actions()
    print(f'Loaded actions: {actions}')
    mcp_actions = [a for a in actions if a.startswith('mcp_')]
    print(f'MCP actions: {mcp_actions}')
    return result and len(mcp_actions) > 0

if __name__ == '__main__':
    success = test_mcp_loading()
    print(f'Success: {success}')
    sys.exit(0 if success else 1)