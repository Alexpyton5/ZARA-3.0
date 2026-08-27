import core.actions
from core.capability_registry import get_loaded_actions, FUNDAMENTAL_ACTIONS

print('Fundamentals:', sorted(FUNDAMENTAL_ACTIONS))
print()
print('Loaded actions:', sorted(get_loaded_actions()))