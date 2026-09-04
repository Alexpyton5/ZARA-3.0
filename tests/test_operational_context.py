from unittest.mock import AsyncMock

import pytest

import core.actions  # noqa: F401 - register closed actions for isolated execution
import core.ipc_handlers as ipc_handlers
from core.ipc_handlers import IPCHandler


@pytest.mark.asyncio
async def test_missing_window_context_asks_for_explicit_target(monkeypatch):
    execute = AsyncMock()
    handler = IPCHandler(AsyncMock())
    monkeypatch.setattr("core.action_registry.execute_action", execute)
    assert "janela recente e inequívoca" in await handler._try_pc_intent("agora minimize ele")
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_folder_context_reuses_only_canonical_id(monkeypatch):
    calls = []
    async def execute(action, **params):
        calls.append((action, params))
        return type("Result", (), {"success": True, "output": "Solicitação enviada.", "data": {}})()
    handler = IPCHandler(AsyncMock())
    handler._last_safe_folder = "downloads"
    handler._touch_operational_context()
    monkeypatch.setattr("core.action_registry.execute_action", execute)
    assert await handler._try_pc_intent("mostre ela de novo") == "Solicitação enviada."
    assert calls == [("os_open", {"folder": "downloads"})]


@pytest.mark.asyncio
async def test_expired_context_is_not_reused(monkeypatch):
    handler = IPCHandler(AsyncMock())
    handler._last_safe_folder = "downloads"
    handler._touch_operational_context()
    monkeypatch.setattr(ipc_handlers.time, "monotonic", lambda: handler._operational_context_updated_at + 121)
    assert await handler._try_pc_intent("mostre ela de novo") == "Qual pasta devo mostrar?"


@pytest.mark.asyncio
async def test_relative_volume_context_clamps(monkeypatch):
    calls = []
    async def execute(action, **params):
        calls.append(params["level"])
        return type("Result", (), {"success": True, "output": "", "data": {}})()
    handler = IPCHandler(AsyncMock())
    handler._last_volume_level = 95
    handler._touch_operational_context()
    monkeypatch.setattr("core.action_registry.execute_action", execute)
    monkeypatch.setattr(ipc_handlers, "_read_windows_volume", lambda: 100)
    assert await handler._try_pc_intent("um pouco mais alto") == "Volume definido para 100%."
    assert calls == [100]


@pytest.mark.asyncio
async def test_contextual_window_minimize_then_restore_reuses_one_hwnd(monkeypatch):
    calls = []
    states = iter(("minimized", "restored"))

    async def execute(action, **params):
        calls.append((action, params))
        return type("Result", (), {
            "success": True,
            "output": "Estado verificado.",
            "data": {"hwnd": 4321, "pid": 987, "after": next(states)},
        })()

    handler = IPCHandler(AsyncMock())
    handler._set_operational_context(
        "app", canonical_target="notepad", pid=987, hwnd=4321,
        verified_value="opened", created_by_zara=True,
    )
    monkeypatch.setattr("core.action_registry.execute_action", execute)

    assert await handler._try_pc_intent("minimize ele") == "Estado verificado."
    assert await handler._try_pc_intent("restaure ele") == "Estado verificado."
    assert calls == [
        ("window_minimize", {"hwnd": 4321}),
        ("window_restore", {"hwnd": 4321}),
    ]


@pytest.mark.asyncio
async def test_this_window_resolves_only_recent_unambiguous_hwnd(monkeypatch):
    calls = []

    async def execute(action, **params):
        calls.append((action, params))
        return type("Result", (), {
            "success": True,
            "output": "Janela maximizada e verificada.",
            "data": {"hwnd": 2468, "pid": 10, "after": "maximized"},
        })()

    handler = IPCHandler(AsyncMock())
    handler._set_operational_context("window", canonical_target="relatorio.pdf", hwnd=2468)
    monkeypatch.setattr("core.action_registry.execute_action", execute)

    assert await handler._try_pc_intent("Zara, maximize isso") == "Janela maximizada e verificada."
    assert calls == [("window_maximize", {"hwnd": 2468})]


@pytest.mark.asyncio
async def test_this_window_without_context_asks_instead_of_guessing(monkeypatch):
    execute = AsyncMock()
    handler = IPCHandler(AsyncMock())
    monkeypatch.setattr("core.action_registry.execute_action", execute)

    assert "janela recente e inequívoca" in await handler._try_pc_intent("maximize isso")
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_dead_contextual_window_is_invalidated(monkeypatch):
    async def execute(action, **params):
        return type("Result", (), {
            "success": False,
            "error": "A janela contextual não existe mais ou deixou de ser segura.",
            "data": {},
        })()

    handler = IPCHandler(AsyncMock())
    handler._set_operational_context("app", canonical_target="notepad", pid=7, hwnd=8)
    monkeypatch.setattr("core.action_registry.execute_action", execute)

    reply = await handler._try_pc_intent("minimize ele")
    assert "não existe mais" in reply
    assert handler._operational_context is None


@pytest.mark.asyncio
async def test_domain_switch_drops_previous_folder_context(monkeypatch):
    async def execute(action, **params):
        return type("Result", (), {
            "success": True,
            "output": "Aplicativo aberto.",
            "data": {"hwnd": 9, "window_pid": 10, "created_pids": [10]},
        })()

    handler = IPCHandler(AsyncMock())
    handler._set_operational_context("folder", canonical_target="downloads")
    monkeypatch.setattr("core.action_registry.execute_action", execute)

    await handler._try_pc_intent("abra o bloco de notas")
    assert handler._operational_context["action_type"] == "app"
    assert await handler._try_pc_intent("abra essa pasta novamente") == "Qual pasta devo mostrar?"


def test_context_record_contains_only_canonical_metadata():
    handler = IPCHandler(AsyncMock())
    handler._set_operational_context(
        "app", canonical_target="notepad", pid=10, hwnd=20,
        verified_value="opened", created_by_zara=True,
    )
    assert set(handler._operational_context) == {
        "action_type", "canonical_target", "pid", "hwnd", "verified_value",
        "timestamp", "created_by_zara",
    }
    assert handler._operational_context["canonical_target"] == "notepad"


def test_unsafe_contextual_close_is_blocked_without_action():
    from core.pc_voice_intent import PcVoiceIntentDetector

    result = PcVoiceIntentDetector(window_context_available=True).detect("feche ele")
    assert result.is_pc_intent is True
    assert result.blocked is True
    assert result.action == ""


@pytest.mark.asyncio
async def test_ambiguous_context_is_not_reused(monkeypatch):
    execute = AsyncMock()
    handler = IPCHandler(AsyncMock())
    handler._last_window_hwnd = 123
    handler._last_safe_folder = "downloads"
    handler._touch_operational_context()
    monkeypatch.setattr("core.action_registry.execute_action", execute)

    assert "janela recente e inequívoca" in await handler._try_pc_intent("minimize ele")
    execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_allowlisted_folder_context_is_never_reused(monkeypatch):
    execute = AsyncMock()
    handler = IPCHandler(AsyncMock())
    handler._set_operational_context("folder", canonical_target=r"C:\\Users\\secret")
    monkeypatch.setattr("core.action_registry.execute_action", execute)

    assert await handler._try_pc_intent("abra essa pasta novamente") == "Qual pasta devo mostrar?"
    execute.assert_not_awaited()
