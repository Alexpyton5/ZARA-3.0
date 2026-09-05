import sys
sys.path.insert(0, '.')
from core.capability_registry import load_fundamentals, get_loaded_actions

print("Before load_fundamentals:")
print(get_loaded_actions())
print("---")

try:
    load_fundamentals()
    print("load_fundamentals succeeded")
except Exception as e:
    print(f"load_fundamentals failed: {e}")
    import traceback
    traceback.print_exc()

print("After load_fundamentals:")
print(get_loaded_actions())