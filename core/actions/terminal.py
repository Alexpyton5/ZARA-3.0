"""
Terminal Action — Execute shell commands.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from core.action_registry import ActionResult, action, get_registry


@action(
    name="terminal",
    category="system",
    description="Execute a shell command and return output",
    risk="HIGH",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "cwd": {"type": "string", "description": "Working directory (default: project root)", "default": "."},
            "timeout": {"type": "integer", "description": "Timeout in seconds (default: 60)", "default": 60},
            "capture": {"type": "boolean", "description": "Capture stdout/stderr (default: true)", "default": True},
        },
        "required": ["command"],
    },
    capability="CODE_EXECUTION",
)
def terminal_action(command: str, cwd: str = ".", timeout: int = 60, capture: bool = True) -> ActionResult:
    """Execute a shell command."""
    try:
        # Resolve working directory
        if cwd == ".":
            from core.paths import project_root
            cwd = str(project_root())

        cwd_path = Path(cwd).resolve()
        if not cwd_path.exists():
            return ActionResult(success=False, error=f"Working directory not found: {cwd}")

        # Prepare command
        if sys.platform == "win32":
            # On Windows, use cmd /c for shell built-ins
            full_cmd = ["cmd", "/c", command]
        else:
            full_cmd = ["/bin/bash", "-c", command]

        # Execute
        result = subprocess.run(
            full_cmd,
            cwd=str(cwd_path),
            capture_output=capture,
            text=True,
            timeout=timeout,
            shell=False,
        )

        output = ""
        if capture:
            if result.stdout:
                output += result.stdout
            if result.stderr:
                if output:
                    output += "\n--- STDERR ---\n"
                output += result.stderr

        if result.returncode == 0:
            return ActionResult(success=True, output=output or "Command completed successfully", data={"returncode": 0})
        else:
            return ActionResult(success=False, error=output or f"Command failed with exit code {result.returncode}", data={"returncode": result.returncode})

    except subprocess.TimeoutExpired:
        return ActionResult(success=False, error=f"Command timed out after {timeout}s")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="terminal_bg",
    category="system",
    description="Start a background shell command (returns immediately)",
    risk="HIGH",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Shell command to execute"},
            "cwd": {"type": "string", "description": "Working directory (default: project root)", "default": "."},
            "name": {"type": "string", "description": "Optional name for the background process"},
        },
        "required": ["command"],
    },
    capability="CODE_EXECUTION",
)
def terminal_bg_action(command: str, cwd: str = ".", name: str = "") -> ActionResult:
    """Start a background process."""
    try:
        if cwd == ".":
            from core.paths import project_root
            cwd = str(project_root())

        cwd_path = Path(cwd).resolve()

        if sys.platform == "win32":
            full_cmd = ["cmd", "/c", command]
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        else:
            full_cmd = ["/bin/bash", "-c", command]
            flags = 0

        proc = subprocess.Popen(
            full_cmd,
            cwd=str(cwd_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=flags,
        )

        return ActionResult(
            success=True,
            output=f"STARTED: background process (PID: {proc.pid})",
            data={"status": "STARTED", "pid": proc.pid, "name": name or command[:50]},
            verificado=False,
        )
    except Exception as e:
        return ActionResult(success=False, error=str(e))


# Register with registry on import
get_registry()
