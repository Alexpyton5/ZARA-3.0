from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, Mock

import pytest

from core.action_registry import ActionResult, get_registry
from core.actions import media_apps
import core.actions  # noqa: F401 -- garante que as actions estao registradas
from core.action_registry import get_registry


def load_capability(name):
    return get_registry().get_spec(name) is not None
from core.ipc_handlers import IPCHandler
from core.pc_voice_intent import PcVoiceIntentDetector


def test_youtube_open_uses_fixed_home_route(monkeypatch):
    # AUDITORIA_2026-08-27 (Alex, ao vivo): youtube_open e LOCAL_PC_CONTROL de
    # proposito. Antes este teste simulava browser_open_url via
    # registry._actions, o que so funcionava porque youtube_open reentrava no
    # gate de browser_open_url (o bug que bloqueava "abra o youtube" sem
    # motivo). Agora simula a funcao crua que youtube_open realmente chama.
    open_url = Mock(return_value=ActionResult(success=True, output="sent", data={"dispatch": "DISPATCH_PROVEN"}))
    monkeypatch.setattr(media_apps, "_send_url_to_default_browser", open_url)
    registry = get_registry()
    assert load_capability("browser_open_url")

    result = registry.execute("youtube_open")

    assert result.success is True
    assert result.output == "YouTube enviado ao navegador padrão."
    assert result.data["service"] == "youtube"
    assert result.data["route"] == "home"
    open_url.assert_called_once_with("https://www.youtube.com/")


@pytest.mark.parametrize(
    ("action_name", "query", "expected"),
    [
        ("youtube_search", "música brasileira", "youtube.com/results?search_query=m%C3%BAsica+brasileira"),
        ("spotify_search", "jazz focus", "open.spotify.com/search/jazz%20focus"),
    ],
)
def test_media_search_uses_fixed_service_host(monkeypatch, action_name, query, expected):
    opened = []

    def open_url(url):
        opened.append(url)
        return ActionResult(success=True, data={"dispatch": "DISPATCH_PROVEN"})

    monkeypatch.setattr(media_apps, "_send_url_to_default_browser", open_url)
    registry = get_registry()
    assert load_capability("browser_open_url")

    result = registry.execute(action_name, query=query)

    assert result.success is True
    assert expected in opened[0]
    assert result.data["query"] == query


@pytest.mark.parametrize(
    ("action_name", "kwargs", "expected"),
    [
        ("youtube_open", {}, "https://www.youtube.com/"),
        ("youtube_search", {"query": "música brasileira"}, "youtube.com/results?search_query=m%C3%BAsica+brasileira"),
        ("spotify_search", {"query": "jazz focus"}, "open.spotify.com/search/jazz%20focus"),
    ],
)
def test_browser_opening_media_actions_work(monkeypatch, action_name, kwargs, expected):
    # AUDITORIA_2026-08-27 (Alex, ao vivo): "abra o youtube" parou de
    # funcionar, bloqueado sem motivo -- youtube_open/search e spotify_search
    # sao LOCAL_PC_CONTROL de proposito e tem que sempre funcionar. Este
    # teste antes esperava o oposto (bloqueado), o que era o proprio bug.
    calls: list[str] = []

    def open_url(url):
        calls.append(url)
        return ActionResult(success=True, data={"dispatch": "DISPATCH_PROVEN"})

    monkeypatch.setattr(media_apps, "_send_url_to_default_browser", open_url)
    registry = get_registry()
    assert load_capability("browser_open_url")

    allowed = registry.execute(action_name, **kwargs)

    assert allowed.success
    assert expected in calls[0]


@pytest.mark.parametrize("query", ["", "   ", "x" * 201, "bad\nquery"])
def test_media_search_rejects_invalid_query_without_opening(monkeypatch, query):
    open_url = AsyncMock()

    result = media_apps.youtube_search_action(query)

    assert result.success is False
    open_url.assert_not_called()


class _FakeSkip:
    name = "Pular anúncio"

    def __init__(self, invoked=True):
        self.invoked = invoked

    def invoke(self):
        return self.invoked


def test_youtube_skip_ad_requires_button_to_disappear(monkeypatch):
    control = _FakeSkip()
    states = iter((control, None))
    monkeypatch.setattr(media_apps, "_find_youtube_skip_button", lambda timeout=1.5: next(states))

    result = media_apps.youtube_skip_ad_action()

    assert result.success is True
    assert result.data == {
        "status": "CONFIRMED",
        "button": "Pular anúncio",
        "coordinates_used": False,
    }


def test_youtube_skip_ad_never_claims_success_without_postcondition(monkeypatch):
    control = _FakeSkip()
    monkeypatch.setattr(media_apps, "_find_youtube_skip_button", lambda timeout=1.5: control)

    result = media_apps.youtube_skip_ad_action()

    assert result.success is False
    assert result.data["status"] == "POSTCONDITION_FAILED"


def test_youtube_play_by_name_requires_playback_postcondition(monkeypatch):
    control = _FakeSkip()
    control.name = "Dire Straits - Sultans Of Swing"
    monkeypatch.setattr(
        media_apps,
        "youtube_search_action",
        lambda query: ActionResult(success=True, data={"query": query}),
    )
    monkeypatch.setattr(media_apps, "_find_youtube_video_result", lambda query: control)
    monkeypatch.setattr(media_apps, "_ensure_youtube_playing", lambda: (False, "PAUSED"))

    result = media_apps.youtube_play_by_name_action("Sultans of Swing")

    assert result.success is False
    assert result.data["status"] == "POSTCONDITION_FAILED"


def test_youtube_play_by_name_confirms_selected_playing_result(monkeypatch):
    control = _FakeSkip()
    control.name = "Dire Straits - Sultans Of Swing"
    monkeypatch.setattr(
        media_apps,
        "youtube_search_action",
        lambda query: ActionResult(success=True, data={"query": query}),
    )
    monkeypatch.setattr(media_apps, "_find_youtube_video_result", lambda query: control)
    monkeypatch.setattr(media_apps, "_ensure_youtube_playing", lambda: (True, "PLAYING"))

    result = media_apps.youtube_play_by_name_action("Sultans of Swing")

    assert result.success is True
    assert result.data["status"] == "PLAYING_CONFIRMED"
    assert result.data["coordinates_used"] is False


def test_youtube_pause_requires_observed_state_change(monkeypatch):
    control = _FakeSkip()
    states = iter((("PLAYING", control), ("PAUSED", None)))
    monkeypatch.setattr(media_apps, "_find_youtube_playback_control", lambda timeout=0.0: next(states))

    result = media_apps.youtube_pause_action()

    assert result.success is True
    assert result.output == "Pausado."
    assert result.data["verified"] is True


def test_youtube_now_playing_reads_verified_title(monkeypatch):
    monkeypatch.setattr(media_apps, "_find_youtube_playback_control", lambda timeout=0.0: ("PLAYING", None))
    monkeypatch.setattr(media_apps, "_youtube_window_title", lambda: "Eagles - Hotel California")

    result = media_apps.youtube_now_playing_action()

    assert result.success is True
    assert result.output == "Tocando Eagles - Hotel California."


def test_youtube_seek_requires_real_position_change(monkeypatch):
    positions = iter((42.0, 42.0, 72.0))
    monkeypatch.setattr(media_apps, "_youtube_playback_position", lambda: next(positions))
    monkeypatch.setattr(media_apps, "_youtube_target_window", lambda: (123, "UNAMBIGUOUS_YOUTUBE"))
    sent = []
    monkeypatch.setattr(media_apps, "_send_browser_hotkey", lambda hwnd, keys: sent.append(keys) or True)
    monkeypatch.setattr(media_apps.time, "sleep", lambda seconds: None)
    result = media_apps.youtube_seek_action(30)
    assert result.success is True
    assert result.data["before_seconds"] == 42.0
    assert result.data["after_seconds"] == 72.0
    assert sent == [(0x27,) * 6]


def test_youtube_seek_never_claims_success_without_readback(monkeypatch):
    monkeypatch.setattr(media_apps, "_youtube_playback_position", lambda: None)
    monkeypatch.setattr(media_apps, "_youtube_target_window", lambda: (123, "UNAMBIGUOUS_YOUTUBE"))
    result = media_apps.youtube_seek_action(-10)
    assert result.success is False
    assert result.data["status"] == "POSITION_UNAVAILABLE"


def test_youtube_semantic_control_has_no_coordinate_fallback():
    source = inspect.getsource(media_apps._find_youtube_skip_button)
    source += inspect.getsource(media_apps.youtube_skip_ad_action)
    for forbidden in ("SetCursorPos", "mouse_event", "click(", "coordinates"):
        if forbidden == "coordinates":
            continue
        assert forbidden not in source


@pytest.mark.parametrize(
    ("phrase", "action", "param"),
    [
        ("pesquise lo-fi no youtube", "youtube_search", "lo-fi"),
        ("toque Sultans of Swing", "youtube_play_by_name", "sultans of swing"),
        ("pause", "youtube_pause", "pause"),
        ("continue a música", "youtube_resume", "resume"),
        ("avance 30 segundos", "youtube_seek", "30"),
        ("volta 10 segundos", "youtube_seek", "-10"),
        ("volta um pouco", "youtube_seek", "-10"),
        ("recomeça essa música", "youtube_seek", "restart"),
        ("o que está tocando", "youtube_now_playing", "current"),
        ("próxima música", "youtube_next", "next"),
        ("não gostei dessa música, coloca outra dele", "youtube_another_by_artist", "current_artist"),
        ("procure jazz no spotify", "spotify_search", "jazz"),
        ("pule o anúncio", "youtube_skip_ad", "skip"),
        ("abra uma nova guia", "browser_new_tab", "new_tab"),
        ("volte no navegador", "browser_back", "back"),
        ("avance no navegador", "browser_forward", "forward"),
        # ZARA-VOLTE-SOZINHO-001: golden path da missao usa "Volte." sozinho,
        # sem "no navegador" -- igual "minimiza" ja funciona sem "a janela".
        ("volte", "browser_back", "back"),
        ("volta", "browser_back", "back"),
        ("avance", "browser_forward", "forward"),
        ("nova aba", "browser_new_tab", "new_tab"),
        ("desça a página", "browser_scroll", "down"),
        ("suba um pouco", "browser_scroll", "up"),
        ("feche essa aba", "browser_close_tab", "close"),
    ],
)
def test_media_app_voice_intents_are_local(phrase, action, param):
    result = PcVoiceIntentDetector().detect(phrase)

    assert result.is_pc_intent is True
    assert result.action == action
    assert result.param == param
    assert result.blocked is False


@pytest.mark.asyncio
async def test_ipc_routes_spotify_query_as_structured_parameter(monkeypatch):
    execute = AsyncMock(return_value=ActionResult(success=True, output="Pesquisa enviada ao Spotify."))
    monkeypatch.setattr("core.action_registry.execute_action", execute)
    handler = IPCHandler(AsyncMock())

    reply = await handler._try_pc_intent("pesquise jazz focus no spotify")

    assert reply == "Pesquisa enviada ao Spotify."
    execute.assert_awaited_once_with("spotify_search", query="jazz focus")


def test_browser_native_shortcut_requires_title_postcondition(monkeypatch):
    titles = iter(("YouTube - Google Chrome", "YouTube - Google Chrome", "Nova guia - Google Chrome"))
    monkeypatch.setattr(media_apps, "_browser_target_window", lambda: (123, "UNAMBIGUOUS"))
    monkeypatch.setattr(media_apps, "_send_browser_hotkey", lambda hwnd, keys: hwnd == 123)
    monkeypatch.setattr(media_apps, "_window_text", lambda hwnd: next(titles))

    result = media_apps.browser_new_tab_action()

    assert result.success is True
    assert result.data["verified"] is True
    assert result.data["coordinates_used"] is False


def test_browser_native_shortcut_never_claims_success_without_change(monkeypatch):
    monkeypatch.setattr(media_apps, "_browser_target_window", lambda: (123, "FOREGROUND"))
    monkeypatch.setattr(media_apps, "_send_browser_hotkey", lambda hwnd, keys: True)
    monkeypatch.setattr(media_apps, "_window_text", lambda hwnd: "YouTube - Google Chrome")
    monkeypatch.setattr(media_apps.time, "sleep", lambda seconds: None)

    result = media_apps.browser_back_action()

    assert result.success is False
    assert result.data["status"] == "POSTCONDITION_FAILED"


def test_browser_native_shortcut_rejects_ambiguous_target(monkeypatch):
    monkeypatch.setattr(media_apps, "_browser_target_window", lambda: (None, "AMBIGUOUS"))

    result = media_apps.browser_forward_action()

    assert result.success is False
    assert result.data["status"] == "AMBIGUOUS"


def test_browser_scroll_requires_readback(monkeypatch):
    monkeypatch.setattr(media_apps, "_browser_target_window", lambda: (123, "UNAMBIGUOUS"))
    monkeypatch.setattr(media_apps, "_window_text", lambda hwnd: "Example - Google Chrome")
    monkeypatch.setattr(media_apps, "_browser_scroll_document", lambda hwnd, direction: (10.0, 17.5))
    result = media_apps.browser_scroll_action("down")
    assert result.success is True
    assert result.data["before"] == 10.0
    assert result.data["after"] == 17.5


def test_browser_room_is_protected_from_mutation(monkeypatch):
    monkeypatch.setattr(media_apps, "_browser_target_window", lambda: (123, "FOREGROUND"))
    monkeypatch.setattr(media_apps, "_window_text", lambda hwnd: "ZARA Room Lab - Google Chrome")
    result = media_apps.browser_scroll_action("down")
    assert result.success is False
    assert result.data["status"] == "PROTECTED_ROOM"
