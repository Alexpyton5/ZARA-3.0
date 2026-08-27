import sys
sys.path.insert(0, '.')

# Import the module and check the registry immediately
from core.action_registry import get_registry, registry
print("Registry before importing os_ops:", registry.list_actions())

import core.actions.os_ops
print("Registry after importing os_ops:", registry.list_actions())

# Check for mcp actions
all_actions = registry.list_actions()
mcp_actions = [a for a in all_actions if a.startswith('mcp_')]
print(f"MCP actions in registry: {mcp_actions}")
print(f"Total actions: {len(all_actions)}")