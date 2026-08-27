import asyncio
import sys
import os
sys.path.insert(0, '.')

async def test_local_mcp_server():
    """Test the local MCP file_ops server directly."""
    from core.mcp.client import MCPClient
    
    print("Testing local MCP file_ops server...")
    
    # Create a client for the file_ops server
    client = MCPClient("file_ops_test")
    project_root = os.getcwd()
    python_exe = sys.executable
    
    try:
        # Connect to the server
        await client.connect([
            python_exe, "-m", "core.mcp.servers.file_ops"
        ], cwd=project_root)
        print("✓ Connected to MCP file_ops server")
        
        # List available tools
        tools = client.list_tools()
        print(f"✓ Available tools ({len(tools)}):")
        for tool in tools:
            print(f"  - {tool.name}")
        
        # Test file_list tool
        print("\nTesting file_list tool...")
        result = await client.call_tool("file_list", {
            "path": ".",
            "pattern": "*.py",
            "recursive": True
        })
        
        if result.get("success"):
            files = result.get("files", [])
            print(f"✓ Success: Found {len(files)} Python files")
            # Show first 3 files
            for i, file_info in enumerate(files[:3]):
                print(f"  {i+1}. {file_info.get('name')} ({file_info.get('size', 0)} bytes)")
            if len(files) > 3:
                print(f"  ... and {len(files) - 3} more")
        else:
            print(f"✗ Failed: {result.get('error', 'Unknown error')}")
            
        # Test file_read tool on this very file
        print("\nTesting file_read tool on debug_registry.py...")
        result = await client.call_tool("file_read", {
            "path": "debug_registry.py"
        })
        
        if result.get("success"):
            content = result.get("content", "")
            lines = content.split('\n')
            print(f"✓ Success: Read {len(lines)} lines")
            print(f"  First line: {lines[0] if lines else 'empty'}")
        else:
            print(f"✗ Failed: {result.get('error', 'Unknown error')}")
            
    except Exception as e:
        print(f"✗ Error connecting to MCP server: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.close()
        print("✓ Connection closed")

if __name__ == "__main__":
    asyncio.run(test_local_mcp_server())