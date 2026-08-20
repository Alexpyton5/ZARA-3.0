"""
ZARA 3.0 - MCP File Operations Server
MCP server for file system operations on Windows.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from core.mcp.base_server import StdioMCPServer


class FileOpsMCPServer(StdioMCPServer):
    """MCP server for file operations."""

    def __init__(self):
        super().__init__("zara-file-ops", "1.0.0")
        self._register_tools()
        self._register_resources()

    def _register_tools(self):
        """Register file operation tools."""

        @self.tool(
            name="file_read",
            description="Read contents of a file",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                    "encoding": {"type": "string", "default": "utf-8", "description": "File encoding"},
                    "max_size": {"type": "integer", "default": 1048576, "description": "Max bytes to read"},
                },
                "required": ["path"],
            }
        )
        async def file_read(path: str, encoding: str = "utf-8", max_size: int = 1048576) -> dict:
            try:
                p = Path(path).resolve()
                if not p.exists():
                    return {"success": False, "error": f"File not found: {path}"}
                if not p.is_file():
                    return {"success": False, "error": f"Not a file: {path}"}

                size = p.stat().st_size
                if size > max_size:
                    return {"success": False, "error": f"File too large: {size} bytes (max {max_size})"}

                content = p.read_text(encoding=encoding)
                return {"success": True, "content": content, "size": size, "path": str(p)}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="file_write",
            description="Write content to a file",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to write"},
                    "content": {"type": "string", "description": "Content to write"},
                    "encoding": {"type": "string", "default": "utf-8", "description": "File encoding"},
                    "create_dirs": {"type": "boolean", "default": True, "description": "Create parent directories"},
                },
                "required": ["path", "content"],
            }
        )
        async def file_write(path: str, content: str, encoding: str = "utf-8", create_dirs: bool = True) -> dict:
            try:
                p = Path(path).resolve()
                if create_dirs:
                    p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content, encoding=encoding)
                return {"success": True, "path": str(p), "size": len(content.encode(encoding))}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="file_list",
            description="List files in a directory",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path"},
                    "pattern": {"type": "string", "description": "Glob pattern (e.g., *.py)"},
                    "recursive": {"type": "boolean", "default": False, "description": "Recursive listing"},
                    "include_dirs": {"type": "boolean", "default": True, "description": "Include directories"},
                },
                "required": ["path"],
            }
        )
        async def file_list(path: str, pattern: str = "*", recursive: bool = False, include_dirs: bool = True) -> dict:
            try:
                p = Path(path).resolve()
                if not p.exists():
                    return {"success": False, "error": f"Directory not found: {path}"}
                if not p.is_dir():
                    return {"success": False, "error": f"Not a directory: {path}"}

                if recursive:
                    files = list(p.rglob(pattern))
                else:
                    files = list(p.glob(pattern))

                result = []
                for f in files:
                    stat = f.stat()
                    result.append({
                        "name": f.name,
                        "path": str(f),
                        "relative": str(f.relative_to(p)),
                        "is_dir": f.is_dir(),
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    })

                return {"success": True, "files": result, "count": len(result)}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="file_copy",
            description="Copy a file or directory",
            input_schema={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source path"},
                    "destination": {"type": "string", "description": "Destination path"},
                    "overwrite": {"type": "boolean", "default": False, "description": "Overwrite if exists"},
                },
                "required": ["source", "destination"],
            }
        )
        async def file_copy(source: str, destination: str, overwrite: bool = False) -> dict:
            try:
                src = Path(source).resolve()
                dst = Path(destination).resolve()

                if not src.exists():
                    return {"success": False, "error": f"Source not found: {source}"}

                if dst.exists() and not overwrite:
                    return {"success": False, "error": f"Destination exists: {destination}"}

                if src.is_dir():
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)

                return {"success": True, "source": str(src), "destination": str(dst)}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="file_move",
            description="Move/rename a file or directory",
            input_schema={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source path"},
                    "destination": {"type": "string", "description": "Destination path"},
                    "overwrite": {"type": "boolean", "default": False, "description": "Overwrite if exists"},
                },
                "required": ["source", "destination"],
            }
        )
        async def file_move(source: str, destination: str, overwrite: bool = False) -> dict:
            try:
                src = Path(source).resolve()
                dst = Path(destination).resolve()

                if not src.exists():
                    return {"success": False, "error": f"Source not found: {source}"}

                if dst.exists() and not overwrite:
                    return {"success": False, "error": f"Destination exists: {destination}"}

                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))

                return {"success": True, "source": str(src), "destination": str(dst)}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="file_delete",
            description="Delete a file or directory",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to delete"},
                    "recursive": {"type": "boolean", "default": False, "description": "Delete directories recursively"},
                },
                "required": ["path"],
            }
        )
        async def file_delete(path: str, recursive: bool = False) -> dict:
            try:
                p = Path(path).resolve()

                if not p.exists():
                    return {"success": False, "error": f"Path not found: {path}"}

                if p.is_dir():
                    if recursive:
                        shutil.rmtree(p)
                    else:
                        p.rmdir()  # Only works if empty
                else:
                    p.unlink()

                return {"success": True, "path": str(p)}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="file_mkdir",
            description="Create a directory",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to create"},
                    "parents": {"type": "boolean", "default": True, "description": "Create parent directories"},
                    "exist_ok": {"type": "boolean", "default": True, "description": "Don't error if exists"},
                },
                "required": ["path"],
            }
        )
        async def file_mkdir(path: str, parents: bool = True, exist_ok: bool = True) -> dict:
            try:
                p = Path(path).resolve()
                p.mkdir(parents=parents, exist_ok=exist_ok)
                return {"success": True, "path": str(p)}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="file_info",
            description="Get file/directory information",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to inspect"},
                },
                "required": ["path"],
            }
        )
        async def file_info(path: str) -> dict:
            try:
                p = Path(path).resolve()

                if not p.exists():
                    return {"success": False, "error": f"Path not found: {path}"}

                stat = p.stat()
                return {
                    "success": True,
                    "path": str(p),
                    "name": p.name,
                    "is_file": p.is_file(),
                    "is_dir": p.is_dir(),
                    "size": stat.st_size,
                    "created": stat.st_ctime,
                    "modified": stat.st_mtime,
                    "accessed": stat.st_atime,
                    "permissions": oct(stat.st_mode)[-3:],
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="file_search",
            description="Search for files by content",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory to search"},
                    "pattern": {"type": "string", "description": "Text pattern to search for"},
                    "file_pattern": {"type": "string", "default": "*", "description": "File glob pattern"},
                    "case_sensitive": {"type": "boolean", "default": False},
                    "max_results": {"type": "integer", "default": 100},
                },
                "required": ["path", "pattern"],
            }
        )
        async def file_search(path: str, pattern: str, file_pattern: str = "*", case_sensitive: bool = False, max_results: int = 100) -> dict:
            try:
                p = Path(path).resolve()
                if not p.exists() or not p.is_dir():
                    return {"success": False, "error": f"Directory not found: {path}"}

                import re
                flags = 0 if case_sensitive else re.IGNORECASE
                regex = re.compile(pattern, flags)

                results = []
                for f in p.rglob(file_pattern):
                    if not f.is_file():
                        continue
                    try:
                        content = f.read_text(encoding="utf-8", errors="ignore")
                        for i, line in enumerate(content.splitlines(), 1):
                            if regex.search(line):
                                results.append({
                                    "file": str(f),
                                    "line": i,
                                    "content": line.strip(),
                                })
                                if len(results) >= max_results:
                                    break
                    except Exception:
                        continue
                    if len(results) >= max_results:
                        break

                return {"success": True, "matches": results, "count": len(results)}
            except Exception as e:
                return {"success": False, "error": str(e)}

    def _register_resources(self):
        """Register file system resources."""

        @self.resource("file:///home", "Home Directory", "User home directory")
        async def home_dir() -> str:
            return str(Path.home())

        @self.resource("file:///cwd", "Current Working Directory", "Current working directory")
        async def cwd() -> str:
            return str(Path.cwd())

        @self.resource("file:///downloads", "Downloads Folder", "Windows Downloads folder")
        async def downloads() -> str:
            import ctypes
            import uuid
            from ctypes import wintypes

            GUID_DOWNLOADS = uuid.UUID("374DE290-123F-4565-9164-39C4925E467B")

            class Guid(ctypes.Structure):
                _fields_ = [
                    ("data1", wintypes.DWORD),
                    ("data2", wintypes.WORD),
                    ("data3", wintypes.WORD),
                    ("data4", ctypes.c_ubyte * 8),
                ]

            raw = GUID_DOWNLOADS.bytes_le
            guid = Guid.from_buffer_copy(raw)
            resolved = ctypes.c_wchar_p()
            result = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(guid), 0, None, ctypes.byref(resolved)
            )
            if result == 0 and resolved.value:
                return resolved.value
            return str(Path.home() / "Downloads")


def main():
    """Entry point for running the server."""
    import asyncio
    server = FileOpsMCPServer()
    asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()
