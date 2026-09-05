import core.ipc_handlers
import inspect

print("IPC handlers imported successfully")

# Check that the method exists
ipc = core.ipc_handlers.IPCHandler
assert hasattr(ipc, 'pedir_autorizacao_ao_alex'), "Method pedir_autorizacao_ao_alex missing"
method = getattr(ipc, 'pedir_autorizacao_ao_alex')
assert inspect.iscoroutinefunction(method), "pedir_autorizacao_ao_alex is not a coroutine function"
print("pedir_autorizacao_ao_alex is present and is a coroutine function")

# Check that the module aprovacao_remota can be imported
import core.aprovacao_remota
print("aprovacao_remota imported successfully")