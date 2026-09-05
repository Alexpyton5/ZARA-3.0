"""Code Helper Skill — wraps core code actions."""
from __future__ import annotations

from core.action_registry import get_registry
from core.actions.code import (
    code_analyze_action,
    code_lint_action,
    code_format_action,
    code_test_action,
    code_generate_action,
)

PLUGIN = {
    "name": "code_helper",
    "description": (
        "Code analysis and helper tools: analyze structure, lint, format, test, "
        "generate code from description. Use for development assistance, "
        "code quality checks, and quick code generation. "
        "Works with Python files primarily."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action to perform",
                "enum": ["analyze", "lint", "format", "test", "generate"],
            },
            "path": {"type": "STRING", "description": "File or directory path (default: project root)", "default": "."},
            "include_private": {"type": "BOOLEAN", "description": "Include private members", "default": False},
            "fix": {"type": "BOOLEAN", "description": "Auto-fix issues (for lint)", "default": False},
            "pattern": {"type": "STRING", "description": "Test pattern (default: test_*.py)", "default": ""},
            "verbose": {"type": "BOOLEAN", "description": "Verbose test output", "default": True},
            "coverage": {"type": "BOOLEAN", "description": "Run with coverage", "default": False},
            "description": {"type": "STRING", "description": "Natural language description of what to generate"},
            "language": {"type": "STRING", "description": "Programming language (default: python)", "default": "python"},
            "template": {"type": "STRING", "description": "Optional template name", "default": ""},
        },
        "required": ["action"],
    },
    "category": "code",
    "version": "1.0.0",
    "author": "ZARA",
}


def run(parameters: dict, context=None) -> str:
    action_name = parameters.get("action")
    registry = get_registry()

    try:
        if action_name == "analyze":
            file_path = parameters.get("path", ".")
            result = registry.execute(
                "code_analyze",
                path=file_path,
                include_private=parameters.get("include_private", False),
            )
        elif action_name == "lint":
            file_path = parameters.get("path", ".")
            result = registry.execute(
                "code_lint",
                path=file_path,
                fix=parameters.get("fix", False),
            )
        elif action_name == "format":
            file_path = parameters.get("path", ".")
            result = registry.execute(
                "code_format",
                path=file_path,
            )
        elif action_name == "test":
            test_path = parameters.get("path", "tests")
            result = registry.execute(
                "code_test",
                path=test_path,
                pattern=parameters.get("pattern", ""),
                verbose=parameters.get("verbose", True),
                coverage=parameters.get("coverage", False),
            )
        elif action_name == "generate":
            description = parameters.get("description")
            if not description:
                return "Erro: 'description' é obrigatório para generate."
            result = registry.execute(
                "code_generate",
                description=description,
                language=parameters.get("language", "python"),
                template=parameters.get("template", ""),
            )
        else:
            return f"Ação desconhecida: {action_name}. Use: analyze, lint, format, test, generate."

        if result.success:
            return result.output or "Feito."
        return f"Falha: {result.error}"
    except Exception as e:
        return f"Erro na skill code_helper: {e}"