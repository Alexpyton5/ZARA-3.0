"""
Tool Adapters — Quick adapters for existing actions (system, audio, files, apps, windows, etc).

KISS approach: minimal wrapping of mature actions.
"""
from __future__ import annotations

from typing import Any

from core.tool_definition import ToolDefinition
from core.tool_risk_model import Capability, RiskLevel, risk_profile
from core.tool_verifier import AlwaysVerified, FileExistsVerifier, FileDeletedVerifier

__all__ = [
    "create_system_adapters",
    "create_audio_adapters",
    "create_file_adapters",
    "create_app_adapters",
    "create_window_adapters",
    "create_clipboard_adapters",
    "create_screenshot_adapters",
    "create_browser_adapters",
]


def create_system_adapters() -> list[ToolDefinition]:
    """Create adapters for system tools (volume, brightness, wifi, etc)."""
    adapters = []

    # Volume control
    adapters.append(ToolDefinition(
        name="system_volume",
        description="Get or set system volume (0-100%)",
        category="system",
        risk_level=RiskLevel.SAFE,
        capability=Capability.LOCAL_PC_CONTROL,
        tags=["deterministic", "local"],
        input_schema={
            "type": "object",
            "properties": {
                "level": {"type": "integer", "description": "Volume level 0-100"},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "level": {"type": "integer"},
            },
        },
    ))

    # Brightness control
    adapters.append(ToolDefinition(
        name="system_brightness",
        description="Get or set screen brightness (0-100%)",
        category="system",
        risk_level=RiskLevel.SAFE,
        capability=Capability.LOCAL_PC_CONTROL,
        tags=["deterministic", "local"],
        input_schema={
            "type": "object",
            "properties": {
                "level": {"type": "integer", "description": "Brightness 0-100"},
            },
        },
    ))

    # Night Light
    adapters.append(ToolDefinition(
        name="system_night_light",
        description="Enable or disable night light",
        category="system",
        risk_level=RiskLevel.SAFE,
        capability=Capability.LOCAL_PC_CONTROL,
        tags=["deterministic", "local"],
        input_schema={
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
            },
        },
    ))

    # WiFi
    adapters.append(ToolDefinition(
        name="system_wifi",
        description="Enable or disable WiFi",
        category="system",
        risk_level=RiskLevel.SAFE,
        capability=Capability.LOCAL_PC_CONTROL,
        tags=["deterministic", "local"],
        input_schema={
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
            },
        },
    ))

    # Bluetooth
    adapters.append(ToolDefinition(
        name="system_bluetooth",
        description="Enable or disable Bluetooth",
        category="system",
        risk_level=RiskLevel.SAFE,
        capability=Capability.LOCAL_PC_CONTROL,
        tags=["deterministic", "local"],
        input_schema={
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
            },
        },
    ))

    return adapters


def create_audio_adapters() -> list[ToolDefinition]:
    """Create adapters for audio tools (mute, unmute, status)."""
    adapters = []

    adapters.append(ToolDefinition(
        name="audio_mute",
        description="Mute system audio",
        category="audio",
        risk_level=RiskLevel.SAFE,
        capability=Capability.LOCAL_PC_CONTROL,
        tags=["deterministic", "local"],
    ))

    adapters.append(ToolDefinition(
        name="audio_unmute",
        description="Unmute system audio",
        category="audio",
        risk_level=RiskLevel.SAFE,
        capability=Capability.LOCAL_PC_CONTROL,
        tags=["deterministic", "local"],
    ))

    adapters.append(ToolDefinition(
        name="audio_status",
        description="Get audio status (muted, volume level)",
        category="audio",
        risk_level=RiskLevel.SAFE,
        capability=Capability.READ_ONLY,
    ))

    return adapters


def create_file_adapters() -> list[ToolDefinition]:
    """Create adapters for file tools (copy, move, delete, create, read)."""
    adapters = []

    adapters.append(ToolDefinition(
        name="file_copy",
        description="Copy a file",
        category="files",
        risk_level=RiskLevel.CONFIRM,
        capability=Capability.FILES_MUTATE,
        requires_confirmation=True,
        verifier=FileExistsVerifier(),
        input_schema={
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "destination": {"type": "string"},
            },
            "required": ["source", "destination"],
        },
    ))

    adapters.append(ToolDefinition(
        name="file_move",
        description="Move or rename a file",
        category="files",
        risk_level=RiskLevel.CONFIRM,
        capability=Capability.FILES_MUTATE,
        requires_confirmation=True,
        input_schema={
            "type": "object",
            "properties": {
                "source": {"type": "string"},
                "destination": {"type": "string"},
            },
            "required": ["source", "destination"],
        },
    ))

    adapters.append(ToolDefinition(
        name="file_delete",
        description="Delete a file (to recycle bin)",
        category="files",
        risk_level=RiskLevel.HIGH_RISK,
        capability=Capability.FILES_MUTATE,
        requires_confirmation=True,
        verifier=FileDeletedVerifier(),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    ))

    adapters.append(ToolDefinition(
        name="file_create",
        description="Create a new file or directory",
        category="files",
        risk_level=RiskLevel.CONFIRM,
        capability=Capability.FILES_MUTATE,
        verifier=FileExistsVerifier(),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "is_directory": {"type": "boolean"},
                "content": {"type": "string"},
            },
            "required": ["path"],
        },
    ))

    adapters.append(ToolDefinition(
        name="file_read",
        description="Read file contents",
        category="files",
        risk_level=RiskLevel.SAFE,
        capability=Capability.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    ))

    return adapters


def create_app_adapters() -> list[ToolDefinition]:
    """Create adapters for app tools (open, close, launch)."""
    adapters = []

    adapters.append(ToolDefinition(
        name="app_open",
        description="Open or launch an application",
        category="apps",
        risk_level=RiskLevel.CONFIRM,
        capability=Capability.PC_CONTROL,
        requires_superbrain=True,
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "args": {"type": "string"},
            },
            "required": ["name"],
        },
    ))

    adapters.append(ToolDefinition(
        name="app_close",
        description="Close an application",
        category="apps",
        risk_level=RiskLevel.CONFIRM,
        capability=Capability.PC_CONTROL,
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "force": {"type": "boolean"},
            },
            "required": ["name"],
        },
    ))

    adapters.append(ToolDefinition(
        name="app_list",
        description="List running applications",
        category="apps",
        risk_level=RiskLevel.SAFE,
        capability=Capability.READ_ONLY,
    ))

    return adapters


def create_window_adapters() -> list[ToolDefinition]:
    """Create adapters for window tools (minimize, maximize, close, focus)."""
    adapters = []

    adapters.append(ToolDefinition(
        name="window_minimize",
        description="Minimize a window",
        category="windows",
        risk_level=RiskLevel.SAFE,
        capability=Capability.LOCAL_PC_CONTROL,
        tags=["deterministic", "local"],
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
        },
    ))

    adapters.append(ToolDefinition(
        name="window_maximize",
        description="Maximize a window",
        category="windows",
        risk_level=RiskLevel.SAFE,
        capability=Capability.LOCAL_PC_CONTROL,
        tags=["deterministic", "local"],
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
        },
    ))

    adapters.append(ToolDefinition(
        name="window_close",
        description="Close a window",
        category="windows",
        risk_level=RiskLevel.CONFIRM,
        capability=Capability.LOCAL_PC_CONTROL,
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
        },
    ))

    adapters.append(ToolDefinition(
        name="window_focus",
        description="Focus/activate a window",
        category="windows",
        risk_level=RiskLevel.SAFE,
        capability=Capability.LOCAL_PC_CONTROL,
        tags=["deterministic", "local"],
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
        },
    ))

    return adapters


def create_clipboard_adapters() -> list[ToolDefinition]:
    """Create adapters for clipboard tools (read, write)."""
    adapters = []

    adapters.append(ToolDefinition(
        name="clipboard_read",
        description="Read clipboard contents",
        category="clipboard",
        risk_level=RiskLevel.SAFE,
        capability=Capability.READ_ONLY,
    ))

    adapters.append(ToolDefinition(
        name="clipboard_write",
        description="Write text to clipboard",
        category="clipboard",
        risk_level=RiskLevel.SAFE,
        capability=Capability.LOCAL_PC_CONTROL,
        tags=["deterministic", "local"],
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
            },
            "required": ["text"],
        },
    ))

    return adapters


def create_screenshot_adapters() -> list[ToolDefinition]:
    """Create adapters for screenshot tools."""
    adapters = []

    adapters.append(ToolDefinition(
        name="screenshot_capture",
        description="Capture a screenshot",
        category="screenshot",
        risk_level=RiskLevel.SAFE,
        capability=Capability.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "region": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "integer"},
                        "y": {"type": "integer"},
                        "width": {"type": "integer"},
                        "height": {"type": "integer"},
                    },
                },
            },
        },
    ))

    return adapters


def create_browser_adapters() -> list[ToolDefinition]:
    """Create adapters for browser tools (navigate, search, screenshot)."""
    adapters = []

    adapters.append(ToolDefinition(
        name="browser_navigate",
        description="Navigate to a URL",
        category="browser",
        risk_level=RiskLevel.CONFIRM,
        capability=Capability.PC_CONTROL,
        requires_superbrain=True,
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
            },
            "required": ["url"],
        },
    ))

    adapters.append(ToolDefinition(
        name="browser_search",
        description="Perform a web search",
        category="browser",
        risk_level=RiskLevel.CONFIRM,
        capability=Capability.PC_CONTROL,
        requires_superbrain=True,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "engine": {"type": "string"},
            },
            "required": ["query"],
        },
    ))

    adapters.append(ToolDefinition(
        name="browser_screenshot",
        description="Take a screenshot of browser page",
        category="browser",
        risk_level=RiskLevel.SAFE,
        capability=Capability.READ_ONLY,
    ))

    return adapters


def create_all_adapters() -> list[ToolDefinition]:
    """Create all standard adapters."""
    adapters = []
    adapters.extend(create_system_adapters())
    adapters.extend(create_audio_adapters())
    adapters.extend(create_file_adapters())
    adapters.extend(create_app_adapters())
    adapters.extend(create_window_adapters())
    adapters.extend(create_clipboard_adapters())
    adapters.extend(create_screenshot_adapters())
    adapters.extend(create_browser_adapters())
    return adapters
