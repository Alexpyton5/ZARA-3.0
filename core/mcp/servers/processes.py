"""
ZARA 3.0 - MCP Processes Server
MCP server for Windows process management.
"""

from __future__ import annotations

import os
import subprocess

import psutil

from core.mcp.base_server import StdioMCPServer


class ProcessesMCPServer(StdioMCPServer):
    """MCP server for process management."""

    def __init__(self):
        super().__init__("zara-processes", "1.0.0")
        self._register_tools()

    def _register_tools(self):
        """Register process management tools."""

        @self.tool(
            name="process_list",
            description="List running processes",
            input_schema={
                "type": "object",
                "properties": {
                    "filter": {"type": "string", "description": "Filter by process name (partial match)"},
                    "limit": {"type": "integer", "default": 100, "description": "Max results"},
                },
            }
        )
        async def process_list(filter: str = "", limit: int = 100) -> dict:
            try:
                processes = []
                for proc in psutil.process_iter(["pid", "name", "exe", "cmdline", "cpu_percent", "memory_info", "status", "create_time", "username"]):
                    try:
                        info = proc.info
                        if filter and filter.lower() not in (info.get("name") or "").lower():
                            continue
                        processes.append({
                            "pid": info["pid"],
                            "name": info["name"],
                            "exe": info["exe"],
                            "cmdline": info["cmdline"],
                            "cpu_percent": info["cpu_percent"],
                            "memory_mb": round(info["memory_info"].rss / 1024 / 1024, 1) if info["memory_info"] else 0,
                            "status": info["status"],
                            "create_time": info["create_time"],
                            "username": info["username"],
                        })
                        if len(processes) >= limit:
                            break
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                return {"success": True, "processes": processes, "count": len(processes)}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="process_get",
            description="Get detailed information about a process",
            input_schema={
                "type": "object",
                "properties": {
                    "pid": {"type": "integer", "description": "Process ID"},
                },
                "required": ["pid"],
            }
        )
        async def process_get(pid: int) -> dict:
            try:
                proc = psutil.Process(pid)
                with proc.oneshot():
                    info = {
                        "pid": proc.pid,
                        "name": proc.name(),
                        "exe": proc.exe(),
                        "cmdline": proc.cmdline(),
                        "cwd": proc.cwd(),
                        "status": proc.status(),
                        "create_time": proc.create_time(),
                        "cpu_percent": proc.cpu_percent(),
                        "memory_info": {
                            "rss": proc.memory_info().rss,
                            "vms": proc.memory_info().vms,
                        },
                        "num_threads": proc.num_threads(),
                        "username": proc.username(),
                        "ppid": proc.ppid(),
                        "children": [p.pid for p in proc.children()],
                    }
                return {"success": True, "process": info}
            except psutil.NoSuchProcess:
                return {"success": False, "error": f"Process not found: {pid}"}
            except psutil.AccessDenied:
                return {"success": False, "error": f"Access denied: {pid}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="process_kill",
            description="Terminate a process",
            input_schema={
                "type": "object",
                "properties": {
                    "pid": {"type": "integer", "description": "Process ID"},
                    "force": {"type": "boolean", "default": False, "description": "Force kill (SIGKILL)"},
                },
                "required": ["pid"],
            }
        )
        async def process_kill(pid: int, force: bool = False) -> dict:
            try:
                proc = psutil.Process(pid)
                if force:
                    proc.kill()
                else:
                    proc.terminate()

                # Wait a bit for termination
                try:
                    proc.wait(timeout=3)
                except psutil.TimeoutExpired:
                    if not force:
                        proc.kill()
                        proc.wait(timeout=1)

                return {"success": True, "pid": pid, "force": force}
            except psutil.NoSuchProcess:
                return {"success": False, "error": f"Process not found: {pid}"}
            except psutil.AccessDenied:
                return {"success": False, "error": f"Access denied: {pid}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="process_start",
            description="Start a new process",
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Command to execute"},
                    "args": {"type": "array", "items": {"type": "string"}, "description": "Command arguments"},
                    "cwd": {"type": "string", "description": "Working directory"},
                    "env": {"type": "object", "description": "Environment variables"},
                    "detached": {"type": "boolean", "default": False, "description": "Run detached"},
                },
                "required": ["command"],
            }
        )
        async def process_start(command: str, args: list[str] = None, cwd: str = None, env: dict = None, detached: bool = False) -> dict:
            try:
                args = args or []
                full_cmd = [command] + args

                # Prepare environment
                proc_env = os.environ.copy()
                if env:
                    proc_env.update(env)

                if detached:
                    # Start detached
                    creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                    proc = subprocess.Popen(
                        full_cmd,
                        cwd=cwd,
                        env=proc_env,
                        creationflags=creationflags,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        stdin=subprocess.DEVNULL,
                    )
                else:
                    proc = subprocess.Popen(
                        full_cmd,
                        cwd=cwd,
                        env=proc_env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                    )

                return {"success": True, "pid": proc.pid, "command": full_cmd}
            except FileNotFoundError:
                return {"success": False, "error": f"Command not found: {command}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="process_wait",
            description="Wait for a process to exit",
            input_schema={
                "type": "object",
                "properties": {
                    "pid": {"type": "integer", "description": "Process ID"},
                    "timeout": {"type": "integer", "default": 30, "description": "Timeout in seconds"},
                },
                "required": ["pid"],
            }
        )
        async def process_wait(pid: int, timeout: int = 30) -> dict:
            try:
                proc = psutil.Process(pid)
                return_code = proc.wait(timeout=timeout)
                return {"success": True, "pid": pid, "return_code": return_code}
            except psutil.NoSuchProcess:
                return {"success": False, "error": f"Process not found: {pid}"}
            except psutil.TimeoutExpired:
                return {"success": False, "error": f"Timeout waiting for process: {pid}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="process_suspend",
            description="Suspend a process",
            input_schema={
                "type": "object",
                "properties": {
                    "pid": {"type": "integer", "description": "Process ID"},
                },
                "required": ["pid"],
            }
        )
        async def process_suspend(pid: int) -> dict:
            try:
                proc = psutil.Process(pid)
                proc.suspend()
                return {"success": True, "pid": pid, "action": "suspended"}
            except psutil.NoSuchProcess:
                return {"success": False, "error": f"Process not found: {pid}"}
            except psutil.AccessDenied:
                return {"success": False, "error": f"Access denied: {pid}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="process_resume",
            description="Resume a suspended process",
            input_schema={
                "type": "object",
                "properties": {
                    "pid": {"type": "integer", "description": "Process ID"},
                },
                "required": ["pid"],
            }
        )
        async def process_resume(pid: int) -> dict:
            try:
                proc = psutil.Process(pid)
                proc.resume()
                return {"success": True, "pid": pid, "action": "resumed"}
            except psutil.NoSuchProcess:
                return {"success": False, "error": f"Process not found: {pid}"}
            except psutil.AccessDenied:
                return {"success": False, "error": f"Access denied: {pid}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="process_priority",
            description="Get or set process priority",
            input_schema={
                "type": "object",
                "properties": {
                    "pid": {"type": "integer", "description": "Process ID"},
                    "priority": {"type": "string", "enum": ["idle", "below_normal", "normal", "above_normal", "high", "realtime"], "description": "Priority to set (optional, omit to get current)"},
                },
                "required": ["pid"],
            }
        )
        async def process_priority(pid: int, priority: str = None) -> dict:
            try:
                proc = psutil.Process(pid)

                priority_map = {
                    "idle": psutil.IDLE_PRIORITY_CLASS,
                    "below_normal": psutil.BELOW_NORMAL_PRIORITY_CLASS,
                    "normal": psutil.NORMAL_PRIORITY_CLASS,
                    "above_normal": psutil.ABOVE_NORMAL_PRIORITY_CLASS,
                    "high": psutil.HIGH_PRIORITY_CLASS,
                    "realtime": psutil.REALTIME_PRIORITY_CLASS,
                }

                if priority:
                    if priority not in priority_map:
                        return {"success": False, "error": f"Invalid priority: {priority}"}
                    proc.nice(priority_map[priority])
                    return {"success": True, "pid": pid, "priority": priority}
                else:
                    current = proc.nice()
                    # Reverse map
                    rev_map = {v: k for k, v in priority_map.items()}
                    return {"success": True, "pid": pid, "priority": rev_map.get(current, "unknown")}
            except psutil.NoSuchProcess:
                return {"success": False, "error": f"Process not found: {pid}"}
            except psutil.AccessDenied:
                return {"success": False, "error": f"Access denied: {pid}"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="process_children",
            description="Get child processes",
            input_schema={
                "type": "object",
                "properties": {
                    "pid": {"type": "integer", "description": "Parent process ID"},
                    "recursive": {"type": "boolean", "default": False, "description": "Get all descendants"},
                },
                "required": ["pid"],
            }
        )
        async def process_children(pid: int, recursive: bool = False) -> dict:
            try:
                proc = psutil.Process(pid)
                children = proc.children(recursive=recursive)
                result = []
                for child in children:
                    with child.oneshot():
                        result.append({
                            "pid": child.pid,
                            "name": child.name(),
                            "exe": child.exe(),
                            "status": child.status(),
                            "cpu_percent": child.cpu_percent(),
                            "memory_mb": round(child.memory_info().rss / 1024 / 1024, 1),
                        })
                return {"success": True, "children": result, "count": len(result)}
            except psutil.NoSuchProcess:
                return {"success": False, "error": f"Process not found: {pid}"}
            except Exception as e:
                return {"success": False, "error": str(e)}


def main():
    """Entry point for running the server."""
    import asyncio
    server = ProcessesMCPServer()
    asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()
