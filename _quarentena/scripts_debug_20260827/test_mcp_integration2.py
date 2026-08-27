import asyncio
import sys
import subprocess
sys.path.insert(0, '.')
from core.mcp.client import MCPClient

async def test():
    # Test local server
    client = MCPClient('file_ops')
    
    import sys
    python_exe = sys.executable
    
    try:
        await client.connect([python_exe, '-m', 'core.mcp.servers.file_ops'], cwd='.')
        print('Connected to file_ops')
        tools = client.list_tools()
        print(f'Tools: {[t.name for t in tools]}')
        
        result = await client.call_tool('file_list', {'path': '.', 'pattern': '*.py', 'recursive': True})
        print(f'File list result: {result}')
    except Exception as e:
        print(f'Error: {e}')
        import traceback
        traceback.print_exc()
    
    await client.close()

asyncio.run(test())