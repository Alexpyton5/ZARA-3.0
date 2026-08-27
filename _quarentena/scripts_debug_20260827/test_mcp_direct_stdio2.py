import asyncio
import sys
import json
import subprocess

async def test_mcp_server_direct():
    """Test the MCP server by communicating with it directly via stdio."""
    print("Starting MCP file_ops server...")
    
    # Start the server process
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "core.mcp.servers.file_ops",
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd="."
    )
    
    print(f"Server started with PID {proc.pid}")
    
    # Read stderr in background
    async def read_stderr():
        while True:
            line = await proc.stderr.readline()
            if not line:
                break
            print(f"STDERR: {line.decode().strip()}")
    
    stderr_task = asyncio.create_task(read_stderr())
    
    # Function to send a request and read response
    async def send_request(request_dict):
        request_json = json.dumps(request_dict) + "\n"
        proc.stdin.write(request_json.encode())
        await proc.stdin.drain()
        
        # Read response
        response_line = await proc.stdout.readline()
        if not response_line:
            raise Exception("Server closed connection")
        return json.loads(response_line.decode().strip())
    
    try:
        # Send initialize request
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "test-client", "version": "1.0.0"},
                "capabilities": {}
            }
        }
        
        print("Sending initialize request...")
        init_response = await send_request(init_request)
        print(f"Initialize response: {json.dumps(init_response, indent=2)}")
        
        # Send initialized notification
        initialized_notif = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {}
        }
        notif_json = json.dumps(initialized_notif) + "\n"
        proc.stdin.write(notif_json.encode())
        await proc.stdin.drain()
        print("Sent initialized notification")
        
        # Send tools/list request
        tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {}
        }
        
        print("Sending tools/list request...")
        tools_response = await send_request(tools_request)
        print(f"Tools response: {json.dumps(tools_response, indent=2)}")
        
        if "result" in tools_response and "tools" in tools_response["result"]:
            tools = tools_response["result"]["tools"]
            print(f"\nFound {len(tools)} tools:")
            for tool in tools:
                print(f"  - {tool['name']}: {tool['description']}")
        
        # Test file_list tool
        print("\nTesting file_list tool...")
        file_list_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "file_list",
                "arguments": {
                    "path": ".",
                    "pattern": "*.py",
                    "recursive": True
                }
            }
        }
        
        file_list_response = await send_request(file_list_request)
        print(f"File list response: {json.dumps(file_list_response, indent=2)}")
        
        if "result" in file_list_response:
            result = file_list_response["result"]
            if result.get("success"):
                files = result.get("files", [])
                print(f"✓ Success: Found {len(files)} Python files")
                for i, file_info in enumerate(files[:3]):
                    print(f"  {i+1}. {file_info.get('name')} ({file_info.get('size', 0)} bytes)")
                if len(files) > 3:
                    print(f"  ... and {len(files) - 3} more")
            else:
                print(f"✗ Failed: {result.get('error', 'Unknown error')}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Terminate the server
        proc.terminate()
        await proc.wait()
        stderr_task.cancel()
        print("Server terminated")

if __name__ == "__main__":
    asyncio.run(test_mcp_server_direct())