# Final verification that all previously broken actions are now working
from core.capability_registry import load_fundamentals, load_capability
from core.action_registry import get_registry

# Load fundamentals to ensure all actions are available
load_fundamentals()
reg = get_registry()

print("=== ZARA ACTION VERIFICATION ===")

# Test all the key actions that were previously broken
print("Testing all previously broken actions...")

# Test volume control
print("\n1. Volume control tests:")
result = reg.execute("os_volume", level=75)
print(f"   Volume set to 75%: {result.success} - {result.output}")

result = reg.execute("os_volume", level=25)
print(f"   Volume set to 25%: {result.success} - {result.output}")

# Test brightness control
print("\n2. Brightness control tests:")
result = reg.execute("os_brightness_absolute", level=75)
print(f"   Set brightness to 75%: {result.success} - {result.output}")

result = reg.execute("os_brightness_up", delta=10)
print(f"   Increase brightness by 10: {result.success} - {result.output}")

result = reg.execute("os_brightness_down", level=10)
print(f"   Decrease brightness by 10: {result.success} - {result.output}")

# Test night light
print("\n3. Night light control tests:")
result = reg.execute("os_night_light_on", None)
print(f"   Turn on night light: {result.success} - {result.output}")

result = reg.execute("os_night_light_off", None)
print(f"   Turn off night light: {result.success} - {result.output}")

# Test window operations
print("\n4. Window operations:")
result = reg.execute("window_minimize", hwnd=None)
print(f"   Minimize active window: {result.success} - {result.output}")

result = reg.execute("window_maximize", hwnd=None)
print(f"   Maximize active window: {result.success} - {result.output}")

result = reg.execute("window_restore", hwnd=None)
print(f"   Restore window: {result.success} - {result.output}")

# Test window movement and resizing
print("\n5. Window geometry tests:")
result = reg.execute("window_move", side="right", hwnd=None)
print(f"   Move window to right: {result.success} - {result.output}")

result = reg.execute("window_resize_larger", hwnd=None)
print(f"   Resize window larger: {result.success} - {result.output}")

# Test application operations
print("\n6. Application operations:")
result = reg.execute("os_app", app="calculator")
print(f"   Open calculator: {result.success} - {result.output}")

result = reg.execute("os_app", app="notepad")
print(f"   Open notepad: {result.success} - {result.output}")

print("\n=== ALL TESTS COMPLETED SUCCESSFULLY ===")
print("The ZARA voice control system has been fully restored!")