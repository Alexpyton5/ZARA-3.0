"""
ZARA 3.0 - MCP Server Launcher
Starts all MCP servers as subprocesses.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

from core.mcp.client import MCPClientManager


class MCPServerLauncher:
    """Manages MCP server processes."""

    def __init__(self, project_root: Path | None = None):
        self.project_root = project_root or Path(__file__).parent.parent.parent.parent
        self._processes: dict[str, subprocess.Popen] = {}
        self._client_manager = MCPClientManager()
        self._register_servers()

    def _register_servers(self):
        """Register all MCP server configurations."""
        python_exe = sys.executable
        servers_dir = self.project_root / "core" / "mcp" / "servers"

        self._client_manager.register_server(
            "file_ops",
            [python_exe, "-m", "core.mcp.servers.file_ops"],
            cwd=str(self.project_root)
        )
        self._client_manager.register_server(
            "registry",
            [python_exe, "-m", "core.mcp.servers.registry"],
            cwd=str(self.project_root)
        )
        self._client_manager.register_server(
            "processes",
            [python_exe, "-m", "core.mcp.servers.processes"],
            cwd=str(self.project_root)
        )
        self._client_manager.register_server(
            "network",
            [python_exe, "-m", "core.mcp.servers.network"],
            cwd=str(self.project_root)
        )
        self._client_manager.register_server(
            "ui_automation",
            [python_exe, "-m", "core.mcp.servers.ui_automation"],
            cwd=str(self.project_root)
        )

    async def start_all(self) -> dict[str, bool]:
        """Start all MCP servers and connect clients."""
        results = {}
        for server_name in ["file_ops", "registry", "processes", "network", "ui_automation"]:
            try:
                client = await self._client_manager.connect(server_name)
                results[server_name] = True
                print(f"[MCP] Connected to {server_name}")
            except Exception as e:
                results[server_name] = False
                print(f"[MCP] Failed to connect to {server_name}: {e}")
        return results

    async def stop_all(self):
        """Stop all MCP servers."""
        await self._client_manager.disconnect_all()
        print("[MCP] All servers disconnected")

    def get_client_manager(self) -> MCPClientManager:
        """Get the client manager."""
        return self._client_manager

    def is_connected(self, server_name: str) -> bool:
        """Check if a server is connected."""
        return server_name in self._client_manager.list_connected()


async def main():
    """Test launcher."""
    launcher = MCPServerLauncher()
    results = await launcher.start_all()
    print(f"MCP Server status: {results}")

    # Test a tool call
    if results.get("file_ops"):
        client = await launcher.get_client_manager().get_client("file_ops")
        result = await client.call_tool("file_list", {"path": ".", "pattern": "*.py", "recursive": True})
        print(f"File list: {result}")

    await launcher.stop_all()


if __name__ == "__main__":
    asyncio.run(main())
