import sys
sys.path.insert(0, '.')
from core.mcp.servers.file_ops import FileOpsMCPServer

server = FileOpsMCPServer()
print("Server created")
print(f"Name: {server.name}")
print(f"Version: {server.version}")
print(f"Tools: {list(server._tools.keys())}")
print(f"Resources: {list(server._resources.keys())}")
print(f"Prompts: {list(server._prompts.keys())}")