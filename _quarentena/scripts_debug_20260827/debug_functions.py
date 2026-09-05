import sys
sys.path.insert(0, '.')

# Import the module
import core.actions.os_ops as ops_module

# Get all functions defined in the module
import inspect
functions = [name for name, obj in inspect.getmembers(ops_module) if inspect.isfunction(obj)]
print(f"Total functions in module: {len(functions)}")

# Look for MCP-related functions
mcp_functions = [f for f in functions if f.startswith('mcp_')]
print(f"MCP functions: {len(mcp_functions)}")
if mcp_functions:
    print("MCP functions found:")
    for func in sorted(mcp_functions):
        print(f"  {func}")
else:
    print("No MCP functions found")

# Check if the functions are coroutines
coroutines = [name for name, obj in inspect.getmembers(ops_module) if inspect.iscoroutinefunction(obj)]
print(f"Coroutine functions: {len(coroutines)}")
mcp_coroutines = [c for c in coroutines if c.startswith('mcp_')]
print(f"MCP coroutines: {len(mcp_coroutines)}")
if mcp_coroutines:
    print("MCP coroutines found:")
    for coro in sorted(mcp_coroutines):
        print(f"  {coro}")