import asyncio
import sys
sys.path.insert(0, '.')
from core.mcp.client import MCPClientManager

async def test():
    manager = MCPClientManager()
    project_root = '.'
    import sys
    python_exe = sys.executable
    
    # Test local server
    manager.register_server('file_ops', [python_exe, '-m', 'core.mcp.servers.file_ops'], cwd=project_root)
    
    # Test npx server
    manager.register_server('filesystem', ['npx', '-y', '@modelcontextprotocol/server-filesystem', project_root], cwd=project_root)
    
    try:
        client = await manager.connect('file_ops')
        print('Connected to file_ops')
        tools = client.list_tools()
        print(f'Tools: {[t.name for t in tools]}')
        
        result = await client.call_tool('file_list', {'path': '.', 'pattern': '*.py', 'recursive': True})
        print(f'File list result: {result}')
    except Exception as e:
        print(f'Error: {e}')
    
    try:
        client2 = await manager.connect('filesystem')
        print('Connected to filesystem')
        tools2 = client2.list_tools()
        print(f'Tools: {[t.name for t in tools2]}')
        
        result2 = await client2.call_tool('list_directory', {'path': project_root})
        print(f'List result: {result2}')
    except Exception as e:
        print(f'Error filesystem: {e}')
    
    await manager.disconnect_all()

asyncio.run(test())