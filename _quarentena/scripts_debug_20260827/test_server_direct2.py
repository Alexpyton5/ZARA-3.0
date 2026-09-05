import asyncio
import sys
sys.path.insert(0, '.')
from core.mcp.servers.file_ops import FileOpsMCPServer

async def test():
    server = FileOpsMCPServer()
    print("Server created")
    print(f"Name: {server.name}")
    print(f"Version: {server.version}")
    print(f"Tools: {list(server._tools.keys())}")
    
    # Test tool call directly
    from core.mcp.base_server import MCPRequest
    
    # Test initialize
    request = MCPRequest(id=1, method="initialize", params={
        "protocolVersion": "2024-11-05",
        "clientInfo": {"name": "test", "version": "1.0.0"},
        "capabilities": {}
    })
    response = await server.handle_request(request)
    print(f"Initialize response: {response.to_dict()}")
    
    # Test tools/list
    request = MCPRequest(id=2, method="tools/list", params={})
    response = await server.handle_request(request)
    print(f"Tools list: {response.to_dict()}")
    
    # Test tool call
    request = MCPRequest(id=3, method="tools/call", params={
        "name": "file_list",
        "arguments": {"path": ".", "pattern": "*.py", "recursive": True}
    })
    response = await server.handle_request(request)
    print(f"Tool call: {response.to_dict()}")

asyncio.run(test())