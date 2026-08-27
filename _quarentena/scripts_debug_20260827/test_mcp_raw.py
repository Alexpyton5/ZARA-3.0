import asyncio
import sys
import subprocess
import json

async def test():
    python_exe = sys.executable
    
    # Start the server process
    process = await asyncio.create_subprocess_exec(
        python_exe, '-m', 'core.mcp.servers.file_ops',
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd='.'
    )
    
    print("Process started")
    
    # Send initialize request
    init_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "test", "version": "1.0.0"},
            "capabilities": {}
        }
    }
    
    request_line = json.dumps(init_request) + "\n"
    process.stdin.write(request_line.encode())
    await process.stdin.drain()
    
    # Read response
    line = await process.stdout.readline()
    print(f"Response: {line.decode()}")
    
    # Send initialized notification
    init_notif = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {}
    }
    notif_line = json.dumps(init_notif) + "\n"
    process.stdin.write(notif_line.encode())
    await process.stdin.drain()
    
    # Send tools/list
    tools_request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/list",
        "params": {}
    }
    request_line = json.dumps(tools_request) + "\n"
    process.stdin.write(request_line.encode())
    await process.stdin.drain()
    
    line = await process.stdout.readline()
    print(f"Tools: {line.decode()}")
    
    # Send tool call
    tool_request = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "tools/call",
        "params": {
            "name": "file_list",
            "arguments": {"path": ".", "pattern": "*.py", "recursive": True}
        }
    }
    request_line = json.dumps(tool_request) + "\n"
    process.stdin.write(request_line.encode())
    await process.stdin.drain()
    
    line = await process.stdout.readline()
    print(f"Tool result: {line.decode()}")
    
    process.terminate()
    await process.wait()

asyncio.run(test())