"""
Files Action — File system operations.
"""
from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

from core.action_registry import ActionResult, action, get_registry

_SAFE_OPEN_EXTENSIONS = {
    ".txt", ".md", ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".csv", ".rtf", ".odt", ".ods", ".odp",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp",
    ".mp3", ".wav", ".m4a", ".flac", ".mp4", ".mkv", ".webm",
}


def _window_snapshot() -> dict[int, str]:
    from core.actions.os_ops import _eligible_windows, _window_text

    return {int(hwnd): _window_text(hwnd).strip() for hwnd in _eligible_windows()}


def _confirm_file_window(file_path: Path, before: dict[int, str], timeout: float = 4.0) -> dict | None:
    from core.actions.os_ops import _eligible_windows, _window_process_name, _window_text

    stem = file_path.stem.casefold()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for hwnd in _eligible_windows():
            title = _window_text(hwnd).strip()
            title_folded = title.casefold()
            if stem and stem in title_folded:
                return {
                    "hwnd": int(hwnd),
                    "process": _window_process_name(hwnd),
                    "window_title": title,
                    "new_window": int(hwnd) not in before,
                    "title_changed": before.get(int(hwnd)) != title,
                }
        time.sleep(0.15)
    return None


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
        if _is_sensitive_path(base):
            return ActionResult(
                success=False,
                error="Acesso a caminho sensível (credenciais/chaves) bloqueado.",
                data=None,
            )

        if recursive:
            files = list(base.rglob(pattern))
        else:
            files = list(base.glob(pattern))

        if not include_hidden:
            files = [f for f in files if not f.name.startswith('.')]

        files = [f for f in files if not _is_sensitive_path(f)]

        result = []
        for f in sorted(files):
            try:
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
            except (ValueError, OSError):
                # Entry outside `base` (junction/symlink) or vanished mid-listing; skip it
                # instead of failing the whole listing.
                continue

        return ActionResult(success=True, output=json.dumps(result, indent=2), data={"files": result, "count": len(result)})

    except Exception as e:
        return ActionResult(success=False, error=str(e))


_SENSITIVE_PATH_PATTERNS = [
    "api_keys", "secrets", "credentials", ".env", "id_rsa", "id_ed25519",
    "token.json", "auth.json", "keyring", ".npmrc", ".pypirc", "wallet",
    "passwords", "login.json", "oauth", ".ssh", ".gnupg", ".aws", ".azure",
    ".codex",
]

def _is_sensitive_path(path: Path) -> bool:
    """True when the resolved path points to credential/secret material."""
    low = str(path).lower()
    return any(p in low for p in _SENSITIVE_PATH_PATTERNS)


def _sensitive_path_error(*paths: Path) -> ActionResult | None:
    if any(_is_sensitive_path(path) for path in paths):
        return ActionResult(
            success=False,
            error="Acesso a caminho sensível (credenciais/chaves) bloqueado.",
        )
    return None


@action(
    name="files_open_latest",
    category="files",
    description="Open the newest safe file in a known directory and verify its associated window",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Known directory path"}},
        "required": ["path"],
    },
)
def files_open_latest_action(path: str) -> ActionResult:
    """Open the latest allowlisted non-secret file; never launch code or executables."""
    try:
        base = Path(path).resolve()
        if not base.is_dir():
            return ActionResult(success=False, error="A pasta de downloads não está disponível.")
        candidates = [
            item for item in base.iterdir()
            if item.is_file()
            and not item.name.startswith(".")
            and item.suffix.casefold() in _SAFE_OPEN_EXTENSIONS
            and not _is_sensitive_path(item)
        ]
        if not candidates:
            return ActionResult(
                success=False,
                error="Não encontrei um download recente seguro para abrir.",
                data={"status": "NO_SAFE_CANDIDATE", "blocked_executable": True},
            )
        target = max(candidates, key=lambda item: item.stat().st_mtime_ns)
        before = _window_snapshot()
        os.startfile(str(target))  # type: ignore[attr-defined]
        proof = _confirm_file_window(target, before)
        if proof is None:
            return ActionResult(
                success=False,
                error=f"Enviei {target.name} para o aplicativo associado, mas não consegui confirmar a janela.",
                data={"status": "POSTCONDITION_FAILED", "name": target.name, "safe_extension": target.suffix.casefold()},
            )
        return ActionResult(
            success=True,
            output=f"Abri o último download seguro: {target.name}.",
            data={"status": "OPEN_CONFIRMED", "name": target.name, "safe_extension": target.suffix.casefold(), **proof},
        )
    except Exception as exc:
        return ActionResult(success=False, error=str(exc))


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
            "overwrite": {"type": "boolean", "description": "Explicitly replace an existing file (default: false)", "default": False},
        },
        "required": ["path", "content"],
    },
    capability="FILES_MUTATE",
)
def files_write_action(
    path: str,
    content: str,
    encoding: str = "utf-8",
    append: bool = False,
    overwrite: bool = False,
) -> ActionResult:
    """Write content to file."""
    try:
        file_path = Path(path).resolve()
        blocked = _sensitive_path_error(file_path)
        if blocked is not None:
            return blocked
        if file_path.exists() and not append and not overwrite:
            return ActionResult(
                success=False,
                error=f"Destination exists; explicit overwrite required: {file_path}",
            )
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if append:
            with file_path.open("a", encoding=encoding) as stream:
                stream.write(content)
        else:
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
        blocked = _sensitive_path_error(file_path)
        if blocked is not None:
            return blocked
        if not file_path.exists():
            return ActionResult(success=False, error=f"Path not found: {path}")

        try:
            if file_path.is_dir():
                if recursive:
                    shutil.rmtree(file_path)
                else:
                    file_path.rmdir()  # Only empty dirs
            else:
                file_path.unlink()
        except FileNotFoundError:
            # Removed by another process between the exists() check and the
            # actual delete (TOCTOU race) — treat as already-gone, not a crash.
            return ActionResult(success=False, error=f"Path not found: {path}")

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
            "overwrite": {"type": "boolean", "description": "Overwrite if exists (default: false)", "default": False},
        },
        "required": ["src", "dst"],
    },
    capability="FILES_MUTATE",
)
def files_copy_action(src: str, dst: str, overwrite: bool = False) -> ActionResult:
    """Copy file or directory."""
    try:
        src_path = Path(src).resolve()
        dst_path = Path(dst).resolve()
        blocked = _sensitive_path_error(src_path, dst_path)
        if blocked is not None:
            return blocked

        if not src_path.exists():
            return ActionResult(success=False, error=f"Source not found: {src}")

        if dst_path.exists():
            suffix = "; delete it through the confirmed delete action first" if overwrite else ""
            return ActionResult(success=False, error=f"Destination exists: {dst}{suffix}")

        try:
            if src_path.is_dir():
                shutil.copytree(src_path, dst_path)
            else:
                dst_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src_path, dst_path)
        except FileExistsError:
            # Destination appeared between the exists() check and the actual copy
            # (TOCTOU race) — report the race instead of silently overwriting.
            return ActionResult(success=False, error=f"Destination exists: {dst}")

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
        blocked = _sensitive_path_error(src_path, dst_path)
        if blocked is not None:
            return blocked

        if not src_path.exists():
            return ActionResult(success=False, error=f"Source not found: {src}")

        if dst_path.exists():
            suffix = "; delete it through the confirmed delete action first" if overwrite else ""
            return ActionResult(success=False, error=f"Destination exists: {dst}{suffix}")

        dst_path.parent.mkdir(parents=True, exist_ok=True)

        if dst_path.exists():
            # Destination appeared between the exists() check above and this point
            # (TOCTOU race). shutil.move's rename/copy fallback can otherwise
            # silently replace it on Windows.
            return ActionResult(success=False, error=f"Destination exists: {dst}")

        shutil.move(str(src_path), str(dst_path))

        return ActionResult(success=True, output=f"Moved {src_path} -> {dst_path}")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="files_rename",
    category="files",
    description="Rename a file or directory without replacing another path",
    risk="MEDIUM",
    parameters={
        "type": "object",
        "properties": {
            "src": {"type": "string", "description": "Source path"},
            "new_name": {"type": "string", "description": "New basename only"},
        },
        "required": ["src", "new_name"],
    },
    capability="FILES_MUTATE",
)
def files_rename_action(src: str, new_name: str) -> ActionResult:
    """Rename inside the current directory; never overwrite a destination."""
    if not new_name or Path(new_name).name != new_name or new_name in {".", ".."}:
        return ActionResult(success=False, error="new_name must be a basename")
    src_path = Path(src).resolve()
    return files_move_action(str(src_path), str(src_path.with_name(new_name)))


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
        blocked = _sensitive_path_error(base)
        if blocked is not None:
            return blocked
        if not base.exists():
            return ActionResult(success=False, error=f"Path not found: {path}")

        flags = 0 if case_sensitive else re.IGNORECASE
        regex = re.compile(pattern, flags)

        results = []
        for file_path in base.rglob(file_pattern):
            if not file_path.is_file():
                continue
            if _is_sensitive_path(file_path) or file_path.stat().st_size > 1_048_576:
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


@action(
    name="files_text_summary",
    category="files",
    description="Summarize a compatible UTF-8 text file without an LLM",
)
def files_text_summary_action(path: str, max_preview_lines: int = 5) -> ActionResult:
    """Return bounded text statistics and a short non-empty-line preview."""
    result = files_read_action(path, max_size=1_048_576)
    if not result.success:
        return result
    content = str(result.output or "")
    lines = content.splitlines()
    nonempty = [" ".join(line.split()) for line in lines if line.strip()]
    preview = nonempty[:max(1, min(int(max_preview_lines), 10))]
    data = {
        "path": str(Path(path).resolve()),
        "characters": len(content),
        "words": len(content.split()),
        "lines": len(lines),
        "preview": preview,
    }
    return ActionResult(
        success=True,
        output=(
            f"Texto com {data['lines']} linha(s), {data['words']} palavra(s) e "
            f"{data['characters']} caractere(s). Prévia: " + " | ".join(preview)
        ),
        data=data,
    )


@action(
    name="files_organize_by_extension",
    category="files",
    description="Organize top-level files into extension folders without deleting or replacing",
    risk="MEDIUM",
    capability="FILES_MUTATE",
)
def files_organize_by_extension_action(path: str, dry_run: bool = True) -> ActionResult:
    """Plan or perform a non-destructive, one-level organization."""
    base = Path(path).resolve()
    blocked = _sensitive_path_error(base)
    if blocked is not None:
        return blocked
    if not base.is_dir():
        return ActionResult(success=False, error=f"Not a directory: {path}")
    plan = []
    for source in sorted(item for item in base.iterdir() if item.is_file() and not item.name.startswith(".")):
        folder_name = source.suffix.casefold().lstrip(".") or "sem_extensao"
        destination = base / folder_name / source.name
        status = "READY" if not destination.exists() else "SKIPPED_DESTINATION_EXISTS"
        plan.append({"source": str(source), "destination": str(destination), "status": status})
    if dry_run:
        return ActionResult(
            success=True,
            output=f"Plano de organização criado para {len(plan)} arquivo(s); nada foi movido.",
            data={"dry_run": True, "plan": plan, "moved": 0, "deleted": 0},
        )
    moved = 0
    for item in plan:
        if item["status"] != "READY":
            continue
        source = Path(item["source"])
        destination = Path(item["destination"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        moved += 1
    return ActionResult(
        success=True,
        output=f"Organização concluída: {moved} arquivo(s) movido(s), nenhum apagado.",
        data={"dry_run": False, "plan": plan, "moved": moved, "deleted": 0},
    )


get_registry()
