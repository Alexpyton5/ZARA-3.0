"""
Files Action — File system operations.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from core.action_registry import ActionResult, action, get_registry


@action(
    name="files_list",
    category="files",
    description="List files in a directory",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path (default: project root)", "default": "."},
            "pattern": {"type": "string", "description": "Glob pattern (default: *)", "default": "*"},
            "recursive": {"type": "boolean", "description": "Recursive search (default: false)", "default": False},
            "include_hidden": {"type": "boolean", "description": "Include hidden files (default: false)", "default": False},
        },
        "required": [],
    },
)
def files_list_action(path: str = ".", pattern: str = "*", recursive: bool = False, include_hidden: bool = False) -> ActionResult:
    """List files matching pattern."""
    try:
        from core.paths import project_root
        if path == ".":
            path = str(project_root())

        base = Path(path).resolve()
        if not base.exists():
            return ActionResult(success=False, error=f"Path not found: {path}")
        if not base.is_dir():
            return ActionResult(success=False, error=f"Not a directory: {path}")

        if recursive:
            files = list(base.rglob(pattern))
        else:
            files = list(base.glob(pattern))

        if not include_hidden:
            files = [f for f in files if not f.name.startswith('.')]

        result = []
        for f in sorted(files):
            stat = f.stat()
            result.append({
                "name": f.name,
                "path": str(f.relative_to(base)),
                "absolute": str(f),
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "is_dir": f.is_dir(),
                "is_file": f.is_file(),
                "extension": f.suffix if f.is_file() else "",
            })

        return ActionResult(success=True, output=json.dumps(result, indent=2), data={"files": result, "count": len(result)})

    except Exception as e:
        return ActionResult(success=False, error=str(e))


_SENSITIVE_PATH_PATTERNS = [
    "api_keys", "secrets", "credentials", ".env", "id_rsa", "id_ed25519",
    "token.json", "auth.json", "keyring", ".npmrc", ".pypirc", "wallet",
    "passwords", "login.json", "oauth",
]

def _is_sensitive_path(path: Path) -> bool:
    """True when the resolved path points to credential/secret material."""
    low = str(path).lower()
    return any(p in low for p in _SENSITIVE_PATH_PATTERNS)


@action(
    name="files_read",
    category="files",
    description="Read file contents",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "encoding": {"type": "string", "description": "Text encoding (default: utf-8)", "default": "utf-8"},
            "max_size": {"type": "integer", "description": "Max bytes to read (default: 1MB)", "default": 1048576},
        },
        "required": ["path"],
    },
)
def files_read_action(path: str, encoding: str = "utf-8", max_size: int = 1048576) -> ActionResult:
    """Read file contents. Credential/secret paths are refused."""
    try:
        file_path = Path(path).resolve()
        if not file_path.exists():
            return ActionResult(success=False, error=f"File not found: {path}")
        if not file_path.is_file():
            return ActionResult(success=False, error=f"Not a file: {path}")

        # PC-CONTROL-POLICY-HARDENING: never expose credentials via actions.
        if _is_sensitive_path(file_path):
            return ActionResult(
                success=False,
                error="Acesso a caminho sensível (credenciais/chaves) bloqueado.",
            )

        if file_path.stat().st_size > max_size:
            return ActionResult(success=False, error=f"File too large ({file_path.stat().st_size} bytes > {max_size})")

        content = file_path.read_text(encoding=encoding)
        return ActionResult(success=True, output=content, data={"path": str(file_path), "size": len(content)})

    except UnicodeDecodeError:
        return ActionResult(success=False, error=f"Cannot decode as {encoding}. File may be binary.")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="files_write",
    category="files",
    description="Write content to file (creates directories)",
    risk="MEDIUM",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path"},
            "content": {"type": "string", "description": "Content to write"},
            "encoding": {"type": "string", "description": "Text encoding (default: utf-8)", "default": "utf-8"},
            "append": {"type": "boolean", "description": "Append instead of overwrite (default: false)", "default": False},
        },
        "required": ["path", "content"],
    },
    capability="FILES_MUTATE",
)
def files_write_action(path: str, content: str, encoding: str = "utf-8", append: bool = False) -> ActionResult:
    """Write content to file."""
    try:
        file_path = Path(path).resolve()
        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_path.write_text(content, encoding=encoding)

        return ActionResult(
            success=True,
            output=f"Written {len(content)} chars to {file_path}",
            data={"path": str(file_path), "size": len(content)}
        )
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="files_delete",
    category="files",
    description="Delete file or directory",
    risk="HIGH",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to delete"},
            "recursive": {"type": "boolean", "description": "Delete directories recursively (default: false)", "default": False},
        },
        "required": ["path"],
    },
    capability="FILES_MUTATE",
)
def files_delete_action(path: str, recursive: bool = False) -> ActionResult:
    """Delete file or directory."""
    try:
        file_path = Path(path).resolve()
        if not file_path.exists():
            return ActionResult(success=False, error=f"Path not found: {path}")

        if file_path.is_dir():
            if recursive:
                shutil.rmtree(file_path)
            else:
                file_path.rmdir()  # Only empty dirs
        else:
            file_path.unlink()

        return ActionResult(success=True, output=f"Deleted: {file_path}")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="files_copy",
    category="files",
    description="Copy file or directory",
    risk="MEDIUM",
    parameters={
        "type": "object",
        "properties": {
            "src": {"type": "string", "description": "Source path"},
            "dst": {"type": "string", "description": "Destination path"},
            "overwrite": {"type": "boolean", "description": "Overwrite if exists (default: true)", "default": True},
        },
        "required": ["src", "dst"],
    },
    capability="FILES_MUTATE",
)
def files_copy_action(src: str, dst: str, overwrite: bool = True) -> ActionResult:
    """Copy file or directory."""
    try:
        src_path = Path(src).resolve()
        dst_path = Path(dst).resolve()

        if not src_path.exists():
            return ActionResult(success=False, error=f"Source not found: {src}")

        if dst_path.exists() and not overwrite:
            return ActionResult(success=False, error=f"Destination exists: {dst}")

        if src_path.is_dir():
            if dst_path.exists():
                shutil.rmtree(dst_path)
            shutil.copytree(src_path, dst_path)
        else:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)

        return ActionResult(success=True, output=f"Copied {src_path} -> {dst_path}")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="files_move",
    category="files",
    description="Move/rename file or directory",
    risk="MEDIUM",
    parameters={
        "type": "object",
        "properties": {
            "src": {"type": "string", "description": "Source path"},
            "dst": {"type": "string", "description": "Destination path"},
            "overwrite": {"type": "boolean", "description": "Overwrite if exists (default: false)", "default": False},
        },
        "required": ["src", "dst"],
    },
    capability="FILES_MUTATE",
)
def files_move_action(src: str, dst: str, overwrite: bool = False) -> ActionResult:
    """Move/rename file or directory."""
    try:
        src_path = Path(src).resolve()
        dst_path = Path(dst).resolve()

        if not src_path.exists():
            return ActionResult(success=False, error=f"Source not found: {src}")

        if dst_path.exists() and not overwrite:
            return ActionResult(success=False, error=f"Destination exists: {dst}")

        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if dst_path.exists() and overwrite:
            if dst_path.is_dir():
                shutil.rmtree(dst_path)
            else:
                dst_path.unlink()

        shutil.move(str(src_path), str(dst_path))

        return ActionResult(success=True, output=f"Moved {src_path} -> {dst_path}")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="files_search",
    category="files",
    description="Search file contents (grep)",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Regex pattern to search"},
            "path": {"type": "string", "description": "Directory to search (default: project root)", "default": "."},
            "file_pattern": {"type": "string", "description": "File glob pattern (default: *)", "default": "*"},
            "case_sensitive": {"type": "boolean", "description": "Case sensitive search (default: false)", "default": False},
            "max_results": {"type": "integer", "description": "Max results (default: 50)", "default": 50},
        },
        "required": ["pattern"],
    },
)
def files_search_action(pattern: str, path: str = ".", file_pattern: str = "*", case_sensitive: bool = False, max_results: int = 50) -> ActionResult:
    """Search file contents using regex."""
    try:
        import re

        from core.paths import project_root
        if path == ".":
            path = str(project_root())

        base = Path(path).resolve()
        if not base.exists():
            return ActionResult(success=False, error=f"Path not found: {path}")

        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)

        results = []
        for file_path in base.rglob(file_pattern):
            if not file_path.is_file():
                continue
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(content.splitlines(), 1):
                    if regex.search(line):
                        results.append({
                            "file": str(file_path.relative_to(base)),
                            "line": i,
                            "content": line.strip(),
                        })
                        if len(results) >= max_results:
                            break
                if len(results) >= max_results:
                    break
            except Exception:
                continue

        return ActionResult(
            success=True,
            output=json.dumps(results, indent=2),
            data={"matches": results, "count": len(results)}
        )
    except Exception as e:
        return ActionResult(success=False, error=str(e))


get_registry()
