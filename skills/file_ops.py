"""File Operations Skill — wraps core file actions."""
from __future__ import annotations

from core.action_registry import get_registry
from core.actions.files import (
    files_list_action,
    files_open_latest_action,
    files_read_action,
    files_write_action,
    files_delete_action,
    files_copy_action,
    files_move_action,
    files_rename_action,
    files_search_action,
    files_text_summary_action,
)

PLUGIN = {
    "name": "file_ops",
    "description": (
        "File system operations: list, open, read, write, delete, copy, move, "
        "rename, search, summarize. Safe by design: blocks sensitive paths, "
        "validates extensions, confirms window openings. Use for file and "
        "folder management."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action to perform",
                "enum": [
                    "list",
                    "open_latest",
                    "read",
                    "write",
                    "delete",
                    "copy",
                    "move",
                    "move",
                    "rename",
                    "search",
                    "summary",
                ],
            },
            "path": {"type": "STRING", "description": "File or directory path"},
            "pattern": {"type": "STRING", "description": "Glob pattern (default: *)", "default": "*"},
            "recursive": {"type": "BOOLEAN", "description": "Recursive search", "default": False},
            "include_hidden": {"type": "BOOLEAN", "description": "Include hidden files", "default": False},
            "encoding": {"type": "STRING", "description": "Text encoding", "default": "utf-8"},
            "max_size": {"type": "INTEGER", "description": "Max bytes to read", "default": 1048576},
            "content": {"type": "STRING", "description": "Content to write"},
            "append": {"type": "BOOLEAN", "description": "Append instead of overwrite", "default": False},
            "overwrite": {"type": "BOOLEAN", "description": "Overwrite if exists", "default": False},
            "src": {"type": "STRING", "description": "Source path"},
            "dst": {"type": "STRING", "description": "Destination path"},
            "new_name": {"type": "STRING", "description": "New basename only"},
            "search_pattern": {"type": "STRING", "description": "Regex pattern to search"},
            "file_pattern": {"type": "STRING", "description": "File glob pattern", "default": "*"},
            "case_sensitive": {"type": "BOOLEAN", "description": "Case sensitive search", "default": False},
            "max_results": {"type": "INTEGER", "description": "Max search results", "default": 50},
            "max_preview_lines": {"type": "INTEGER", "description": "Preview lines for summary", "default": 5},
        },
        "required": ["action"],
    },
    "category": "files",
    "version": "1.0.0",
    "author": "ZARA",
}


def run(parameters: dict, context=None) -> str:
    action_name = parameters.get("action")
    registry = get_registry()

    try:
        if action_name == "list":
            result = registry.execute(
                "files_list",
                path=parameters.get("path", "."),
                pattern=parameters.get("pattern", "*"),
                recursive=parameters.get("recursive", False),
                include_hidden=parameters.get("include_hidden", False),
            )
        elif action_name == "open_latest":
            path = parameters.get("path")
            if not path:
                return "Erro: 'path' é obrigatório para open_latest."
            result = registry.execute("files_open_latest", path=path)
        elif action_name == "read":
            file_path = parameters.get("path")
            if not file_path:
                return "Erro: 'path' é obrigatório para read."
            result = registry.execute(
                "files_read",
                path=file_path,
                encoding=parameters.get("encoding", "utf-8"),
                max_size=parameters.get("max_size", 1048576),
            )
        elif action_name == "write":
            file_path = parameters.get("path")
            content = parameters.get("content")
            if not file_path or content is None:
                return "Erro: 'path' e 'content' são obrigatórios para write."
            result = registry.execute(
                "files_write",
                path=file_path,
                content=content,
                encoding=parameters.get("encoding", "utf-8"),
                append=parameters.get("append", False),
                overwrite=parameters.get("overwrite", False),
            )
        elif action_name == "delete":
            file_path = parameters.get("path")
            if not file_path:
                return "Erro: 'path' é obrigatório para delete."
            result = registry.execute(
                "files_delete",
                path=file_path,
                recursive=parameters.get("recursive", False),
            )
        elif action_name == "copy":
            src = parameters.get("src")
            dst = parameters.get("dst")
            if not src or not dst:
                return "Erro: 'src' e 'dst' são obrigatórios para copy."
            result = registry.execute(
                "files_copy",
                src=src,
                dst=dst,
                overwrite=parameters.get("overwrite", False),
            )
        elif action_name == "move":
            src = parameters.get("src")
            dst = parameters.get("dst")
            if not src or not dst:
                return "Erro: 'src' e 'dst' são obrigatórios para move."
            result = registry.execute(
                "files_move",
                src=src,
                dst=dst,
                overwrite=parameters.get("overwrite", False),
            )
        elif action_name == "rename":
            src = parameters.get("src")
            new_name = parameters.get("new_name")
            if not src or not new_name:
                return "Erro: 'src' e 'new_name' são obrigatórios para rename."
            result = registry.execute(
                "files_rename",
                src=src,
                new_name=new_name,
            )
        elif action_name == "search":
            pattern = parameters.get("search_pattern")
            if not pattern:
                return "Erro: 'search_pattern' é obrigatório para search."
            result = registry.execute(
                "files_search",
                pattern=pattern,
                path=parameters.get("path", "."),
                file_pattern=parameters.get("file_pattern", "*"),
                case_sensitive=parameters.get("case_sensitive", False),
                max_results=parameters.get("max_results", 50),
            )
        elif action_name == "summary":
            file_path = parameters.get("path")
            if not file_path:
                return "Erro: 'path' é obrigatório para summary."
            result = registry.execute(
                "files_text_summary",
                path=file_path,
                max_preview_lines=parameters.get("max_preview_lines", 5),
            )
        else:
            return f"Ação desconhecida: {action_name}. Use: list, open_latest, read, write, delete, copy, move, rename, search, summary."

        if result.success:
            return result.output or "Feito."
        return f"Falha: {result.error}"
    except Exception as e:
        return f"Erro na skill file_ops: {e}"