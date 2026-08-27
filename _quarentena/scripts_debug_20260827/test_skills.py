import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.plugin_loader import discover_plugins
from pathlib import Path

# Test plugin discovery
skills_dir = Path('./skills')
core_tool_names = set()  # We'll get these from the action registry

def logger(msg):
    print(f"[PLUGIN] {msg}")

print("Discovering plugins...")
registry = discover_plugins(skills_dir, core_tool_names, logger)

print(f"\nDiscovered {len(registry._plugins)} valid plugins:")
for name, plugin in registry._plugins.items():
    print(f"  - {name}: {plugin.description}")

# Test executing each skill
print("\nTesting skills:")
for skill_name in ['system_control', 'file_ops', 'web_search', 'code_helper']:
    if skill_name in registry._plugins:
        print(f"\nTesting {skill_name}:")
        try:
            # Test with minimal parameters
            if skill_name == 'system_control':
                result = registry.run(skill_name, {'action': 'time'})
            elif skill_name == 'file_ops':
                result = registry.run(skill_name, {'action': 'list', 'path': '.'})
            elif skill_name == 'web_search':
                result = registry.run(skill_name, {'action': 'web_search', 'query': 'test'})
            elif skill_name == 'code_helper':
                result = registry.run(skill_name, {'action': 'analyze', 'path': '.'})
            
            print(f"  Result: {result[:100]}..." if len(result) > 100 else f"  Result: {result}")
        except Exception as e:
            print(f"  Error: {e}")
    else:
        print(f"  {skill_name}: NOT FOUND")