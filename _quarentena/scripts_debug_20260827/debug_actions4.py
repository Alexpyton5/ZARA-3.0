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

# Let's look at what the @action decorator does
# It wraps the function in guarded_action
# Check if the action is actually registered
print("\\nRegistry actions:", reg.list_actions())

# Check if the spec exists
spec = reg.get_spec("os_brightness_absolute")
print("Spec:", spec)