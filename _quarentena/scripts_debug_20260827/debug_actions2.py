from core.capability_registry import load_capability, load_fundamentals
load_fundamentals()
from core.action_registry import get_registry
reg = get_registry()

# Try to load some missing actions
for action in ['os_brightness_absolute', 'os_night_light_on', 'os_night_light_off', 'window_move', 'window_resize_larger', 'window_close', 'window_focus_named']:
    result = load_capability(action)
    print(f'load_capability({action}) = {result}')

actions = reg.list_actions()
print('\\nLoaded actions after load_capability:', sorted(actions))
print('Count:', len(actions))