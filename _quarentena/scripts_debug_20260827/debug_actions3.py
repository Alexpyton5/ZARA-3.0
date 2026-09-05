# Test if importing os_ops registers the actions
from core.capability_registry import load_fundamentals
load_fundamentals()
from core.action_registry import get_registry
reg = get_registry()

# Check if os_brightness_absolute exists BEFORE importing os_ops
print("Before import os_ops:")
print("  os_brightness_absolute:", reg.get("os_brightness_absolute"))

# Now import os_ops directly
import core.actions.os_ops as os_ops
print("\\nAfter import os_ops:")
print("  os_brightness_absolute:", reg.get("os_brightness_absolute"))

# Try calling the function directly
result = os_ops.os_brightness_absolute_action(50)
print("\\nDirect call result:", result)