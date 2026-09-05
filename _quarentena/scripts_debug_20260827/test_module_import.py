import sys
sys.path.insert(0, '.')
try:
    import core.actions.os_ops
    print('Module imported successfully')
except Exception as e:
    print(f'Error importing module: {e}')
    import traceback
    traceback.print_exc()