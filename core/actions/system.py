"""
System Action — System monitoring and information.
"""
from __future__ import annotations

import json
import os
import platform
import sys
from datetime import datetime

import psutil

from core.action_registry import ActionResult, action, get_registry


@action(name="system_time", category="system", description="Read the local system clock", capability="READ_ONLY")
def system_time_action() -> ActionResult:
    """Return the current timezone-aware local clock without model inference."""
    observed = datetime.now().astimezone()
    return ActionResult(
        success=True,
        output=f"Agora são {observed:%H:%M}.",
        data={
            "local_iso": observed.isoformat(),
            "timezone": observed.tzname() or "LOCAL",
            "verified": True,
        },
    )


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
        boot_timestamp = psutil.boot_time()
        battery = psutil.sensors_battery()
        adapters = []
        for name, stats in psutil.net_if_stats().items():
            adapters.append({"name": name, "is_up": bool(stats.isup), "speed_mbps": int(stats.speed or 0), "mtu": int(stats.mtu or 0)})
        system_drive = os.environ.get("SystemDrive", "C:") + os.sep if platform.system() == "Windows" else os.sep
        disk = psutil.disk_usage(system_drive)
        info = {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "platform_release": platform.release(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "python_version": sys.version.split()[0],
            "hostname": platform.node(),
            "boot_time": datetime.fromtimestamp(boot_timestamp).isoformat(),
            "uptime_seconds": max(0, int(datetime.now().timestamp() - boot_timestamp)),
            "battery": None if battery is None else {
                "percent": float(battery.percent),
                "plugged": bool(battery.power_plugged),
                "seconds_left": None if battery.secsleft in {psutil.POWER_TIME_UNKNOWN, psutil.POWER_TIME_UNLIMITED} else int(battery.secsleft),
            },
            "network": {
                "connected": any(adapter["is_up"] and not adapter["name"].casefold().startswith("loopback") for adapter in adapters),
                "adapters": adapters,
            },
            "disk": {"path": system_drive, "total": disk.total, "used": disk.used, "free": disk.free, "percent": disk.percent},
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


@action(
    name="system_env",
    category="system",
    description="Set an environment variable for this process. Reading environment "
    "variables back is never allowed, regardless of variable name — there is no "
    "reliable pattern to tell secret names from public ones, so ZARA never echoes "
    "or lists environment values.",
    risk="MEDIUM",
    capability="CODE_EXECUTION",
    parameters={
        "type": "object",
        "properties": {
            "var_name": {"type": "string", "description": "Variable name to set"},
            "value": {"type": "string", "description": "Value to set"},
        },
        "required": [],
    },
)
def system_env_action(var_name: str = "", value: str = "") -> ActionResult:
    """Set an environment variable. Never reads or echoes values back."""
    if not var_name or not value:
        # No write requested (or incomplete) -- refuse the read path outright.
        # ZARA_TEST_PUBLIC_NAME=... calls with value set skip this branch.
        return ActionResult(
            success=False,
            error="ENVIRONMENT_READ_BLOCKED",
            data=None,
        )

    try:
        os.environ[var_name] = value
        return ActionResult(success=True, output=f"Variável {var_name} definida.", data=None)
    except Exception as e:
        return ActionResult(success=False, error=str(e), data=None)

get_registry()
