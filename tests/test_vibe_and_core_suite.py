"""Testes offline (sem rede, sem tocar o cofre real do Obsidian) para as
peças isoladas autorizadas em 2026-08-28: core/vibe_guardrails.py,
core/obsidian_memory.py + tools/git_assistant.py, tools/syntax_watcher.py,
tools/mock_data_gen.py, tools/boilerplate_gen.py, tools/snippet_finder.py.
Nenhum destes módulos é chamado pelo pipeline de produção da Zara -- provam
a peça em si (nível SOURCE/TEST), não integração.

core/smart_router.py foi deliberadamente NÃO construído nesta rodada
(duplicação com core/multi_intent_parser.py + core/intent_classifier.py já
existentes) -- ver backlog do projeto.

Os testes de core/obsidian_memory.py usam um cofre MOCKADO em `tmp_path`
(fixture padrão do pytest, isolada e limpa automaticamente) em vez de um
caminho fixo em `temp/` -- mesmo padrão já usado no resto deste arquivo, e
garante que nenhum teste toca o cofre real do Alex.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from core.obsidian_memory import ObsidianMemoryManager, get_system_context
from core.vibe_guardrails import check_command_safety, translate_crash_log
from tools.boilerplate_gen import BoilerplateExistsError, create_python_boilerplate
from tools.git_assistant import GitAssistantError, generate_smart_commit
from tools.mock_data_gen import generate_mock_json
from tools.snippet_finder import get_code_snippet
from tools.syntax_watcher import check_python_syntax

# --- core/vibe_guardrails.py ---------------------------------------------

@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /home/alex/projeto",
        "del /f /s /q C:\\temp",
        "git reset --hard origin/main",
        "git push --force origin main",
        "DROP TABLE usuarios;",
        "export KEY=sk-abcdefghijklmnopqrstuvwx1234",
    ],
)
def test_check_command_safety_flags_dangerous_commands(command):
    result = check_command_safety(command)

    assert result["safe"] is False
    assert result["risk_level"] == "high"
    assert result["reasons"]


@pytest.mark.parametrize("command", ["git status", "ls -la", "npm run build", "git commit -m 'fix: x'"])
def test_check_command_safety_allows_normal_commands(command):
    result = check_command_safety(command)

    assert result == {"safe": True, "risk_level": "low", "reasons": []}


def test_translate_crash_log_module_not_found():
    trace = "Traceback (most recent call last):\n  File x\nModuleNotFoundError: No module named 'yt_dlp'"
    message = translate_crash_log(trace)

    assert "yt_dlp" in message
    assert "instalado" in message


def test_translate_crash_log_unknown_format_is_honest():
    message = translate_crash_log("algo totalmente diferente de um traceback")

    assert "Não reconheci" in message


def test_translate_crash_log_empty_input():
    assert translate_crash_log("") == "Nenhum log de erro foi informado."


# --- tools/syntax_watcher.py ----------------------------------------------

def test_check_python_syntax_valid_file(tmp_path):
    file_path = tmp_path / "ok.py"
    file_path.write_text("def soma(a, b):\n    return a + b\n", encoding="utf-8")

    result = check_python_syntax(str(file_path))

    assert result["ok"] is True


def test_check_python_syntax_reports_line_of_error(tmp_path):
    file_path = tmp_path / "quebrado.py"
    file_path.write_text("def soma(a, b)\n    return a + b\n", encoding="utf-8")

    result = check_python_syntax(str(file_path))

    assert result["ok"] is False
    assert result["line"] == 1


def test_check_python_syntax_missing_file():
    result = check_python_syntax("nao_existe_de_verdade.py")

    assert result["ok"] is False
    assert "não encontrado" in result["message"]


# --- tools/mock_data_gen.py -----------------------------------------------

@pytest.mark.parametrize("data_type,expected_keys", [
    ("users", {"id", "name", "email", "age"}),
    ("products", {"id", "name", "price", "stock"}),
    ("logs", {"id", "level", "message", "timestamp"}),
])
def test_generate_mock_json_shapes(data_type, expected_keys):
    result = generate_mock_json(data_type, count=5)

    assert len(result) == 5
    assert set(result[0].keys()) == expected_keys
    assert len({item["id"] for item in result}) == 5  # ids não colidem


def test_generate_mock_json_unsupported_type_raises():
    with pytest.raises(ValueError, match="não suportado"):
        generate_mock_json("naves_espaciais")


def test_generate_mock_json_zero_count_raises():
    with pytest.raises(ValueError):
        generate_mock_json("users", count=0)


# --- tools/boilerplate_gen.py ---------------------------------------------

def test_create_python_boilerplate_creates_expected_structure(tmp_path):
    project_path = Path(create_python_boilerplate("meu_projeto", str(tmp_path)))

    assert project_path.is_dir()
    assert (project_path / "src").is_dir()
    assert (project_path / "tests").is_dir()
    assert (project_path / "requirements.txt").exists()
    assert (project_path / ".gitignore").exists()


def test_create_python_boilerplate_refuses_to_overwrite_existing(tmp_path):
    create_python_boilerplate("duplicado", str(tmp_path))

    with pytest.raises(BoilerplateExistsError):
        create_python_boilerplate("duplicado", str(tmp_path))


def test_create_python_boilerplate_empty_name_raises(tmp_path):
    with pytest.raises(ValueError):
        create_python_boilerplate("   ", str(tmp_path))


# --- tools/snippet_finder.py ----------------------------------------------

def test_get_code_snippet_known_topic():
    snippet = get_code_snippet("httpx_async")

    assert "async def fetch" in snippet
    assert "httpx" in snippet


def test_get_code_snippet_accepts_natural_language_alias():
    snippet = get_code_snippet("requisição assíncrona")

    assert "httpx" in snippet


def test_get_code_snippet_unknown_topic_lists_alternatives():
    result = get_code_snippet("blockchain quântico")

    assert "Não tenho um snippet" in result
    assert "httpx_async" in result


# --- tools/git_assistant.py ------------------------------------------------

def test_generate_smart_commit_uses_staged_diff(tmp_path):
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_x(): pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "tests/test_x.py"], cwd=tmp_path, check=True, capture_output=True)

    message = generate_smart_commit(str(tmp_path))

    assert message.startswith("test")
    assert "test_x.py" in message


def test_generate_smart_commit_no_changes_raises(tmp_path):
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)

    with pytest.raises(GitAssistantError, match="Nenhuma mudança"):
        generate_smart_commit(str(tmp_path))


def test_generate_smart_commit_not_a_repo_raises(tmp_path):
    with pytest.raises(GitAssistantError):
        generate_smart_commit(str(tmp_path))


def test_generate_smart_commit_never_calls_git_commit(tmp_path, monkeypatch):
    """Garantia dura: esta função NUNCA deve invocar 'git commit'."""
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=tmp_path, check=True, capture_output=True)

    import tools.git_assistant as module

    real_run = module.subprocess.run

    def guarded_run(args, **kwargs):
        assert args[:2] != ["git", "commit"], "generate_smart_commit não deve executar git commit"
        return real_run(args, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", guarded_run)
    generate_smart_commit(str(tmp_path))


# --- core/obsidian_memory.py ------------------------------------------------

@pytest.fixture
def mock_vault(tmp_path):
    vault = tmp_path / "obsidian_mock"
    vault.mkdir()
    (vault / "Receitas.md").write_text(
        "---\ntitle: Receitas\n---\n\nBolo de chocolate: 3 ovos, farinha, cacau.",
        encoding="utf-8",
    )
    sub = vault / "Trabalho"
    sub.mkdir()
    (sub / "Projeto-Zara.md").write_text(
        "# Projeto Zara\n\nDecisão: priorizar voz Kore antes de features novas.",
        encoding="utf-8",
    )
    return vault


def test_obsidian_manager_unavailable_without_vault(tmp_path):
    manager = ObsidianMemoryManager(vault_path=tmp_path / "nao-existe")

    assert manager.available is False
    assert manager.search_notes("qualquer coisa") == []
    assert manager.save_memory("topico", "conteúdo") is None


def test_obsidian_search_notes_finds_match_with_snippet(mock_vault):
    manager = ObsidianMemoryManager(vault_path=mock_vault)

    results = manager.search_notes("bolo de chocolate")

    assert len(results) == 1
    assert results[0]["title"] == "Receitas"
    assert "bolo de chocolate" in results[0]["snippet"].lower()


def test_obsidian_search_notes_is_recursive_and_case_insensitive(mock_vault):
    manager = ObsidianMemoryManager(vault_path=mock_vault)

    results = manager.search_notes("VOZ KORE")

    assert len(results) == 1
    assert results[0]["path"] == str(Path("Trabalho") / "Projeto-Zara.md")


def test_obsidian_search_notes_no_match_returns_empty(mock_vault):
    manager = ObsidianMemoryManager(vault_path=mock_vault)

    assert manager.search_notes("assunto que não existe em lugar nenhum") == []


def test_obsidian_save_memory_creates_note_in_zara_subfolder(mock_vault):
    manager = ObsidianMemoryManager(vault_path=mock_vault)

    saved_path = manager.save_memory("Preferência de Volume", "Alex prefere passos maiores.", category="Aprendizado")

    assert saved_path is not None
    note = Path(saved_path)
    assert note.parent.name == "Zara-Memoria"
    assert note.parent.parent == mock_vault
    text = note.read_text(encoding="utf-8")
    assert "Alex prefere passos maiores." in text
    assert "Aprendizado" in text


def test_obsidian_save_memory_appends_on_second_call(mock_vault):
    manager = ObsidianMemoryManager(vault_path=mock_vault)

    first_path = manager.save_memory("Mesmo Tópico", "primeira entrada")
    second_path = manager.save_memory("Mesmo Tópico", "segunda entrada")

    assert first_path == second_path
    text = Path(second_path).read_text(encoding="utf-8")
    assert "primeira entrada" in text
    assert "segunda entrada" in text


def test_obsidian_manager_prefers_explicit_path_over_env(mock_vault, monkeypatch):
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(mock_vault / "nao-deveria-usar-isto"))

    manager = ObsidianMemoryManager(vault_path=mock_vault)

    assert manager.vault_path == mock_vault
    assert manager.available is True


def test_obsidian_manager_falls_back_to_env_var(mock_vault, monkeypatch):
    monkeypatch.setenv("OBSIDIAN_VAULT_PATH", str(mock_vault))

    manager = ObsidianMemoryManager()

    assert manager.vault_path == mock_vault
    assert manager.available is True


def test_get_system_context_combines_notes_and_files(mock_vault, tmp_path):
    scan_dir = tmp_path / "Desktop"
    scan_dir.mkdir()
    (scan_dir / "Projeto Zara Notas.txt").write_text("nota qualquer", encoding="utf-8")
    (scan_dir / "outro-arquivo.txt").write_text("irrelevante", encoding="utf-8")

    result = get_system_context("projeto zara", vault_path=mock_vault, scan_dirs=(scan_dir,))

    assert len(result["notes"]) == 1
    assert len(result["files"]) == 1
    assert "Projeto Zara Notas.txt" in result["files"][0]


def test_get_system_context_empty_query_returns_no_files(mock_vault, tmp_path):
    scan_dir = tmp_path / "Desktop"
    scan_dir.mkdir()

    result = get_system_context("", vault_path=mock_vault, scan_dirs=(scan_dir,))

    assert result == {"notes": [], "files": []}
