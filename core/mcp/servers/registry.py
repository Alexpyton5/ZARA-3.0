"""
ZARA 3.0 - MCP Registry Server
MCP server for Windows Registry operations.
"""

from __future__ import annotations

import winreg
from typing import Any

from core.mcp.base_server import StdioMCPServer


class RegistryMCPServer(StdioMCPServer):
    """MCP server for Windows Registry operations."""

    def __init__(self):
        super().__init__("zara-registry", "1.0.0")
        self._register_tools()

    def _register_tools(self):
        """Register registry operation tools."""

        # Registry hive mapping
        self._hives = {
            "HKLM": winreg.HKEY_LOCAL_MACHINE,
            "HKCU": winreg.HKEY_CURRENT_USER,
            "HKCR": winreg.HKEY_CLASSES_ROOT,
            "HKU": winreg.HKEY_USERS,
            "HKCC": winreg.HKEY_CURRENT_CONFIG,
        }

        @self.tool(
            name="registry_read",
            description="Read a registry value",
            input_schema={
                "type": "object",
                "properties": {
                    "hive": {"type": "string", "enum": ["HKLM", "HKCU", "HKCR", "HKU", "HKCC"], "description": "Registry hive"},
                    "path": {"type": "string", "description": "Registry key path"},
                    "name": {"type": "string", "description": "Value name (empty for default)"},
                },
                "required": ["hive", "path"],
            }
        )
        async def registry_read(hive: str, path: str, name: str = "") -> dict:
            try:
                hkey = self._hives[hive]
                with winreg.OpenKey(hkey, path, 0, winreg.KEY_READ) as key:
                    value, reg_type = winreg.QueryValueEx(key, name)
                    return {
                        "success": True,
                        "hive": hive,
                        "path": path,
                        "name": name or "(default)",
                        "value": value,
                        "type": reg_type,
                        "type_name": self._type_name(reg_type),
                    }
            except FileNotFoundError:
                return {"success": False, "error": f"Key or value not found: {hive}\\{path}\\{name}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="registry_write",
            description="Write a registry value",
            input_schema={
                "type": "object",
                "properties": {
                    "hive": {"type": "string", "enum": ["HKLM", "HKCU", "HKCR", "HKU", "HKCC"], "description": "Registry hive"},
                    "path": {"type": "string", "description": "Registry key path"},
                    "name": {"type": "string", "description": "Value name (empty for default)"},
                    "value": {"description": "Value to write"},
                    "type": {"type": "string", "enum": ["REG_SZ", "REG_DWORD", "REG_QWORD", "REG_BINARY", "REG_MULTI_SZ", "REG_EXPAND_SZ"], "default": "REG_SZ", "description": "Registry value type"},
                },
                "required": ["hive", "path", "name", "value"],
            }
        )
        async def registry_write(hive: str, path: str, name: str, value: Any, type: str = "REG_SZ") -> dict:
            try:
                hkey = self._hives[hive]
                type_map = {
                    "REG_SZ": winreg.REG_SZ,
                    "REG_DWORD": winreg.REG_DWORD,
                    "REG_QWORD": winreg.REG_QWORD,
                    "REG_BINARY": winreg.REG_BINARY,
                    "REG_MULTI_SZ": winreg.REG_MULTI_SZ,
                    "REG_EXPAND_SZ": winreg.REG_EXPAND_SZ,
                }

                with winreg.CreateKey(hkey, path) as key:
                    winreg.SetValueEx(key, name, 0, type_map[type], value)

                return {"success": True, "hive": hive, "path": path, "name": name, "type": type}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="registry_delete_value",
            description="Delete a registry value",
            input_schema={
                "type": "object",
                "properties": {
                    "hive": {"type": "string", "enum": ["HKLM", "HKCU", "HKCR", "HKU", "HKCC"], "description": "Registry hive"},
                    "path": {"type": "string", "description": "Registry key path"},
                    "name": {"type": "string", "description": "Value name to delete"},
                },
                "required": ["hive", "path", "name"],
            }
        )
        async def registry_delete_value(hive: str, path: str, name: str) -> dict:
            try:
                hkey = self._hives[hive]
                with winreg.OpenKey(hkey, path, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, name)
                return {"success": True, "hive": hive, "path": path, "name": name}
            except FileNotFoundError:
                return {"success": False, "error": f"Value not found: {hive}\\{path}\\{name}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="registry_delete_key",
            description="Delete a registry key (and subkeys)",
            input_schema={
                "type": "object",
                "properties": {
                    "hive": {"type": "string", "enum": ["HKLM", "HKCU", "HKCR", "HKU", "HKCC"], "description": "Registry hive"},
                    "path": {"type": "string", "description": "Registry key path to delete"},
                },
                "required": ["hive", "path"],
            }
        )
        async def registry_delete_key(hive: str, path: str) -> dict:
            try:
                hkey = self._hives[hive]
                # Use SHDeleteKey for recursive delete
                import ctypes
                ctypes.windll.shlwapi.SHDeleteKeyW(hkey, path)
                return {"success": True, "hive": hive, "path": path}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="registry_list_keys",
            description="List subkeys of a registry key",
            input_schema={
                "type": "object",
                "properties": {
                    "hive": {"type": "string", "enum": ["HKLM", "HKCU", "HKCR", "HKU", "HKCC"], "description": "Registry hive"},
                    "path": {"type": "string", "description": "Registry key path"},
                },
                "required": ["hive", "path"],
            }
        )
        async def registry_list_keys(hive: str, path: str) -> dict:
            try:
                hkey = self._hives[hive]
                with winreg.OpenKey(hkey, path, 0, winreg.KEY_READ) as key:
                    subkeys = []
                    i = 0
                    while True:
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            subkeys.append(subkey_name)
                            i += 1
                        except OSError:
                            break

                    values = []
                    i = 0
                    while True:
                        try:
                            value_name, value_data, value_type = winreg.EnumValue(key, i)
                            values.append({
                                "name": value_name or "(default)",
                                "value": value_data,
                                "type": self._type_name(value_type),
                            })
                            i += 1
                        except OSError:
                            break

                    return {"success": True, "hive": hive, "path": path, "subkeys": subkeys, "values": values}
            except FileNotFoundError:
                return {"success": False, "error": f"Key not found: {hive}\\{path}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="registry_create_key",
            description="Create a registry key",
            input_schema={
                "type": "object",
                "properties": {
                    "hive": {"type": "string", "enum": ["HKLM", "HKCU", "HKCR", "HKU", "HKCC"], "description": "Registry hive"},
                    "path": {"type": "string", "description": "Registry key path to create"},
                },
                "required": ["hive", "path"],
            }
        )
        async def registry_create_key(hive: str, path: str) -> dict:
            try:
                hkey = self._hives[hive]
                with winreg.CreateKey(hkey, path) as key:
                    pass
                return {"success": True, "hive": hive, "path": path}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="registry_search",
            description="Search registry for keys/values matching pattern",
            input_schema={
                "type": "object",
                "properties": {
                    "hive": {"type": "string", "enum": ["HKLM", "HKCU", "HKCR", "HKU", "HKCC"], "description": "Registry hive"},
                    "path": {"type": "string", "description": "Root path to search from"},
                    "pattern": {"type": "string", "description": "Search pattern (in key names and value names)"},
                    "max_results": {"type": "integer", "default": 50, "description": "Maximum results"},
                },
                "required": ["hive", "path", "pattern"],
            }
        )
        async def registry_search(hive: str, path: str, pattern: str, max_results: int = 50) -> dict:
            try:
                hkey = self._hives[hive]
                import re
                regex = re.compile(pattern, re.IGNORECASE)

                results = []

                def search_recursive(current_hkey, current_path, depth=0):
                    if depth > 10 or len(results) >= max_results:  # Limit depth
                        return

                    try:
                        with winreg.OpenKey(current_hkey, current_path, 0, winreg.KEY_READ) as key:
                            # Check values
                            i = 0
                            while True:
                                try:
                                    value_name, value_data, value_type = winreg.EnumValue(key, i)
                                    if regex.search(value_name or "") or regex.search(str(value_data)):
                                        results.append({
                                            "path": current_path,
                                            "type": "value",
                                            "name": value_name or "(default)",
                                            "value": value_data,
                                            "value_type": self._type_name(value_type),
                                        })
                                        if len(results) >= max_results:
                                            return
                                    i += 1
                                except OSError:
                                    break

                            # Check subkeys
                            i = 0
                            while True:
                                try:
                                    subkey_name = winreg.EnumKey(key, i)
                                    if regex.search(subkey_name):
                                        results.append({
                                            "path": f"{current_path}\\{subkey_name}",
                                            "type": "key",
                                            "name": subkey_name,
                                        })
                                        if len(results) >= max_results:
                                            return
                                    # Recurse
                                    search_recursive(current_hkey, f"{current_path}\\{subkey_name}", depth + 1)
                                    i += 1
                                except OSError:
                                    break
                    except Exception:
                        pass

                search_recursive(hkey, path)
                return {"success": True, "matches": results, "count": len(results)}
            except Exception as e:
                return {"success": False, "error": str(e)}

    def _type_name(self, reg_type: int) -> str:
        """Convert registry type to name."""
        type_names = {
            winreg.REG_SZ: "REG_SZ",
            winreg.REG_DWORD: "REG_DWORD",
            winreg.REG_QWORD: "REG_QWORD",
            winreg.REG_BINARY: "REG_BINARY",
            winreg.REG_MULTI_SZ: "REG_MULTI_SZ",
            winreg.REG_EXPAND_SZ: "REG_EXPAND_SZ",
        }
        return type_names.get(reg_type, f"UNKNOWN({reg_type})")


def main():
    """Entry point for running the server."""
    import asyncio
    server = RegistryMCPServer()
    asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()
