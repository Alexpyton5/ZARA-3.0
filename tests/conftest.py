"""Isolamento de dados reais durante os testes.

Descoberto em 15/08, olhando o arquivo de medição de latência da máquina do
Alex: havia 40 registros de descarte, e parte deles eram **frases de teste** —
"e por isso que o ceu e azul", "abra o chrome agora para continuar". A suíte
estava escrevendo no arquivo de dados dele.

Isso é pior do que sujeira: aquele arquivo existe para responder "onde o tempo da
ZARA está indo" e "o que ela descartou em silêncio". Misturar frase de teste com
fala real do Alex envenena exatamente a evidência que ele usa para decidir — e
este projeto inteiro é construído sobre a evidência ser confiável.

A instrumentação nova (`core/cronometro.py`) é chamada de dentro do caminho de
voz, então qualquer teste que exercite wake gate ou eco escreve lá sem querer.
Isolar aqui, uma vez, protege a suíte inteira — inclusive os testes que ainda
não existem, que é onde o mesmo erro voltaria.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# INCIDENTE_2026-09-02: um teste em test_os_ops_truth_contracts.py mockava
# `os_ops._read_windows_volume`/`_set_windows_volume`, mas o código de
# produção ainda chamava pycaw direto (sem esses seams existirem) — o
# monkeypatch não tinha efeito nenhum e a suíte mexeu no volume real da
# máquina do Alex, de madrugada, repetidas vezes, rodando em paralelo.
#
# Isso é uma classe de bug: qualquer teste pode achar que está mockando um
# seam que a implementação real não usa. A defesa de um arquivo por vez não
# escala. Esta rede de segurança bloqueia por padrão, no nível mais baixo
# possível de cada domínio de hardware conhecido, e só libera com
# ALLOW_LIVE_TESTS=1 — sem essa flag, qualquer chamada real vira erro claro
# em vez de mexer no PC do Alex.
# ---------------------------------------------------------------------------

os.environ.setdefault("ZARA_TEST_MODE", "1")

_LIVE_ALLOWED = os.environ.get("ALLOW_LIVE_TESTS") == "1"

# (module_path, attr_name, fake_return_value) — cada seam vira um fake que
# devolve algo neutro em vez de tocar hardware. Testes que precisam de um
# comportamento específico continuam livres para sobrescrever com o próprio
# `monkeypatch.setattr(...)` dentro do teste: como isso roda DEPOIS desta
# fixture autouse, o valor do teste sempre vence.
_HARDWARE_WRITE_SEAMS = [
    ("core.actions.os_ops", "_set_windows_volume", lambda level: False),
    ("core.actions.os_ops", "_set_windows_mute", lambda muted: False),
    ("core.actions.os_ops", "_set_windows_brightness", lambda level: False),
]


def _blocked_live_call(*_args, **_kwargs):
    raise RuntimeError(
        "Chamada de hardware real bloqueada em modo de teste (ZARA_TEST_MODE=1). "
        "Se este teste precisa tocar hardware de verdade, marque @pytest.mark.live "
        "e rode a suíte com ALLOW_LIVE_TESTS=1 — nunca em CI/background."
    )


@pytest.fixture(autouse=True)
def _bloquear_hardware_real_por_padrao(request, monkeypatch):
    """Rede de segurança: nenhum teste muda volume/brilho/mudo reais sem opt-in explícito.

    Não substitui mocks específicos de cada teste — só garante que, se um
    teste ESQUECER de mockar, a falha é um RuntimeError claro em vez de uma
    mudança real e silenciosa no PC do Alex.
    """
    if _LIVE_ALLOWED or request.node.get_closest_marker("live"):
        yield
        return

    for module_path, attr_name, fake in _HARDWARE_WRITE_SEAMS:
        try:
            module = __import__(module_path, fromlist=[attr_name])
        except ImportError:
            continue
        monkeypatch.setattr(module, attr_name, fake, raising=False)

    yield


def _lock_path():
    from pathlib import Path

    lock_dir = Path(__file__).resolve().parent.parent / ".zara-tests"
    lock_dir.mkdir(parents=True, exist_ok=True)
    return lock_dir / "test-run.lock"


def pytest_sessionstart(session):
    """TEST RUN LOCK: recusa iniciar uma segunda suíte completa concorrente.

    INCIDENTE_2026-09-02: múltiplos agentes em paralelo dispararam
    "pytest -q" (suíte inteira) ao mesmo tempo, multiplicando qualquer efeito
    colateral (inclusive o de hardware real). Isso impede a próxima vez.
    """
    import json
    import time

    # A golden-path smoke is intentionally a nested pytest process launched
    # by one test. It has its own process boundary and must not be rejected by
    # the outer session's lock; the caller opts in explicitly.
    if os.environ.get("ZARA_TEST_ALLOW_NESTED") == "1":
        return
    lock_file = _lock_path()
    if lock_file.exists():
        try:
            info = json.loads(lock_file.read_text(encoding="utf-8"))
        except Exception:
            info = {}
        pid = info.get("pid")
        alive = False
        if pid:
            try:
                import psutil

                alive = psutil.pid_exists(int(pid))
            except Exception:
                alive = True  # não sabemos — trata como vivo, falha seguro
        if alive:
            raise pytest.UsageError(
                f"Já existe uma execução de testes ativa (PID {pid}, iniciada "
                f"{info.get('start_time', '?')}). Lock em {lock_file}. "
                "Se tiver certeza que ela morreu, apague o arquivo de lock."
            )
        # Lock órfão (processo morreu sem limpar) — segue e sobrescreve.

    lock_file.write_text(
        json.dumps(
            {
                "pid": os.getpid(),
                "start_time": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "trigger": os.environ.get("ZARA_TEST_TRIGGER", "manual"),
            }
        ),
        encoding="utf-8",
    )


def pytest_sessionfinish(session, exitstatus):
    if os.environ.get("ZARA_TEST_ALLOW_NESTED") == "1":
        return
    lock_file = _lock_path()
    try:
        lock_file.unlink(missing_ok=True)
    except Exception:
        pass


def pytest_collection_modifyitems(config, items):
    """Pula testes @pytest.mark.live por padrão; só roda com ALLOW_LIVE_TESTS=1."""
    if _LIVE_ALLOWED:
        return
    skip_live = pytest.mark.skip(reason="LIVE test bloqueado por padrão — rode com ALLOW_LIVE_TESTS=1")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


@pytest.fixture(autouse=True)
def _nunca_escrever_nos_dados_do_alex(monkeypatch, tmp_path):
    """Manda toda medição/estado real para uma pasta temporária do próprio teste.

    INCIDENTE_2026-09-02 (recorrente): `config/telegram_lido.json` foi
    sobrescrito por pelo menos 3 rodadas de suíte completa nesta mesma
    madrugada porque `tests/test_telegram_ponte.py` só isola
    `PonteTelegram._arquivo_marcador` em UM dos seus testes — os outros usam
    o caminho real via `config_dir()`. Mesma classe de erro do cronômetro
    (ver comentário do módulo): isolar aqui, uma vez, protege a suíte
    inteira, inclusive testes futuros que cometeriam o mesmo esquecimento.
    """
    from core import cronometro
    from core.telegram_ponte import PonteTelegram

    monkeypatch.setattr(
        cronometro, "_arquivo", lambda: tmp_path / "latencia.jsonl", raising=False
    )
    monkeypatch.setattr(
        PonteTelegram, "_arquivo_marcador",
        staticmethod(lambda: tmp_path / "telegram_lido.json"),
        raising=False,
    )


# ---------------------------------------------------------------------------
# INCIDENTE_2026-09-10 (NIGHT-03B): uma suíte de não-regressão construiu um
# `LabV1Service()` real. O serviço resolve o caminho do banco sozinho, em
# `_get_runtime` (core/lab_v1/service.py:716-728): `LabStore()` sem argumento
# cai em `data_dir()/lab/zara_lab_v1.db`, e o boot ainda escreve a linha
# `@last_boot` na tabela `lab_boot_reconciliation`. Resultado: o banco REAL do
# Lab do Alex ganhou uma tabela e uma linha durante `pytest -q`.
#
# Mesma classe dos incidentes de volume/cronômetro/telegram: a defesa arquivo a
# arquivo não escala, porque o teste que esquece é sempre o próximo. O caminho
# real é resolvido por `core/paths.user_data_dir()`, que já respeita
# `ZARA3_HOME` — então a defesa certa é redirecionar a árvore INTEIRA de dados
# por padrão, uma vez, para todo teste.
#
# Duas camadas:
#   1. `ZARA3_HOME` → tmp_path por teste (isolamento por padrão, automático).
#   2. guarda em `sqlite3.connect`: qualquer conexão a um .db dentro da árvore
#      real vira erro claro — pega até caminho hardcoded que ignore ZARA3_HOME.
#
# Opt-in explícito: `@pytest.mark.live` ou `@pytest.mark.real_env`.
# ---------------------------------------------------------------------------


def _real_home() -> Path:
    """Árvore de dados real do Alex, resolvida ANTES de qualquer override de teste."""
    base = os.environ.get("ZARA3_HOME")
    if base:
        return Path(base).resolve()
    root = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.local/share")
    return (Path(root) / "ZARA3").resolve()


_REAL_ZARA3_HOME = _real_home()
_REAL_SQLITE_CONNECT = sqlite3.connect


def _dentro_da_arvore_real(database) -> bool:
    if isinstance(database, (int, bytes)):
        return False
    text = str(database)
    if text == ":memory:" or text.startswith("file::memory:"):
        return False
    if text.startswith("file:"):
        text = text[5:].split("?", 1)[0]
    try:
        candidate = Path(text).expanduser().resolve()
    except (OSError, ValueError):
        return False
    return candidate == _REAL_ZARA3_HOME or _REAL_ZARA3_HOME in candidate.parents


@pytest.fixture(autouse=True)
def _isolar_a_arvore_de_dados_real(request, monkeypatch, tmp_path_factory):
    """Nenhum teste escreve nos dados reais do Alex sem pedir explicitamente.

    Marque `@pytest.mark.live` ou `@pytest.mark.real_env` no teste que
    realmente precisa do ambiente real — ele fica de fora das duas camadas, e
    `live` já é pulado por padrão em `pytest_collection_modifyitems`.

    A home isolada NÃO fica dentro de `tmp_path`: testes que listam o próprio
    `tmp_path` (ex.: `test_files_list_skips_sensitive_children...`) passariam a
    enxergar uma pasta que o teste não criou.
    """
    if request.node.get_closest_marker("live") or request.node.get_closest_marker("real_env"):
        yield
        return

    home = tmp_path_factory.mktemp("zara3-home")
    monkeypatch.setenv("ZARA3_HOME", str(home))

    def guarded_connect(database, *args, **kwargs):
        if _dentro_da_arvore_real(database):
            raise RuntimeError(
                f"Teste tentou abrir um banco DENTRO dos dados reais do Alex: {database}\n"
                "ZARA3_HOME já está redirecionado para uma pasta temporária deste teste, "
                "então este caminho veio de um valor fixo/capturado antes do redirecionamento. "
                "Se o teste precisa mesmo do ambiente real, marque @pytest.mark.real_env."
            )
        return _REAL_SQLITE_CONNECT(database, *args, **kwargs)

    monkeypatch.setattr(sqlite3, "connect", guarded_connect)
    yield


@pytest.fixture
def modelos_de_voz_reais():
    """Empresta os modelos reais (Vosk/Kokoro) para dentro da home isolada.

    `models/` é asset somente-leitura, não dado do Alex: um teste de pipeline de
    voz precisa do modelo de verdade, mas continua sem poder escrever em
    `data/`, `memory/`, `logs/` ou `config/` reais. Devolve o caminho do
    `models/` visível para o teste, ou pula o teste se a máquina não tiver os
    modelos instalados.
    """
    real = _REAL_ZARA3_HOME / "models"
    if not real.is_dir():
        pytest.skip(f"Modelos de voz reais não encontrados em {real}")

    home = Path(os.environ["ZARA3_HOME"])
    link = home / "models"
    if link.exists():
        return link
    try:
        os.symlink(real, link, target_is_directory=True)
    except OSError:
        # Sem Modo Desenvolvedor/admin o symlink falha; junção NTFS não exige.
        import subprocess

        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(real)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            pytest.skip(f"Não consegui ligar os modelos reais: {result.stderr.strip()}")
    return link
