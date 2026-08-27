from core.action_registry import get_registry
r = get_registry()
specs = r.get_all_specs()
for name, spec in specs.items():
    print(f'{name}: {spec.capability}')