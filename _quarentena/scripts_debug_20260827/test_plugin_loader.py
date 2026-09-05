import sys
sys.path.insert(0, '.')

from core.plugin_loader import discover_plugins
from core.action_registry import get_registry
from pathlib import Path

# Get core tool names
registry = get_registry()
core_tool_names = set(registry._actions.keys())
print(f"Core tools: {core_tool_names}")

# Discover plugins
skills_dir = Path("skills")
plugin_registry = discover_plugins(skills_dir, core_tool_names)

print("\n=== All records ===")
for rec in plugin_registry.list_for_ui():
    print(f"  {rec['name']}: valid={rec['valid']}, enabled={rec['enabled']}, error={rec['error']}")

print("\n=== Enabled tools ===")
tools = plugin_registry.get_tool_declarations(enabled_only=True)
for t in tools:
    print(f"  {t['name']}: {t['description']}")

print("\n=== All tools (including disabled) ===")
tools = plugin_registry.get_tool_declarations(enabled_only=False)
for t in tools:
    print(f"  {t['name']}: {t['description']} (valid={True})")