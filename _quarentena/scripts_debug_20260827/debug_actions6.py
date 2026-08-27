# Check which actions from os_ops are NOT in FUNDAMENTAL_ACTIONS
from core.capability_registry import FUNDAMENTAL_ACTIONS, _ACTION_TO_MODULE

# Find all actions that map to os_ops
os_ops_actions = [action for action, module in _ACTION_TO_MODULE.items() if module == 'os_ops']
print("All os_ops actions:")
for a in sorted(os_ops_actions):
    status = "✓ FUNDAMENTAL" if a in FUNDAMENTAL_ACTIONS else "✗ MISSING"
    print(f"  {a}: {status}")

print(f"\nTotal os_ops actions: {len(os_ops_actions)}")
print(f"In FUNDAMENTAL_ACTIONS: {len([a for a in os_ops_actions if a in FUNDAMENTAL_ACTIONS])}")
print(f"Missing: {len([a for a in os_ops_actions if a not in FUNDAMENTAL_ACTIONS])}")