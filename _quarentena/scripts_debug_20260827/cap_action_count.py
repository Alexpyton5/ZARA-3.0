from core.action_registry import get_registry
r = get_registry()
specs = r.get_all_specs()
print('Total actions:', len(specs))
caps = {}
for name, spec in specs.items():
    caps.setdefault(spec.capability, []).append(name)
for cap, names in caps.items():
    print(f'{cap}: {len(names)} actions')
    for n in names[:5]:
        print('  ', n)
    if len(names) > 5:
        print('  ...')