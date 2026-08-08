"""
System Action — System monitoring and information.
"""
from __future__ import annotations

import json
import os
import platform
import re
import sys
from datetime import datetime

import psutil

from core.action_registry import ActionResult, action, get_registry


@action(
    name="system_info",
    category="system",
    description="Get system information",
    parameters={
        "type": "object",
        "properties": {
            "detailed": {"type": "boolean", "description": "Include detailed info (default: false)", "default": False},
        },
        "required": [],
    },
)
def system_info_action(detailed: bool = False) -> ActionResult:
    """Get system information."""
    try:
        info = {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "platform_release": platform.release(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "python_version": sys.version.split()[0],
            "hostname": platform.node(),
            "boot_time": datetime.fromtimestamp(psutil.boot_time()).isoformat(),
        }

        if detailed:
            info.update({
                "cpu_count_logical": psutil.cpu_count(logical=True),
                "cpu_count_physical": psutil.cpu_count(logical=False),
                "cpu_freq": psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None,
                "memory_total": psutil.virtual_memory().total,
                "memory_available": psutil.virtual_memory().available,
                "disk_partitions": [p._asdict() for p in psutil.disk_partitions()],
                "network_interfaces": list(psutil.net_if_addrs().keys()),
                "users": [u._asdict() for u in psutil.users()],
            })

        return ActionResult(
            success=True,
            output=json.dumps(info, indent=2),
            data=info
        )
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="system_metrics",
    category="system",
    description="Get real-time system metrics (CPU, RAM, disk, network)",
    parameters={
        "type": "object",
        "properties": {
            "interval": {"type": "number", "description": "CPU measurement interval in seconds (default: 0.5)", "default": 0.5},
        },
        "required": [],
    },
)
def system_metrics_action(interval: float = 0.5) -> ActionResult:
    """Get real-time system metrics."""
    try:
        cpu_percent = psutil.cpu_percent(interval=interval)
        cpu_per_core = psutil.cpu_percent(interval=0, percpu=True)

        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()

        disk = psutil.disk_usage("/")

        net_io = psutil.net_io_counters()

        # Process count
        processes = len(psutil.pids())

        # Top processes by CPU
        top_cpu = []
        for proc in sorted(psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']),
                          key=lambda p: p.info['cpu_percent'] or 0, reverse=True)[:5]:
            try:
                top_cpu.append({
                    "pid": proc.info['pid'],
                    "name": proc.info['name'],
                    "cpu": proc.info['cpu_percent'],
                    "mem": proc.info['memory_percent'],
                })
            except Exception:
                pass

        metrics = {
            "timestamp": datetime.now().isoformat(),
            "cpu": {
                "total": cpu_percent,
                "per_core": cpu_per_core,
            },
            "memory": {
                "total": mem.total,
                "used": mem.used,
                "available": mem.available,
                "percent": mem.percent,
            },
            "swap": {
                "total": swap.total,
                "used": swap.used,
                "percent": swap.percent,
            },
            "disk": {
                "total": disk.total,
                "used": disk.used,
                "free": disk.free,
                "percent": disk.percent,
            },
            "network": {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv,
                "packets_sent": net_io.packets_sent,
                "packets_recv": net_io.packets_recv,
            },
            "processes": processes,
            "top_cpu": top_cpu,
        }

        # Format output
        output = f"""CPU: {cpu_percent:.1f}% | RAM: {mem.percent:.1f}% | Disk: {disk.percent:.1f}%
Net: ↑{net_io.bytes_sent/1024/1024:.1f}MB ↓{net_io.bytes_recv/1024/1024:.1f}MB | Processes: {processes}"""

        return ActionResult(
            success=True,
            output=output,
            data=metrics
        )
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="system_processes",
    category="system",
    description="List running processes",
    parameters={
        "type": "object",
        "properties": {
            "filter": {"type": "string", "description": "Filter by name (substring)"},
            "sort_by": {"type": "string", "description": "Sort field (default: cpu)", "default": "cpu", "enum": ["cpu", "memory", "name", "pid"]},
            "limit": {"type": "integer", "description": "Max results (default: 20)", "default": 20},
        },
        "required": [],
    },
)
def system_processes_action(filter: str = "", sort_by: str = "cpu", limit: int = 20) -> ActionResult:
    """List running processes."""
    try:
        procs = []
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent', 'username', 'status', 'create_time']):
            try:
                info = proc.info
                if filter and filter.lower() not in (info['name'] or '').lower():
                    continue
                procs.append({
                    "pid": info['pid'],
                    "name": info['name'],
                    "cpu": info['cpu_percent'] or 0,
                    "memory": info['memory_percent'] or 0,
                    "user": info['username'],
                    "status": info['status'],
                    "started": datetime.fromtimestamp(info['create_time']).isoformat() if info['create_time'] else None,
                })
            except Exception:
                pass

        # Sort
        reverse = sort_by in ("cpu", "memory")
        procs.sort(key=lambda p: p.get(sort_by, 0), reverse=reverse)

        procs = procs[:limit]

        return ActionResult(
            success=True,
            output=json.dumps(procs, indent=2),
            data={"processes": procs, "count": len(procs)}
        )
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="system_kill",
    category="system",
    description="Kill a process by PID",
    risk="HIGH",
    parameters={
        "type": "object",
        "properties": {
            "pid": {"type": "integer", "description": "Process ID"},
            "force": {"type": "boolean", "description": "Force kill (SIGKILL/TerminateProcess)", "default": False},
        },
        "required": ["pid"],
    },
    capability="SYSTEM_POWER",
)
def system_kill_action(pid: int, force: bool = False) -> ActionResult:
    """Kill a process."""
    try:
        proc = psutil.Process(pid)
        name = proc.name()

        if force:
            proc.kill()
        else:
            proc.terminate()

        # Wait a bit
        proc.wait(timeout=5)

        return ActionResult(success=True, output=f"Killed process {pid} ({name})")
    except psutil.NoSuchProcess:
        return ActionResult(success=False, error=f"Process {pid} not found")
    except psutil.AccessDenied:
        return ActionResult(success=False, error=f"Access denied to kill process {pid}")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


_SENSITIVE_ENV = re.compile(
    r"(API[_-]?KEY|SECRET|PASSWORD|TOKEN|PASSWD|CREDENTIAL|AUTH|PRIVATE[_-]?KEY|"
    r"OPENAI|GEMINI|GROQ|NVIDIA|ANTHROPIC|OPENROUTER|GOOGLE_API|DEEPSEEK)",
    re.IGNORECASE,
)

def _redact_env(env: dict) -> dict:
    """Return a copy with sensitive values redacted (never expose secrets)."""
    out = {}
    for k, v in env.items():
        if _SENSITIVE_ENV.search(k):
            out[k] = "[REDACTED]" if v else v
        else:
            out[k] = v
    return out


@action(
    name="system_env",
    category="system",
    description="Get or set environment variables",
    parameters={
        "type": "object",
        "properties": {
            "var_name": {"type": "string", "description": "Variable name (omit to list all)"},
            "value": {"type": "string", "description": "Value to set (omit to get)"},
        },
        "required": [],
    },
)
def system_env_action(var_name: str = "", value: str = "") -> ActionResult:
    """Get or set environment variables. Sensitive values are redacted."""
    try:
        if not var_name:
            # List all (redacted)
            env = _redact_env(dict(os.environ))
            return ActionResult(
                success=True,
                output=json.dumps(env, indent=2),
                data=env
            )

        if not value:
            # Get (redacted)
            val = os.environ.get(var_name)
            if val is None:
                return ActionResult(success=False, error=f"Variable {var_name} not set")
            if _SENSITIVE_ENV.search(var_name):
                return ActionResult(success=True, output="[REDACTED]", data={var_name: "[REDACTED]"})
            return ActionResult(success=True, output=val, data={var_name: val})

        # Set
        os.environ[var_name] = value
        return ActionResult(success=True, output=f"Set {var_name}=[REDACTED]" if _SENSITIVE_ENV.search(var_name) else f"Set {var_name}={value}")

    except Exception as e:
        return ActionResult(success=False, error=str(e))

get_registry()
