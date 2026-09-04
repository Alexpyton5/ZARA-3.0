"""Router integrity proofs (ZARA-NIGHT-SHIFT 049-050 / 054).

049 found a real orphan route: the voice intent detector mapped "role a tela para
baixo" to an unregistered action. P1-B resolves it with the registered,
readback-verified browser_scroll action.
execute_action() raised ValueError, the generic except swallowed it and returned
None, so the request fell through to the LLM — which can happily answer as if the
screen had scrolled. That is exactly the false-success class this shift must kill.

050 fixes it with the smallest honest patch: a detected PC intent whose action is
not registered returns an explicit unsupported message instead of falling through.
"""
from __future__ import annotations

import asyncio

import pytest

import core.actions  # noqa: F401  (registers only fundamental actions)
from core.action_registry import execute_action, get_registry
def load_capability(name):
    return get_registry().get_spec(name) is not None


def load_fundamentals():
    import core.actions  # noqa: F401
from core.ipc_handlers import IPCHandler
from core.pc_voice_intent import PcVoiceIntentDetector


def _detector(**kw):
    kw.setdefault("pc_control_allowed", True)
    return PcVoiceIntentDetector(**kw)


def _handler():
    h = IPCHandler.__new__(IPCHandler)
    h.supercerebro_active = True
    h._last_volume_level = 40
    h._last_window_hwnd = None
    h._last_safe_folder = None
    h._last_brightness_level = None
    h._operational_context_turns = 0
    h._context_fresh = lambda _kind: False  # type: ignore[method-assign]
    h._set_operational_context = lambda *a, **k: None  # type: ignore[method-assign]
    h._clear_operational_context = lambda: None  # type: ignore[method-assign]
    return h


# ---------- 049 diagnostico ----------
def test_049_every_registered_action_name_is_unique():
    specs = get_registry()._specs
    assert len(specs) == len(set(specs))


def test_049_scroll_intent_is_detected():
    res = _detector().detect("role para baixo")
    assert res.is_pc_intent is True
    assert res.action == "browser_scroll"


def test_049_scroll_action_is_registered():
    assert load_capability("browser_scroll") is True
    assert "browser_scroll" in get_registry()._specs


def test_049_executing_an_unknown_action_still_raises():
    with pytest.raises(ValueError):
        asyncio.run(execute_action("scroll", direction="down"))


# ---------- 050 correcao ----------
#
# ZARA-TESTE-INSTAVEL-001 (2026-08-14)
# Estes dois testes tocavam o NAVEGADOR DE VERDADE. Com o Chrome aberto numa
# pagina, browser_scroll rolava mesmo e a resposta virava "Pagina rolada e
# confirmada" — sucesso legitimo, mas o teste esperava recusa. Rodando 3 vezes
# seguidas: passou 2, falhou 1.
#
# Um teste que depende do que esta aberto na tela do Alex nao prova nada: ele
# mente nos dois sentidos. Agora o executor e controlado aqui dentro, e cada
# teste prova UMA regra:
#
#   - executor falhou   -> a resposta DIZ que falhou, e nunca e None
#   - executor foi bem  -> a resposta e a do executor, sem inventar
#
# O que a versao antiga protegia continua protegido: intent detectado jamais
# cai no LLM, e falha jamais vira falso sucesso.
def _resultado(*, success: bool, output: str = "", error: str = ""):
    return type("Resultado", (), {
        "success": success, "output": output, "error": error, "data": {},
    })()


@pytest.mark.asyncio
async def test_050_falha_do_executor_vira_recusa_honesta(monkeypatch):
    """Se o scroll falhar de verdade, ela precisa dizer que falhou."""
    async def falhou(*_a, **_k):
        return _resultado(success=False, error="navegador nao respondeu")

    monkeypatch.setattr("core.action_registry.execute_action", falhou)

    reply = await _handler()._try_pc_intent("role para baixo")

    assert reply is not None, "nao pode cair no LLM"
    assert "não consegui" in reply.lower()


@pytest.mark.asyncio
async def test_050_falha_do_executor_nunca_vira_sucesso(monkeypatch):
    async def falhou(*_a, **_k):
        return _resultado(success=False, error="navegador nao respondeu")

    monkeypatch.setattr("core.action_registry.execute_action", falhou)

    reply = await _handler()._try_pc_intent("role para cima")

    lowered = reply.lower()
    for mentira in ("pronto", "feito", "rolei", "concluído", "concluido", "confirmada"):
        assert mentira not in lowered


@pytest.mark.asyncio
async def test_050_sucesso_do_executor_e_repassado_sem_invencao(monkeypatch):
    """A outra metade: quando dá certo, a fala vem do executor, não do modelo."""
    async def deu_certo(*_a, **_k):
        return _resultado(success=True, output="Página rolada e confirmada.")

    monkeypatch.setattr("core.action_registry.execute_action", deu_certo)

    reply = await _handler()._try_pc_intent("role para baixo")

    assert reply is not None
    assert "rolada e confirmada" in reply.lower()


@pytest.mark.asyncio
async def test_050_nao_depende_do_navegador_da_maquina(monkeypatch):
    """Trava a regressão: o teste não pode voltar a tocar o Chrome real.

    Se alguém remover o controle do executor, esta chamada explode em vez de
    silenciosamente virar instável de novo.
    """
    chamadas = []

    async def registrando(nome, **kw):
        chamadas.append(nome)
        return _resultado(success=False, error="controlado pelo teste")

    monkeypatch.setattr("core.action_registry.execute_action", registrando)

    await _handler()._try_pc_intent("role para baixo")

    assert chamadas == ["browser_scroll"], f"rota inesperada: {chamadas}"


@pytest.mark.asyncio
async def test_050_non_pc_message_still_falls_through_to_llm():
    assert await _handler()._try_pc_intent("me explica o que é um relay") is None


@pytest.mark.asyncio
async def test_050_open_ended_browser_intent_still_asks_for_supercerebro():
    h = _handler()
    h.supercerebro_active = False
    reply = await h._try_pc_intent("abra o site da openai")
    assert reply is not None
    assert "supercérebro" in reply.lower()


@pytest.mark.parametrize(
    "text,expected_action",
    [
        ("abra a calculadora", "os_app"),
        ("volume em 30", "os_volume"),
        ("abra downloads", "os_open"),
        ("mute", "audio_mute"),
        ("minimize a janela", "window_minimize"),
        ("ative a luz noturna", "os_night_light_on"),
    ],
)
def test_050_core_routes_point_to_registered_actions(text, expected_action):
    res = _detector().detect(text)
    assert res.action == expected_action
    assert load_capability(expected_action) is True
    assert expected_action in get_registry()._specs, f"rota orfa: {expected_action}"


def test_050_blocked_drive_format_is_not_an_executable_route():
    res = _detector().detect("formatar C")

    assert res.is_pc_intent is True
    assert res.blocked is True
    assert res.action == ""


def test_050_mcp_actions_are_not_mapped_or_lazy_loadable():
    """MCP morto não pode importar os_ops nem expor capabilities."""
    from core.action_mapping import _ACTION_TO_MODULE

    assert not {name for name in _ACTION_TO_MODULE if name.startswith("mcp_")}

    before = set(get_registry()._specs)
    assert load_capability("mcp_connect") is False
    assert set(get_registry()._specs) == before


def test_050_all_intent_actions_except_known_gap_are_registered():
    """Rede de seguranca: nenhuma rota orfa NOVA pode ser introduzida.

    Com lazy-loading, carrega capabilities sob demanda via API publica antes de checar.
    """
    import inspect
    import re

    # Garante fundamentais carregados
    load_fundamentals()

    src = inspect.getsource(PcVoiceIntentDetector)
    referenced = set(re.findall(r'"([a-z_]+)",\s*(?:"[^"]*"|None)\)', src))
    referenced |= set(re.findall(r'action="([a-z_]+)"', src))

    # ZARA-TEST-DEBT-001: a regex acima e um heuristico sobre texto-fonte,
    # nao um parser real de tupla de rota -- ela tambem casa chamadas
    # `dict.get("chave", default)` que nada tem a ver com roteamento.
    # Confirmado lendo core/pc_voice_intent.py: "content" vem de
    # `result.get("choices", [{}])[0].get("message", {}).get("content", "")`
    # (parse de resposta de LLM) e "param" vem de `parsed.get("param", "")`
    # (mesmo parser). Nenhum dos dois e nome de action de verdade.
    referenced -= {"content", "param"}

    # Carrega sob demanda cada action referenciada
    for action_name in referenced:
        load_capability(action_name)

    registered = set(get_registry()._specs)
    missing = referenced - registered
    print(f"referenced-registered = {sorted(missing)}")
    assert not missing, f"rotas sem action registrada: {sorted(missing)}"
