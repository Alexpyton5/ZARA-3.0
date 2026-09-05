import asyncio
import sys
import os
sys.path.insert(0, '.')

async def test_mcp_server():
    """Test starting an MCP server and checking its capabilities."""
    from core.mcp.client import MCPClientManager
    
    manager = MCPClientManager()
    project_root = os.getcwd()
    python_exe = sys.executable
    
    print("Testing MCP file_ops server...")
    
    # Register the file_ops server
    manager.register_server(
        "file_ops",
        [python_exe, "-m", "core.mcp.servers.file_ops"],
        cwd=project_root
    )
    
    try:
        # Try to connect
        client = await manager.connect("file_ops")
        print("✓ Connected to file_ops server")
        
        # List tools
        tools = client.list_tools()
        print(f"✓ Found {len(tools)} tools:")
        for tool in tools:
            print(f"  - {tool.name}: {tool.description}")
        
        # Try calling a simple tool
        if tools:
            print("\nTesting file_list tool...")
            result = await client.call_tool("file_list", {
                "path": ".",
                "pattern": "*.py",
                "recursive": True
            })
            if result.get("success"):
                print(f"✓ file_list succeeded: found {result.get('count', 0)} files")
                # Show first few files
                files = result.get("files", [])[:3]
                for f in files:
                    print(f"  - {f.get('name', 'unknown')} ({f.get('size', 0)} bytes)")
            else:
                print(f"✗ file_list failed: {result.get('error', 'unknown error')}")
        
        # List resources
        resources = client.list_resources()
        print(f"\n✓ Found {len(resources)} resources:")
        for resource in resources:
            print(f"  - {resource.uri}: {resource.name}")
        
        # List prompts
        prompts = client.list_prompts()
        print(f"✓ Found {len(prompts)} prompts:")
        for prompt in prompts:
            print(f"  - {prompt.name}: {prompt.description}")
            
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await manager.disconnect_all()
        print("✓ Disconnected from all servers")

if __name__ == "__main__":
    asyncio.run(test_mcp_server())