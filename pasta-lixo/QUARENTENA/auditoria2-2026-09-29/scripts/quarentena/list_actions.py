import sys
sys.path.insert(0, 'C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002')
from core.action_registry import get_registry
reg = get_registry()
actions = reg.list_actions()
print(f'Total actions: {len(actions)}')
for a in sorted(actions):
    spec = reg.get_spec(a)
    print(f'  {a}: risk={spec.risk}, capability={spec.capability}, category={spec.category}')