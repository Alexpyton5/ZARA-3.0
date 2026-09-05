import sys
sys.path.insert(0, 'C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002')
from core.action_registry import get_registry
# Import actions to trigger decorators
from core import actions  # noqa: F401
r = get_registry()
specs = r.get_all_specs()
print('Total actions:', len(specs))
for name, spec in specs.items():
    print(f'{name}: {spec.capability}')