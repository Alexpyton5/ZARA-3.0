import sys
sys.path.insert(0, '.')

print("Trying to import core.actions.os_ops...")
try:
    import core.actions.os_ops
    print("SUCCESS: Module imported without errors")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()