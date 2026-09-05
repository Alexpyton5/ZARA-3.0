import sys
sys.path.insert(0, '.')
from core.capability_registry import load_capability, get_loaded_actions
from core.action_registry import get_registry

print("Before loading:")
print(get_loaded_actions())
print("Registry actions:", get_registry().list_actions())

print("\nLoading files_list...")
result = load_capability('files_list')
print(f"Result: {result}")
print("After loading:")
print(get_loaded_actions())
print("Registry actions:", get_registry().list_actions())

print("\nLoading files_read...")
result = load_capability('files_read')
print(f"Result: {result}")
print("After loading:")
print(get_loaded_actions())
print("Registry actions:", get_registry().list_actions())