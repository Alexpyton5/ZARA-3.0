# Final verification that all the previously broken actions are now working
from core.capability_registry import load_fundamentals, load_capability
load_fundamentals()
from core.action_registry import get_registry

# Check that all previously broken actions are now available
actions_to_test = [
    'os_brightness_absolute',
    'os_night_light_on',
    'os_night_light_off',
    'window_move',
    'window_resize_larger',
    'window_close',
    'window_focus_named',
    'window_switch',
    'window_switch_next',
    'os_app'
]

reg = get_registry()
print("Verifying action availability:")
for action in actions_to_test:
    spec = reg.get_spec(action)
    available = spec is not None
    print(f"  {action}: {'✓' if available else '✗'} (spec: {spec is not None})")

# Test a few key actions
print("\nTesting key actions:")
actions_to_test = [
    ('os_brightness_absolute', '50'),
    ('os_night_light_on', None),
    ('os_night_light_off', None),
    ('window_move', None),
    ('os_app', 'calculator')
]

for action, param in actions_to_test:
    try:
        if action == 'window_focus_named':
            # Special case for window_focus_named - needs a valid target
            result = reg.execute(action, target="chrome")
        elif action == 'os_app':
            # Special case for os_app - needs a valid app name
            result = reg.execute(action, app="calculator")
        elif action == 'os_brightness_absolute':
            result = reg.execute(action, level=50)
        else:
            result = reg.execute(action, **({'level': param} if isinstance(param, str) and param.isdigit() else {}))
        
        if result.success:
            print(f"  ✓ {action} succeeded: {result.output}")
        else:
            print(f"  ✗ {action} failed: {result.error}")
    except Exception as e:
        print(f"  ✗ {action} error: {e}")