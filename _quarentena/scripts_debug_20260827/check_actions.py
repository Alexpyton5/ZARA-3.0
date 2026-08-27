from core.capability_registry import get_fundamental_actions, get_loaded_actions
fund = get_fundamental_actions()
loaded = get_loaded_actions()
print('Fundamental actions:')
for a in sorted(fund):
    print(f'  {a}')
print(f'Total fundamental: {len(fund)}')
print()
print('Loaded actions:')
for a in sorted(loaded):
    print(f'  {a}')
print(f'Total loaded: {len(loaded)}')