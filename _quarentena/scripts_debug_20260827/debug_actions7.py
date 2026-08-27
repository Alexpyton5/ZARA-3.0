from core.capability_registry import load_fundamentals
load_fundamentals()
from core.action_registry import get_registry
reg = get_registry()

# Test the action directly
result = reg.execute("os_brightness_absolute", level="50")
print("Direct execution result:", result)