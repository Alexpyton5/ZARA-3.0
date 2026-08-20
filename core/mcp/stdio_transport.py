"""
ZARA 3.0 - MCP Stdio Transport
Stdio-based transport for MCP server/client communication.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class StdioTransport:
    """Stdio transport for MCP communication."""

    _reader: asyncio.StreamReader | None = None
    _writer: asyncio.StreamWriter | None = None
    _running: bool = False
    _message_handler: Callable[[dict], Any] | None = None

    async def connect(self):
        """Connect to stdio."""
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, asyncio.subprocess.PIPE)

        # For client, we need to spawn the server process
        # This is a simplified version - actual implementation would spawn subprocess
        pass

    async def start_server_process(self, command: list[str], cwd: str | None = None):
        """Start an MCP server as a subprocess."""
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

        # Start reading messages
        asyncio.create_task(self._read_loop())

    async def _read_loop(self):
        """Read messages from the server."""
        while self._running and self._reader:
            try:
                line = await self._reader.readline()
                if not line:
                    break
                line = line.decode("utf-8").strip()
                if not line:
                    continue

                message = json.loads(line)
                if self._message_handler:
                    await self._message_handler(message)
            except json.JSONDecodeError:
                pass
            except Exception:
                break

    async def send(self, message: dict) -> None:
        """Send a message to the server."""
        if self._writer and not self._writer.is_closing():
            data = (json.dumps(message) + "\n").encode("utf-8")
            self._writer.write(data)
            await self._writer.drain()

    async def request(self, method: str, params: dict | None = None, request_id: str | None = None) -> dict:
        """Send a request and wait for response."""
        if request_id is None:
            request_id = str(uuid.uuid4())

        future = asyncio.Future()
        # In a full implementation, we'd track pending requests
        # For now, this is a placeholder
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        await self.send(message)

        # Wait for response (simplified)
        return await future

    def on_message(self, handler: Callable[[dict], Any]):
        """Set message handler."""
        self._message_handler = handler

    async def close(self):
        """Close the transport."""
        self._running = False
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        if hasattr(self, '_process') and self._process:
            self._process.terminate()
            await self._process.wait()
