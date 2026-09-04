"""
Code Action — Code analysis, generation, and editing.
"""
from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

from core.action_registry import ActionResult, action, get_registry


@action(
    name="code_analyze",
    category="code",
    description="Analyze Python code structure (imports, functions, classes)",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File or directory path"},
            "include_private": {"type": "boolean", "description": "Include private members (default: false)", "default": False},
        },
        "required": ["path"],
    },
)
def code_analyze_action(path: str, include_private: bool = False) -> ActionResult:
    """Analyze Python code."""
    try:
        target = Path(path).resolve()
        if not target.exists():
            return ActionResult(success=False, error=f"Path not found: {path}")

        files = [target] if target.is_file() else list(target.rglob("*.py"))

        results = []
        for f in files:
            try:
                content = f.read_text(encoding="utf-8")
                tree = ast.parse(content)

                imports = []
                functions = []
                classes = []

                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            imports.append(alias.name)
                    elif isinstance(node, ast.ImportFrom):
                        module = node.module or ""
                        for alias in node.names:
                            imports.append(f"{module}.{alias.name}")
                    elif isinstance(node, ast.FunctionDef):
                        if include_private or not node.name.startswith("_"):
                            functions.append({
                                "name": node.name,
                                "line": node.lineno,
                                "args": [a.arg for a in node.args.args],
                                "returns": ast.unparse(node.returns) if node.returns else None,
                                "docstring": ast.get_docstring(node),
                            })
                    elif isinstance(node, ast.ClassDef):
                        if include_private or not node.name.startswith("_"):
                            methods = []
                            for item in node.body:
                                if isinstance(item, ast.FunctionDef):
                                    if include_private or not item.name.startswith("_"):
                                        methods.append(item.name)
                            classes.append({
                                "name": node.name,
                                "line": node.lineno,
                                "methods": methods,
                                "bases": [ast.unparse(b) for b in node.bases],
                                "docstring": ast.get_docstring(node),
                            })

                results.append({
                    "file": str(f.relative_to(target) if target.is_dir() else f.name),
                    "imports": imports,
                    "functions": functions,
                    "classes": classes,
                })
            except SyntaxError as e:
                results.append({"file": str(f), "error": f"Syntax error: {e}"})
            except Exception as e:
                results.append({"file": str(f), "error": str(e)})

        return ActionResult(
            success=True,
            output=json.dumps(results, indent=2),
            data={"files": results, "count": len(results)}
        )
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="code_lint",
    category="code",
    description="Lint Python code with ruff",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File or directory path (default: project root)", "default": "."},
            "fix": {"type": "boolean", "description": "Auto-fix issues (default: false)", "default": False},
        },
        "required": [],
    },
)
def code_lint_action(path: str = ".", fix: bool = False) -> ActionResult:
    """Lint code with ruff."""
    try:
        from core.paths import project_root
        if path == ".":
            path = str(project_root())

        cmd = ["ruff", "check"]
        if fix:
            cmd.append("--fix")
        cmd.append(path)

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        return ActionResult(
            success=result.returncode == 0,
            output=result.stdout or result.stderr,
            data={"returncode": result.returncode, "fixed": fix}
        )
    except FileNotFoundError:
        return ActionResult(success=False, error="ruff not installed. Run: uv pip install ruff")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="code_format",
    category="code",
    description="Format Python code with ruff",
    risk="MEDIUM",
    capability="FILES_MUTATE",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File or directory path (default: project root)", "default": "."},
        },
        "required": [],
    },
)
def code_format_action(path: str = ".") -> ActionResult:
    """Format code with ruff."""
    try:
        from core.paths import project_root
        if path == ".":
            path = str(project_root())

        result = subprocess.run(
            ["ruff", "format", path],
            capture_output=True, text=True, timeout=60
        )

        return ActionResult(
            success=result.returncode == 0,
            output=result.stdout or result.stderr,
            data={"returncode": result.returncode}
        )
    except FileNotFoundError:
        return ActionResult(success=False, error="ruff not installed")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="code_test",
    category="code",
    description="Run pytest tests",
    risk="MEDIUM",
    capability="CODE_EXECUTION",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Test path (default: tests/)", "default": "tests"},
            "pattern": {"type": "string", "description": "Test pattern (default: test_*.py)"},
            "verbose": {"type": "boolean", "description": "Verbose output (default: true)", "default": True},
            "coverage": {"type": "boolean", "description": "Run with coverage (default: false)", "default": False},
        },
        "required": [],
    },
)
def code_test_action(path: str = "tests", pattern: str = "", verbose: bool = True, coverage: bool = False) -> ActionResult:
    """Run pytest tests."""
    try:
        from core.paths import project_root
        test_path = Path(path)
        if not test_path.is_absolute():
            test_path = project_root() / path

        cmd = ["pytest"]
        if verbose:
            cmd.append("-v")
        if coverage:
            cmd.extend(["--cov=core", "--cov-report=term-missing"])
        if pattern:
            cmd.extend(["-k", pattern])
        cmd.append(str(test_path))

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        return ActionResult(
            success=result.returncode == 0,
            output=result.stdout + ("\n" + result.stderr if result.stderr else ""),
            data={"returncode": result.returncode}
        )
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="code_generate",
    category="code",
    description="Generate code from template/description",
    risk="MEDIUM",
    parameters={
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "Natural language description of what to generate"},
            "language": {"type": "string", "description": "Programming language (default: python)", "default": "python"},
            "template": {"type": "string", "description": "Optional template name"},
        },
        "required": ["description"],
    },
)
def code_generate_action(description: str, language: str = "python", template: str = "") -> ActionResult:
    """Generate code from a basic language template."""
    try:
        # Basic template
        if language == "python":
            template_code = f'''"""
{description}
"""
from __future__ import annotations


def main():
    """Main entry point."""
    pass


if __name__ == "__main__":
    main()
'''
        else:
            template_code = f"// {description}\n\n// TODO: Implement"

        return ActionResult(
            success=True,
            output=template_code,
            data={"source": "template", "language": language}
        )
    except Exception as e:
        return ActionResult(success=False, error=str(e))


get_registry()
