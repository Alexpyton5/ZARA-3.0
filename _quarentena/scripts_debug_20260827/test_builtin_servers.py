import asyncio
import sys
import os
sys.path.insert(0, '.')

from core.mcp.client import MCPClient

async def test_server(server_name, command, args, cwd=None):
    print(f"\n=== Testing {server_name} ===")
    client = MCPClient(server_name)
    try:
        await client.connect(command, cwd=cwd or os.getcwd())
        print(f"Connected to {server_name}")
        tools = client.list_tools()
        print(f"Tools: {[t.name for t in tools]}")
        # Try to call a simple tool if available
        if tools:
            # Try to call the first tool with empty args if possible
            tool_name = tools[0].name
            print(f"Trying to call {tool_name}...")
            try:
                result = await client.call_tool(tool_name, {})
                print(f"Result: {result}")
            except Exception as e:
                print(f"Error calling {tool_name}: {e}")
    except Exception as e:
        print(f"Error connecting to {server_name}: {e}")
    finally:
        await client.close()

async def main():
    # Test filesystem
    await test_server(
        "filesystem",
        "npx",
        ["-y", "@modelcontextprotocol/server-filesystem", "."],
        cwd="."
    )
    # Test git
    await test_server(
        "git",
        "npx",
        ["-y", "@modelcontextprotocol/server-git"],
        cwd="."
    )
    # Test fetch
    await test_server(
        "fetch",
        "npx",
        ["-y", "@modelcontextprotocol/server-fetch"],
        cwd="."
    )
    # Github and sqlite require env vars or db path, skip for now

if __name__ == "__main__":
    asyncio.run(main())