
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'core', 'actions'))
from os_ops import os_volume_action, os_brightness_action, os_night_light_on_action

print("Testing os_volume_action...")
result = os_volume_action(level=50)
print("Result:", result)

print("Testing os_brightness_action...")
result = os_brightness_action(level=50)
print("Result:", result)

print("Testing os_night_light_on_action...")
result = os_night_light_on_action()
print("Result:", result)
