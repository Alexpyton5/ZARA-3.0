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
