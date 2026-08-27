from core.capability_registry import load_fundamentals
load_fundamentals()
from core.action_registry import get_registry
reg = get_registry()
actions = reg.list_actions()
print('Loaded actions:', sorted(actions))
print('Count:', len(actions))