"""tests/regression_suite.py -- Protocolo Anti-Regressão (Alex, 2026-08-28)

Isolado: não plugado em nenhum hook automático ainda. Duas peças:

1. `run_golden_path_smoke()` -- roda, num processo próprio (via
   `.venv\\Scripts\\python.exe -m pytest`, nunca `python` solto), os arquivos
   de teste que cobrem o que já quebrou fisicamente antes neste projeto
   (volume, brilho, intent de PC). Devolve passou/quantidade/saída -- nunca
   esconde falha.
2. `create_restore_point(label)` -- cria uma TAG git (ação aditiva, segura)
   antes de uma mudança arriscada. NÃO existe `rollback_automatico()` aqui:
   `git reset --hard` é proibido sem autorização nomeada
   (`.claude/rules/governance.md`), então esta peça só devolve o COMANDO
   exato pra reverter -- quem decide rodar é humano (ou Claude com
   autorização daquela tarefa específica), nunca automático.
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_PYTHON = _PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"

# Arquivos que já pegaram regressão física real neste projeto -- ver
# docs/audits/ e o histórico de commits. Golden path = "nunca deve quebrar
# de novo sem a gente saber na hora".
_GOLDEN_PATH_FILES = (
    "tests/test_volume_context.py",
    "tests/test_brightness_control.py",
    "tests/test_new_features.py",
)


class RegressionSuiteError(RuntimeError):
    """Levantado quando o próprio processo de teste não consegue rodar
    (python ausente, pytest ausente) -- diferente de "os testes rodaram e
    falharam", que é reportado normalmente, não levantado."""


@dataclass(frozen=True, slots=True)
class SmokeResult:
    passed: bool
    exit_code: int
    summary: str
    output: str = field(repr=False)


def run_golden_path_smoke(
    *,
    python_exe: Path | str | None = None,
    test_files: tuple[str, ...] = _GOLDEN_PATH_FILES,
    cwd: Path | str | None = None,
) -> SmokeResult:
    """Roda o subconjunto golden-path de pytest num processo próprio.
    `passed=False` nunca é escondido -- `summary`/`output` trazem o motivo."""
    python_path = Path(python_exe) if python_exe is not None else _DEFAULT_PYTHON
    root = Path(cwd) if cwd is not None else _PROJECT_ROOT
    if not python_path.exists():
        raise RegressionSuiteError(f"Python do projeto não encontrado: {python_path}")

    try:
        result = subprocess.run(
            [str(python_path), "-m", "pytest", "-q", *test_files],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RegressionSuiteError(f"Não consegui rodar pytest: {exc}") from exc

    output = result.stdout + result.stderr
    last_line = next((line for line in reversed(output.splitlines()) if line.strip()), "")
    return SmokeResult(
        passed=result.returncode == 0,
        exit_code=result.returncode,
        summary=last_line,
        output=output,
    )


def create_restore_point(label: str, *, cwd: Path | str | None = None) -> str:
    """Cria uma tag git leve como ponto de restauração ANTES de uma mudança
    arriscada. Ação puramente aditiva -- nunca apaga, nunca move HEAD.
    Devolve o nome da tag criada."""
    clean_label = "".join(c if c.isalnum() or c in "-_." else "-" for c in str(label or "").strip())
    if not clean_label:
        raise ValueError("label não pode ser vazio.")

    root = Path(cwd) if cwd is not None else _PROJECT_ROOT
    tag_name = f"restore-point-{clean_label}"
    result = subprocess.run(
        ["git", "tag", tag_name],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode != 0:
        raise RegressionSuiteError(f"Não consegui criar a tag de restauração: {result.stderr.strip()}")
    return tag_name


def rollback_command_for(tag_name: str) -> str:
    """Devolve o COMANDO exato pra voltar ao ponto de restauração --
    NUNCA executa. `git reset --hard` exige autorização nomeada
    (governance.md); esta função só monta a instrução pra um humano decidir."""
    if not tag_name.strip():
        raise ValueError("tag_name não pode ser vazio.")
    return f"git reset --hard {tag_name.strip()}"


if __name__ == "__main__":
    outcome = run_golden_path_smoke()
    print(outcome.summary)
    sys.exit(outcome.exit_code)
