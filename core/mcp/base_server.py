"""
ZARA 3.0 - MCP Base Server
Core MCP server implementation with stdio transport support.
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MCPErrorCode(Enum):
    """Standard MCP error codes."""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    RESOURCE_NOT_FOUND = -32002
    TOOL_NOT_FOUND = -32001


@dataclass
class MCPTool:
    """MCP tool definition."""
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any] | None = None
    handler: Callable | None = None


@dataclass
class MCPResource:
    """MCP resource definition."""
    uri: str
    name: str
    description: str
    mime_type: str = "text/plain"
    handler: Callable | None = None


@dataclass
class MCPPrompt:
    """MCP prompt template definition."""
    name: str
    description: str
    arguments: list[dict[str, Any]] = field(default_factory=list)
    handler: Callable | None = None


@dataclass
class MCPRequest:
    """MCP JSON-RPC request."""
    jsonrpc: str = "2.0"
    id: str | int | None = None
    method: str = ""
    params: dict[str, Any] | None = None


@dataclass
class MCPResponse:
    """MCP JSON-RPC response."""
    jsonrpc: str = "2.0"
    id: str | int | None = None
    result: Any = None
    error: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {"jsonrpc": self.jsonrpc}
        if self.id is not None:
            d["id"] = self.id
        if self.error is not None:
            d["error"] = self.error
        else:
            d["result"] = self.result
        return d


class MCPServer(ABC):
    """Base MCP server with tool, resource, and prompt registration."""

    def __init__(self, name: str, version: str = "1.0.0"):
        self.name = name
        self.version = version
        self._tools: dict[str, MCPTool] = {}
        self._resources: dict[str, MCPResource] = {}
        self._prompts: dict[str, MCPPrompt] = {}
        self._initialized = False

    def register_tool(self, tool: MCPTool) -> None:
        """Register a tool with the server."""
        self._tools[tool.name] = tool

    def register_resource(self, resource: MCPResource) -> None:
        """Register a resource with the server."""
        self._resources[resource.uri] = resource

    def register_prompt(self, prompt: MCPPrompt) -> None:
        """Register a prompt template with the server."""
        self._prompts[prompt.name] = prompt

    def tool(self, name: str, description: str, input_schema: dict, output_schema: dict | None = None):
        """Decorator to register a tool."""
        def decorator(func: Callable):
            tool = MCPTool(
                name=name,
                description=description,
                input_schema=input_schema,
                output_schema=output_schema,
                handler=func
            )
            self.register_tool(tool)
            return func
        return decorator

    def resource(self, uri: str, name: str, description: str, mime_type: str = "text/plain"):
        """Decorator to register a resource."""
        def decorator(func: Callable):
            resource = MCPResource(
                uri=uri,
                name=name,
                description=description,
                mime_type=mime_type,
                handler=func
            )
            self.register_resource(resource)
            return func
        return decorator

    def prompt(self, name: str, description: str, arguments: list[dict] | None = None):
        """Decorator to register a prompt template."""
        def decorator(func: Callable):
            prompt = MCPPrompt(
                name=name,
                description=description,
                arguments=arguments or [],
                handler=func
            )
            self.register_prompt(prompt)
            return func
        return decorator

    async def handle_request(self, request: MCPRequest) -> MCPResponse:
        """Handle an incoming MCP request."""
        try:
            if request.method == "initialize":
                return await self._handle_initialize(request)
            elif request.method == "tools/list":
                return await self._handle_tools_list(request)
            elif request.method == "tools/call":
                return await self._handle_tool_call(request)
            elif request.method == "resources/list":
                return await self._handle_resources_list(request)
            elif request.method == "resources/read":
                return await self._handle_resource_read(request)
            elif request.method == "prompts/list":
                return await self._handle_prompts_list(request)
            elif request.method == "prompts/get":
                return await self._handle_prompt_get(request)
            elif request.method == "notifications/initialized":
                self._initialized = True
                return MCPResponse(id=request.id, result={})
            else:
                return self._error_response(request.id, MCPErrorCode.METHOD_NOT_FOUND, f"Method not found: {request.method}")
        except Exception as e:
            return self._error_response(request.id, MCPErrorCode.INTERNAL_ERROR, str(e))

    async def _handle_initialize(self, request: MCPRequest) -> MCPResponse:
        """Handle initialize request."""
        self._initialized = True
        params = request.params or {}
        client_info = params.get("clientInfo", {})
        return MCPResponse(
            id=request.id,
            result={
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": True},
                    "resources": {"subscribe": True, "listChanged": True},
                    "prompts": {"listChanged": True},
                },
                "serverInfo": {
                    "name": self.name,
                    "version": self.version,
                },
            }
        )

    async def _handle_tools_list(self, request: MCPRequest) -> MCPResponse:
        """Handle tools/list request."""
        tools = [
            {
                "name": tool.name,
                "description": tool.description,
                "inputSchema": tool.input_schema,
            }
            for tool in self._tools.values()
        ]
        return MCPResponse(id=request.id, result={"tools": tools})

    async def _handle_tool_call(self, request: MCPRequest) -> MCPResponse:
        """Handle tools/call request."""
        params = request.params or {}
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name not in self._tools:
            return self._error_response(request.id, MCPErrorCode.TOOL_NOT_FOUND, f"Tool not found: {tool_name}")

        tool = self._tools[tool_name]
        if tool.handler is None:
            return self._error_response(request.id, MCPErrorCode.INTERNAL_ERROR, f"Tool handler not implemented: {tool_name}")

        try:
            # Validate arguments against input schema
            result = await tool.handler(**arguments)
            return MCPResponse(id=request.id, result=result)
        except Exception as e:
            return self._error_response(request.id, MCPErrorCode.INTERNAL_ERROR, f"Tool execution failed: {str(e)}")

    async def _handle_resources_list(self, request: MCPRequest) -> MCPResponse:
        """Handle resources/list request."""
        resources = [
            {
                "uri": resource.uri,
                "name": resource.name,
                "description": resource.description,
                "mimeType": resource.mime_type,
            }
            for resource in self._resources.values()
        ]
        return MCPResponse(id=request.id, result={"resources": resources})

    async def _handle_resource_read(self, request: MCPRequest) -> MCPResponse:
        """Handle resources/read request."""
        params = request.params or {}
        uri = params.get("uri")

        if uri not in self._resources:
            return self._error_response(request.id, MCPErrorCode.RESOURCE_NOT_FOUND, f"Resource not found: {uri}")

        resource = self._resources[uri]
        if resource.handler is None:
            return self._error_response(request.id, MCPErrorCode.INTERNAL_ERROR, f"Resource handler not implemented: {uri}")

        try:
            content = await resource.handler()
            return MCPResponse(
                id=request.id,
                result={
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": resource.mime_type,
                            "text": content if isinstance(content, str) else json.dumps(content),
                        }
                    ]
                }
            )
        except Exception as e:
            return self._error_response(request.id, MCPErrorCode.INTERNAL_ERROR, f"Resource read failed: {str(e)}")

    async def _handle_prompts_list(self, request: MCPRequest) -> MCPResponse:
        """Handle prompts/list request."""
        prompts = [
            {
                "name": prompt.name,
                "description": prompt.description,
                "arguments": prompt.arguments,
            }
            for prompt in self._prompts.values()
        ]
        return MCPResponse(id=request.id, result={"prompts": prompts})

    async def _handle_prompt_get(self, request: MCPRequest) -> MCPResponse:
        """Handle prompts/get request."""
        params = request.params or {}
        prompt_name = params.get("name")
        arguments = params.get("arguments", {})

        if prompt_name not in self._prompts:
            return self._error_response(request.id, MCPErrorCode.METHOD_NOT_FOUND, f"Prompt not found: {prompt_name}")

        prompt = self._prompts[prompt_name]
        if prompt.handler is None:
            return self._error_response(request.id, MCPErrorCode.INTERNAL_ERROR, f"Prompt handler not implemented: {prompt_name}")

        try:
            messages = await prompt.handler(**arguments)
            return MCPResponse(id=request.id, result={"messages": messages})
        except Exception as e:
            return self._error_response(request.id, MCPErrorCode.INTERNAL_ERROR, f"Prompt execution failed: {str(e)}")

    def _error_response(self, request_id: str | int | None, code: MCPErrorCode, message: str) -> MCPResponse:
        """Create an error response."""
        return MCPResponse(
            id=request_id,
            error={"code": code.value, "message": message}
        )

    def get_capabilities(self) -> dict[str, Any]:
        """Return server capabilities for discovery."""
        return {
            "tools": list(self._tools.keys()),
            "resources": list(self._resources.keys()),
            "prompts": list(self._prompts.keys()),
        }


class StdioMCPServer(MCPServer):
    """MCP server that communicates via stdio (for subprocess integration)."""

    def __init__(self, name: str, version: str = "1.0.0"):
        super().__init__(name, version)
        self._running = False
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def run_stdio(self):
        """Run the server using stdio transport."""
        import sys
        self._running = True

        # Create stdio transport
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)
        writer_transport, writer_protocol = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin, sys.stdout
        )
        writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, loop)

        self._reader = reader
        self._writer = writer

        # Process incoming messages
        while self._running:
            try:
                line = await reader.readline()
                if not line:
                    break
                line = line.decode("utf-8").strip()
                if not line:
                    continue

                request_data = json.loads(line)
                request = MCPRequest(**request_data)
                response = await self.handle_request(request)
                response_line = json.dumps(response.to_dict()) + "\n"
                writer.write(response_line.encode("utf-8"))
                await writer.drain()
            except json.JSONDecodeError:
                error_response = self._error_response(None, MCPErrorCode.PARSE_ERROR, "Parse error")
                writer.write((json.dumps(error_response.to_dict()) + "\n").encode("utf-8"))
                await writer.drain()
            except Exception as e:
                error_response = self._error_response(None, MCPErrorCode.INTERNAL_ERROR, str(e))
                writer.write((json.dumps(error_response.to_dict()) + "\n").encode("utf-8"))
                await writer.drain()

        writer.close()
        await writer.wait_closed()

    async def send_notification(self, method: str, params: dict[str, Any] | None = None):
        """Send a notification to the client."""
        if self._writer and not self._writer.is_closing():
            notification = {
                "jsonrpc": "2.0",
                "method": method,
                "params": params or {},
            }
            self._writer.write((json.dumps(notification) + "\n").encode("utf-8"))
            await self._writer.drain()

    def stop(self):
        """Stop the server."""
        self._running = False
