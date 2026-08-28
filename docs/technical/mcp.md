# Model Context Protocol (MCP) in ZARA 3.0

## Overview

ZARA 3.0 implements the Model Context Protocol (MCP) to integrate with local and remote servers that provide tools, resources, and prompts. This allows ZARA to extend its capabilities through standardized MCP servers while maintaining security through capability gating and local-only server options.

## MCP Architecture

ZARA's MCP implementation consists of:

1. **MCP Client Manager** (`core/mcp/client.py`) - Manages connections to multiple MCP servers
2. **MCP Base Server** (`core/mcp/base_server.py`) - Foundation for creating MCP servers
3. **Local MCP Servers** (`core/mcp/servers/`) - Windows-specific automation servers:
   - `file_ops.py` - File system operations
   - `registry.py` - Windows Registry access
   - `processes.py` - Process management
   - `network.py` - Network information and tools
   - `ui_automation.py` - UI Automation for desktop control
4. **Built-in MCP Servers** - Standard MCP servers accessible via npm packages:
   - filesystem
   - git
   - github
   - sqlite
   - fetch

## Key Features

### Local-First Approach
- ZARA prioritizes local MCP servers that run on the user's machine
- Built-in servers require npm packages but provide standardized capabilities
- All MCP interactions are gated through ZARA's capability system

### Security Design
- MCP servers are only accessible after capability validation
- Local servers run with the same permissions as ZARA
- No automatic remote server connections without explicit configuration
- MCP tools inherit ZARA's capability requirements (PC_CONTROL, LOCAL_PC_CONTROL, etc.)

### Integration Points
- MCP actions are registered in `core/action_mapping.py`
- MCP client manager is initialized in `core/actions/os_ops.py`
- Configuration is managed through `config/schemas/mcp.py`

## Local MCP Servers

### File Operations Server (`file_ops.py`)
Provides file system capabilities:
- Read/write files
- List directories
- Create/delete files and folders
- Move/copy operations
- File information (size, timestamps, etc.)

### Registry Server (`registry.py`)
Provides Windows Registry access:
- Read registry keys and values
- Create/delete registry keys
- Enumerate subkeys and values
- Registry hive navigation

### Processes Server (`processes.py`)
Provides process management:
- List running processes
- Get process information
- Start/terminate processes
- Process monitoring

### Network Server (`network.py`)
Provides network tools:
- Network interface information
- DNS resolution
- Ping and traceroute
- Port scanning
- HTTP requests

### UI Automation Server (`ui_automation.py`)
Provides desktop automation:
- Find windows and controls
- Send mouse and keyboard input
- Read UI element properties
- Take screenshots
- Window management

## MCP Configuration

MCP configuration is managed through:
- `config/schemas/mcp.py` - Defines configuration structure
- `enable_mcp` flag - Global toggle for MCP functionality
- Server-specific configuration sections for each MCP server
- Environment variable support via `ZARA_MCP_*` prefixes

## Usage

MCP capabilities are accessed through ZARA's normal action system. When an MCP action is requested:

1. The action mapping routes the request to the MCP handler in `os_ops.py`
2. The MCP client manager locates the appropriate server (local or built-in)
3. The request is forwarded to the MCP server via stdio or network transport
4. Results are returned through ZARA's action result system

## Status

**PRONTO** — Functional and tested as part of Fases 1-2. The MCP system integrates 10 servers (5 local + 5 built-in) providing 38 MCP actions mapped to the os_ops module. Local MCP servers are functional and tested; built-in servers require npm package installation for full functionality.