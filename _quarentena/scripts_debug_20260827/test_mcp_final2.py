import sys
sys.path.insert(0, '.')

def test_mcp_loading():
    from core.capability_registry import load_fundamentals, get_loaded_actions
    print('Loading fundamentals...')
    load_fundamentals()
    actions = get_loaded_actions()
    mcp_actions = [a for a in actions if a.startswith('mcp_')]
    print(f'Loaded {len(actions)} total actions')
    print(f'Loaded {len(mcp_actions)} MCP actions')
    if mcp_actions:
        print('MCP actions:', ', '.join(sorted(mcp_actions)))
        return True
    else:
        print('No MCP actions loaded')
        return False

if __name__ == '__main__':
    success = test_mcp_loading()
    sys.exit(0 if success else 1)