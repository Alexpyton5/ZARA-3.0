"""ZARA-BOILERPLATE-GEN-001 (Alex, 2026-08-28)

Peca isolada. Cria a estrutura inicial de um projeto Python (src/, tests/,
requirements.txt, .gitignore). Recusa-se a sobrescrever um projeto que ja
existe no destino -- criar boilerplate por cima de trabalho existente seria
exatamente o tipo de "perda de trabalho por suposicao" que as regras deste
projeto proibem.
"""
from __future__ import annotations

from pathlib import Path

_GITIGNORE_TEMPLATE = """\
__pycache__/
*.pyc
.venv/
venv/
.env
*.egg-info/
dist/
build/
.pytest_cache/
"""


class BoilerplateExistsError(RuntimeError):
    """Levantado quando o diretório do projeto já existe -- nunca
    sobrescreve silenciosamente."""


def create_python_boilerplate(project_name: str, target_dir: str) -> str:
    """Cria `<target_dir>/<project_name>/` com `src/`, `tests/`,
    `requirements.txt` e `.gitignore`. Devolve o caminho absoluto criado.
    Levanta BoilerplateExistsError se o destino já existir."""
    name = str(project_name or "").strip()
    if not name:
        raise ValueError("project_name não pode ser vazio.")

    project_path = Path(target_dir).expanduser().resolve() / name
    if project_path.exists():
        raise BoilerplateExistsError(f"'{project_path}' já existe -- não sobrescrevo projeto existente.")

    (project_path / "src").mkdir(parents=True)
    (project_path / "tests").mkdir(parents=True)
    (project_path / "requirements.txt").write_text("", encoding="utf-8")
    (project_path / ".gitignore").write_text(_GITIGNORE_TEMPLATE, encoding="utf-8")
    (project_path / "src" / "__init__.py").write_text("", encoding="utf-8")
    (project_path / "tests" / "__init__.py").write_text("", encoding="utf-8")

    return str(project_path)
