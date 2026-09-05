"""
ZARA 3.0 - MCP Client
Client for connecting to MCP servers via stdio transport.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class MCPTool:
    """MCP tool definition from server."""
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class MCPResource:
    """MCP resource definition from server."""
    uri: str
    name: str
    description: str
    mime_type: str


@dataclass
class MCPPrompt:
    """MCP prompt definition from server."""
    name: str
    description: str
    arguments: list[dict[str, Any]]


class MCPClient:
    """MCP client for communicating with MCP servers."""

    def __init__(self, server_name: str):
        self.server_name = server_name
        self._process: asyncio.subprocess.Process | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._running = False
        self._tools: dict[str, MCPTool] = {}
        self._resources: dict[str, MCPResource] = {}
        self._prompts: dict[str, MCPPrompt] = {}
        self._initialized = False
        self._notification_handlers: list[Callable[[str, dict], Any]] = []

    async def connect(self, command: list[str], cwd: str | None = None):
        """Connect to an MCP server via stdio."""
        self._process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )

        self._reader = self._process.stdout
        self._writer = self._process.stdin
        self._running = True

        # Start reading loop
        asyncio.create_task(self._read_loop())

        # Initialize
        await self.initialize()

    async def _read_loop(self):
        """Read messages from server."""
        while self._running and self._reader:
            try:
                line = await self._reader.readline()
                if not line:
                    break
                line = line.decode("utf-8").strip()
                if not line:
                    continue

                message = json.loads(line)
                await self._handle_message(message)
            except json.JSONDecodeError:
                pass
            except Exception:
                break

    async def _handle_message(self, message: dict):
        """Handle incoming message."""
        # Response to our request
        if "id" in message and message["id"] in self._pending:
            future = self._pending.pop(message["id"])
            if "error" in message:
                future.set_exception(Exception(message["error"]["message"]))
            else:
                future.set_result(message.get("result"))
        # Notification from server
        elif "method" in message and "id" not in message:
            method = message["method"]
            params = message.get("params", {})
            for handler in self._notification_handlers:
                try:
                    await handler(method, params)
                except Exception:
                    pass

    async def _send_request(self, method: str, params: dict | None = None) -> Any:
        """Send a request and wait for response."""
        request_id = str(uuid.uuid4())
        future = asyncio.Future()
        self._pending[request_id] = future

        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }

        await self._send(message)

        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except TimeoutError:
            self._pending.pop(request_id, None)
            raise TimeoutError(f"Request {method} timed out")

    async def _send(self, message: dict):
        """Send a message."""
        if self._writer and not self._writer.is_closing():
            data = (json.dumps(message) + "\n").encode("utf-8")
            self._writer.write(data)
            await self._writer.drain()

    async def initialize(self):
        """Initialize connection with server."""
        result = await self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "clientInfo": {"name": "zara-sidecar", "version": "1.0.0"},
            "capabilities": {},
        })

        # Send initialized notification
        await self._send({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        })

        self._initialized = True

        # Load tools, resources, prompts
        await self._load_capabilities()

    async def _load_capabilities(self):
        """Load tools, resources, prompts from server."""
        # Tools
        tools_result = await self._send_request("tools/list")
        for tool_data in tools_result.get("tools", []):
            self._tools[tool_data["name"]] = MCPTool(**tool_data)

        # Resources
        resources_result = await self._send_request("resources/list")
        for resource_data in resources_result.get("resources", []):
            self._resources[resource_data["uri"]] = MCPResource(**resource_data)

        # Prompts
        prompts_result = await self._send_request("prompts/list")
        for prompt_data in prompts_result.get("prompts", []):
            self._prompts[prompt_data["name"]] = MCPPrompt(**prompt_data)

    async def call_tool(self, name: str, arguments: dict) -> Any:
        """Call a tool on the server."""
        if name not in self._tools:
            raise ValueError(f"Tool not found: {name}")
        return await self._send_request("tools/call", {"name": name, "arguments": arguments})

    async def read_resource(self, uri: str) -> str:
        """Read a resource from the server."""
        if uri not in self._resources:
            raise ValueError(f"Resource not found: {uri}")
        result = await self._send_request("resources/read", {"uri": uri})
        contents = result.get("contents", [])
        if contents:
            return contents[0].get("text", "")
        return ""

    async def get_prompt(self, name: str, arguments: dict | None = None) -> list[dict]:
        """Get a prompt from the server."""
        if name not in self._prompts:
            raise ValueError(f"Prompt not found: {name}")
        result = await self._send_request("prompts/get", {"name": name, "arguments": arguments or {}})
        return result.get("messages", [])

    def list_tools(self) -> list[MCPTool]:
        """List available tools."""
        return list(self._tools.values())

    def list_resources(self) -> list[MCPResource]:
        """List available resources."""
        return list(self._resources.values())

    def list_prompts(self) -> list[MCPPrompt]:
        """List available prompts."""
        return list(self._prompts.values())

    def on_notification(self, handler: Callable[[str, dict], Any]):
        """Register notification handler."""
        self._notification_handlers.append(handler)

    async def close(self):
        """Close connection."""
        self._running = False
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        if self._process:
            self._process.terminate()
            await self._process.wait()


class MCPClientManager:
    """Manages multiple MCP client connections."""

    def __init__(self):
        self._clients: dict[str, MCPClient] = {}
        self._server_configs: dict[str, dict] = {}

    def register_server(self, name: str, command: list[str], cwd: str | None = None):
        """Register an MCP server configuration."""
        self._server_configs[name] = {"command": command, "cwd": cwd}

    async def connect(self, name: str) -> MCPClient:
        """Connect to a registered server."""
        if name in self._clients:
            return self._clients[name]

        if name not in self._server_configs:
            raise ValueError(f"Server not registered: {name}")

        config = self._server_configs[name]
        client = MCPClient(name)
        await client.connect(config["command"], config["cwd"])
        self._clients[name] = client
        return client

    async def get_client(self, name: str) -> MCPClient | None:
        """Get an existing client."""
        return self._clients.get(name)

    async def disconnect_all(self):
        """Disconnect all clients."""
        for client in self._clients.values():
            await client.close()
        self._clients.clear()

    def list_connected(self) -> list[str]:
        """List connected servers."""
        return list(self._clients.keys())
