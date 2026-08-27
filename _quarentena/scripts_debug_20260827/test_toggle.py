import sys
sys.path.insert(0, '.')

from config.config_manager import get_skill_enabled, set_skill_enabled
from pathlib import Path

print("Before toggle:")
print(f"  hello_skill enabled: {get_skill_enabled('hello_skill')}")

# Disable it
set_skill_enabled('hello_skill', False)
print("\nAfter disabling hello_skill:")
print(f"  hello_skill enabled: {get_skill_enabled('hello_skill')}")

# Now test plugin loader sees the change without restart
from core.plugin_loader import discover_plugins
from core.action_registry import get_registry

registry = get_registry()
core_tool_names = set(registry._actions.keys())
skills_dir = Path("skills")
plugin_registry = discover_plugins(skills_dir, core_tool_names)

print("\nPlugin registry after toggle:")
for rec in plugin_registry.list_for_ui():
    if rec['name'] == 'hello_skill':
        print(f"  {rec['name']}: enabled={rec['enabled']}")
        # Test running the skill when disabled
        result = plugin_registry.run('hello_skill', {'name': 'Test'}, None)
        print(f"  Running disabled skill result: {result}")

# Re-enable it
set_skill_enabled('hello_skill', True)
print("\nAfter re-enabling hello_skill:")
print(f"  hello_skill enabled: {get_skill_enabled('hello_skill')}")

# Test plugin loader sees the change again
plugin_registry2 = discover_plugins(skills_dir, core_tool_names)
print("\nPlugin registry after re-enable:")
for rec in plugin_registry2.list_for_ui():
    if rec['name'] == 'hello_skill':
        print(f"  {rec['name']}: enabled={rec['enabled']}")
        # Test running the skill when enabled
        result = plugin_registry2.run('hello_skill', {'name': 'Test'}, None)
        print(f"  Running enabled skill result: {result}")