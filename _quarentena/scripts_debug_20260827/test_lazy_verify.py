from core.capability_registry import get_loaded_actions, load_fundamentals, FUNDAMENTAL_ACTIONS, load_capability
from core.action_registry import get_registry

print('Fundamental actions:', len(FUNDAMENTAL_ACTIONS))

reg = get_registry()
print('Before load_fundamentals:', len(reg._actions))

load_fundamentals()
loaded = get_loaded_actions()
print('After load_fundamentals:', len(loaded))

fundamental_set = set(FUNDAMENTAL_ACTIONS)
loaded_set = set(loaded)
non_fundamental_loaded = loaded_set - fundamental_set
print('Non-fundamental loaded:', len(non_fundamental_loaded))
if non_fundamental_loaded:
    print('  ->', sorted(non_fundamental_loaded))
print()

# Test lazy loading
print('Testing lazy loading of code_analyze...')
success = load_capability('code_analyze')
print('Result:', success)
loaded_after = get_loaded_actions()
print('Total after lazy load:', len(loaded_after))