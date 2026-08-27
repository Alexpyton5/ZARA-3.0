import sys
sys.path.insert(0, '.')
from core.capability_registry import load_fundamentals, get_loaded_actions, load_capability

print("Before load_fundamentals:")
print(get_loaded_actions())
print("---")

load_fundamentals()
print("After load_fundamentals:")
print(get_loaded_actions())
print("---")

# Try loading some MCP actions
mcp_actions_to_try = ['mcp_connect', 'mcp_list_servers', 'mcp_call_tool']
for action in mcp_actions_to_try:
    print(f"Loading {action}...")
    result = load_capability(action)
    print(f"  Result: {result}")
    print(f"  Loaded actions: {get_loaded_actions()}")
    print("---")