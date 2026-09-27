import asyncio, pathlib 
from core.ipc_handlers import IPCHandler 
import inspect 
print('import ok') 
print([k for k in IPCHandler.__dict__ if 'latencia' in k.lower()]) 
import asyncio 
from core.cronometro import relatorio 
print(relatorio()) 
