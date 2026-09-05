"""System Control Skill — wraps core system actions."""
from __future__ import annotations

from core.action_registry import get_registry
from core.actions.system import (
    system_time_action,
    system_info_action,
    system_metrics_action,
    system_processes_action,
    system_kill_action,
    system_env_action,
)

PLUGIN = {
    "name": "system_control",
    "description": (
        "System monitoring and control: time, info, metrics, processes, "
        "kill process, environment variables. Use for system queries and "
        "management. Does NOT cover volume, brightness, or window ops "
        "(those are separate skills)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action to perform",
                "enum": ["time", "info", "metrics", "processes", "kill", "env"],
            },
            "detailed": {"type": "BOOLEAN", "description": "Detailed system info", "default": False},
            "interval": {"type": "NUMBER", "description": "CPU measurement interval (seconds)", "default": 0.5},
            "filter": {"type": "STRING", "description": "Filter processes by name"},
            "sort_by": {"type": "STRING", "description": "Sort field", "enum": ["cpu", "memory", "name", "pid"], "default": "cpu"},
            "limit": {"type": "INTEGER", "description": "Max processes to return", "default": 20},
            "pid": {"type": "INTEGER", "description": "Process ID to kill"},
            "force": {"type": "BOOLEAN", "description": "Force kill", "default": False},
            "var_name": {"type": "STRING", "description": "Environment variable name"},
            "value": {"type": "STRING", "description": "Value to set (omit to get)"},
        },
        "required": ["action"],
    },
    "category": "system",
    "version": "1.0.0",
    "author": "ZARA",
}


def run(parameters: dict, context=None) -> str:
    action_name = parameters.get("action")
    registry = get_registry()

    try:
        if action_name == "time":
            result = registry.execute("system_time")
        elif action_name == "info":
            result = registry.execute("system_info", detailed=parameters.get("detailed", False))
        elif action_name == "metrics":
            result = registry.execute("system_metrics", interval=parameters.get("interval", 0.5))
        elif action_name == "processes":
            result = registry.execute(
                "system_processes",
                filter=parameters.get("filter", ""),
                sort_by=parameters.get("sort_by", "cpu"),
                limit=parameters.get("limit", 20),
            )
        elif action_name == "kill":
            pid = parameters.get("pid")
            if pid is None:
                return "Erro: 'pid' é obrigatório para kill."
            result = registry.execute("system_kill", pid=pid, force=parameters.get("force", False))
        elif action_name == "env":
            result = registry.execute(
                "system_env",
                var_name=parameters.get("var_name", ""),
                value=parameters.get("value", ""),
            )
        else:
            return f"Ação desconhecida: {action_name}. Use: time, info, metrics, processes, kill, env."

        if result.success:
            return result.output or "Feito."
        return f"Falha: {result.error}"
    except Exception as e:
        return f"Erro na skill system_control: {e}"