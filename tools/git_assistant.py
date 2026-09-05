"""ZARA-GIT-ASSISTANT-001 (Alex, 2026-08-28)

Peca isolada. generate_smart_commit() SO SUGERE uma mensagem no padrao
Conventional Commits -- NUNCA roda `git commit` sozinha. Mesma regra que ja
vale pra mim (Claude Code) neste projeto: nunca commitar sem o humano ver a
mensagem antes. Quem quiser commitar de fato usa a mensagem devolvida com
`git commit -m "<mensagem>"` por conta propria.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# Extensao/pasta -> tipo Conventional Commit mais provavel, nessa ordem de
# prioridade (primeira pasta que bater decide o escopo).
_SCOPE_HINTS: tuple[tuple[str, str], ...] = (
    ("tests/", "test"),
    ("docs/", "docs"),
    (".md", "docs"),
    ("requirements.txt", "chore"),
    ("package.json", "chore"),
)


class GitAssistantError(RuntimeError):
    """Levantado quando não dá pra ler o estado do git (não é repo, git
    ausente, etc) -- nunca inventa uma mensagem sem ver mudança real."""


def _run_git(args: list[str], repo_path: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitAssistantError(f"Não consegui rodar git: {exc}") from exc
    if result.returncode != 0:
        raise GitAssistantError(f"git falhou: {result.stderr.strip()}")
    return result.stdout


def _guess_type_and_scope(changed_files: list[str]) -> tuple[str, str | None]:
    if not changed_files:
        return "chore", None

    for needle, commit_type in _SCOPE_HINTS:
        if any(needle in f for f in changed_files):
            return commit_type, None

    top_dirs = {Path(f).parts[0] for f in changed_files if Path(f).parts}
    scope = sorted(top_dirs)[0] if len(top_dirs) == 1 else None
    # Sem sinal mais forte, "feat" é o palpite mais seguro pra mudança de
    # código de produto -- "fix" exigiria saber a intenção, que o diff
    # sozinho não prova.
    return "feat", scope


def generate_smart_commit(repo_path: str = ".") -> str:
    """Lê `git diff --staged` (cai para o diff completo se nada estiver
    staged) e devolve uma mensagem sugerida no padrão Conventional Commits.
    Só SUGERE -- não executa `git commit`."""
    staged_files_raw = _run_git(["diff", "--staged", "--name-only"], repo_path)
    changed_files = [line.strip() for line in staged_files_raw.splitlines() if line.strip()]
    scope_source = "staged"

    if not changed_files:
        unstaged_raw = _run_git(["diff", "--name-only"], repo_path)
        changed_files = [line.strip() for line in unstaged_raw.splitlines() if line.strip()]
        scope_source = "unstaged"

    if not changed_files:
        raise GitAssistantError("Nenhuma mudança encontrada (staged ou não) para sugerir commit.")

    commit_type, scope = _guess_type_and_scope(changed_files)
    scope_part = f"({scope})" if scope else ""
    summary_files = ", ".join(Path(f).name for f in changed_files[:3])
    if len(changed_files) > 3:
        summary_files += f" e mais {len(changed_files) - 3}"

    prefix = "" if scope_source == "staged" else "[ainda não staged] "
    return f"{prefix}{commit_type}{scope_part}: update {summary_files}"
