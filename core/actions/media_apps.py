"""Closed, semantic controls for YouTube and Spotify."""
from __future__ import annotations

import re
import time
import unicodedata
from urllib.parse import quote, quote_plus

from core.action_registry import ActionResult, action
from core.actions.os_ops import (
    _eligible_windows,
    _foreground_window,
    _send_url_to_default_browser,
    _window_process_name,
    _window_text,
)

_YOUTUBE_SKIP_NAMES = (
    "Pular anúncio",
    "Pular anúncios",
    "Pular",
    "Skip ad",
    "Skip ads",
    "Skip",
)
_YOUTUBE_SPONSORED_MARKERS = ("anuncio", "patrocinado", "sponsored", "promoted")
_BROWSER_PROCESSES = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"}
_BROWSER_HOTKEYS = {
    "new_tab": (0x11, 0x54),  # Ctrl+T
    "back": (0x12, 0x25),  # Alt+Left
    "forward": (0x12, 0x27),  # Alt+Right
    "close_tab": (0x11, 0x57),  # Ctrl+W
}


def _protected_room_title(title: str) -> bool:
    return "zara room" in _normalized(title)


def _safe_query(query: str) -> str | None:
    raw = str(query or "")
    if any(ord(char) < 32 for char in raw):
        return None
    value = " ".join(raw.split())
    if not value or len(value) > 200:
        return None
    return value


def _browser_target_window() -> tuple[int | None, str]:
    """Choose only an active or unambiguous external browser window."""
    candidates = [
        hwnd for hwnd in _eligible_windows()
        if _window_process_name(hwnd) in _BROWSER_PROCESSES
    ]
    foreground = _foreground_window()
    if foreground in candidates:
        return foreground, "FOREGROUND"
    if len(candidates) == 1:
        return candidates[0], "UNAMBIGUOUS"
    if not candidates:
        return None, "NO_BROWSER"
    return None, "AMBIGUOUS"


def _youtube_target_window() -> tuple[int | None, str]:
    """Select an active or unique browser window whose title is YouTube."""
    candidates = [
        hwnd for hwnd in _eligible_windows()
        if _window_process_name(hwnd) in _BROWSER_PROCESSES
        and "youtube" in _normalized(_window_text(hwnd))
    ]
    foreground = _foreground_window()
    if foreground in candidates:
        return foreground, "FOREGROUND"
    if len(candidates) == 1:
        return candidates[0], "UNAMBIGUOUS_YOUTUBE"
    if not candidates:
        return None, "NO_YOUTUBE_WINDOW"
    return None, "AMBIGUOUS_YOUTUBE"


def _send_browser_hotkey(hwnd: int, keys: tuple[int, ...]) -> bool:
    """Send one fixed native shortcut after foreground verification."""
    import ctypes

    user32 = ctypes.windll.user32
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.12)
    if int(user32.GetForegroundWindow() or 0) != hwnd:
        return False
    for key in keys:
        user32.keybd_event(key, 0, 0, 0)
    for key in reversed(keys):
        user32.keybd_event(key, 0, 0x0002, 0)
    return True


def _browser_title_shortcut(command: str) -> ActionResult:
    """Execute a fixed browser accelerator and require an observable title change."""
    target, selection = _browser_target_window()
    if target is None:
        reason = "nenhuma janela de navegador" if selection == "NO_BROWSER" else "mais de uma janela de navegador"
        return ActionResult(
            success=False,
            error=f"Controle não executado: {reason}; o alvo não é inequívoco.",
            data={"status": selection, "verified": False, "coordinates_used": False},
        )
    before = _window_text(target).strip()
    if _protected_room_title(before):
        return ActionResult(success=False, error="A ZARA Room está protegida e não será controlada.", data={"status": "PROTECTED_ROOM", "verified": False})
    if not _send_browser_hotkey(target, _BROWSER_HOTKEYS[command]):
        return ActionResult(
            success=False,
            error="O navegador não pôde ser colocado em primeiro plano com segurança.",
            data={"status": "FOCUS_FAILED", "verified": False, "coordinates_used": False},
        )
    after = before
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        observed = _window_text(target).strip()
        if observed and observed != before:
            after = observed
            break
        time.sleep(0.1)
    if after == before:
        return ActionResult(
            success=False,
            error="Atalho enviado, mas a mudança do navegador não pôde ser confirmada.",
            data={
                "status": "POSTCONDITION_FAILED", "verified": False,
                "before_title": before, "after_title": after,
                "coordinates_used": False,
            },
        )
    labels = {"new_tab": "Nova guia aberta", "back": "Navegação voltou", "forward": "Navegação avançou"}
    return ActionResult(
        success=True,
        output=f"{labels[command]} e confirmada pelo título da janela.",
        data={
            "status": "CONFIRMED", "verified": True, "selection": selection,
            "before_title": before, "after_title": after,
            "coordinates_used": False,
        },
    )


@action(name="browser_new_tab", category="media", description="Open a browser tab with a verified native shortcut", capability="LOCAL_PC_CONTROL")
def browser_new_tab_action() -> ActionResult:
    return _browser_title_shortcut("new_tab")


@action(name="browser_back", category="media", description="Navigate back with a verified native browser shortcut", capability="LOCAL_PC_CONTROL")
def browser_back_action() -> ActionResult:
    return _browser_title_shortcut("back")


@action(name="browser_forward", category="media", description="Navigate forward with a verified native browser shortcut", capability="LOCAL_PC_CONTROL")
def browser_forward_action() -> ActionResult:
    return _browser_title_shortcut("forward")


def _browser_scroll_document(hwnd: int, direction: str) -> tuple[float, float] | None:
    automation, UIA = _uia_client()
    if automation is None:
        return None
    try:
        window = automation.ElementFromHandle(hwnd)
        condition = automation.CreatePropertyCondition(UIA.UIA_IsScrollPatternAvailablePropertyId, True)
        element = window.FindFirst(UIA.TreeScope_Descendants, condition)
        if element is None:
            return None
        pattern = element.GetCurrentPattern(UIA.UIA_ScrollPatternId).QueryInterface(UIA.IUIAutomationScrollPattern)
        before = float(pattern.CurrentVerticalScrollPercent)
        pattern.Scroll(2, 4 if direction == "down" else 1)  # horizontal none, vertical small step
        after = before
        deadline = time.monotonic() + 0.8
        while time.monotonic() < deadline:
            time.sleep(0.1)
            after = float(pattern.CurrentVerticalScrollPercent)
            if after != before:
                break
        return before, after
    except Exception:
        return None


@action(name="browser_scroll", category="media", description="Scroll an unequivocal active browser document with UI Automation readback", capability="LOCAL_PC_CONTROL")
def browser_scroll_action(direction: str) -> ActionResult:
    canonical = str(direction or "").strip().casefold()
    if canonical not in {"up", "down"}:
        return ActionResult(success=False, error="Direção de rolagem inválida.")
    target, selection = _browser_target_window()
    if target is None:
        return ActionResult(success=False, error="Não consegui identificar um navegador inequívoco.", data={"status": selection, "verified": False})
    title = _window_text(target).strip()
    if _protected_room_title(title):
        return ActionResult(success=False, error="A ZARA Room está protegida e não será controlada.", data={"status": "PROTECTED_ROOM", "verified": False})
    observed = _browser_scroll_document(target, canonical)
    if observed is None:
        return ActionResult(success=False, error="A página não expôs rolagem acessível.", data={"status": "SCROLL_UNAVAILABLE", "verified": False})
    before, after = observed
    changed = after != before
    boundary = (canonical == "up" and before <= 0) or (canonical == "down" and before >= 100)
    if not changed and not boundary:
        return ActionResult(success=False, error="A rolagem foi solicitada, mas não pôde ser confirmada.", data={"before": before, "after": after, "verified": False})
    return ActionResult(success=True, output="Página rolada e confirmada." if changed else "A página já está no limite.", data={"hwnd": target, "direction": canonical, "before": before, "after": after, "boundary": boundary, "verified": True})


def _browser_tab_count(hwnd: int) -> int | None:
    automation, UIA = _uia_client()
    if automation is None:
        return None
    try:
        window = automation.ElementFromHandle(hwnd)
        condition = automation.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, UIA.UIA_TabItemControlTypeId)
        return int(window.FindAll(UIA.TreeScope_Descendants, condition).Length)
    except Exception:
        return None


@action(name="browser_close_tab", category="media", description="Close one verified browser tab without closing the browser window", capability="LOCAL_PC_CONTROL")
def browser_close_tab_action() -> ActionResult:
    target, selection = _browser_target_window()
    if target is None:
        return ActionResult(success=False, error="Não consegui identificar um navegador inequívoco.", data={"status": selection, "verified": False})
    before_title = _window_text(target).strip()
    if _protected_room_title(before_title):
        return ActionResult(success=False, error="A ZARA Room está protegida e não será fechada.", data={"status": "PROTECTED_ROOM", "verified": False})
    before_count = _browser_tab_count(target)
    if before_count is None or before_count < 2:
        return ActionResult(success=False, error="Não confirmei duas abas; fechar poderia encerrar a janela.", data={"status": "TAB_COUNT_UNSAFE", "tab_count": before_count, "verified": False})
    if not _send_browser_hotkey(target, _BROWSER_HOTKEYS["close_tab"]):
        return ActionResult(success=False, error="O navegador não pôde ser focado com segurança.")
    import ctypes
    time.sleep(0.25)
    after_count = _browser_tab_count(target)
    alive = bool(ctypes.windll.user32.IsWindow(target))
    verified = alive and after_count == before_count - 1
    if not verified:
        return ActionResult(success=False, error="A redução de uma aba não pôde ser confirmada.", data={"before_count": before_count, "after_count": after_count, "window_alive": alive, "verified": False})
    return ActionResult(success=True, output="Aba fechada e confirmada; a janela permaneceu aberta.", data={"hwnd": target, "before_count": before_count, "after_count": after_count, "window_alive": True, "verified": True})


def _browser_accessible_page(hwnd: int) -> tuple[str, str]:
    """Read the active browser document through UI Automation, never page secrets."""
    automation, UIA = _uia_client()
    if automation is None:
        return "", ""
    try:
        window = automation.ElementFromHandle(hwnd)
        document = window.FindFirst(
            UIA.TreeScope_Descendants,
            automation.CreatePropertyCondition(UIA.UIA_ControlTypePropertyId, UIA.UIA_DocumentControlTypeId),
        )
        if document is None:
            return "", ""
        url = ""
        address = window.FindFirst(
            UIA.TreeScope_Descendants,
            automation.CreatePropertyCondition(UIA.UIA_AutomationIdPropertyId, "address and search bar"),
        )
        if address is not None:
            try:
                pattern = address.GetCurrentPattern(UIA.UIA_ValuePatternId)
                url = str(pattern.QueryInterface(UIA.IUIAutomationValuePattern).CurrentValue or "").strip()
            except Exception:
                url = ""
        elements = document.FindAll(UIA.TreeScope_Descendants, automation.CreateTrueCondition())
        lines: list[str] = []
        seen: set[str] = set()
        for index in range(min(int(elements.Length), 3000)):
            element = elements.GetElement(index)
            try:
                if bool(element.CurrentIsPassword):
                    continue
                name = " ".join(str(element.CurrentName or "").split())
            except Exception:
                continue
            if not name or name in seen or len(name) > 1000:
                continue
            seen.add(name)
            lines.append(name)
            if sum(map(len, lines)) >= 12_000:
                break
        return url, "\n".join(lines)
    except Exception:
        return "", ""


def _brief_page_summary(title: str, content: str) -> str:
    cleaned = re.sub(r"\s+", " ", content).strip()
    if not cleaned:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    useful = [sentence for sentence in sentences if len(sentence) >= 35][:3] or [cleaned[:500]]
    summary = " ".join(useful)[:900]
    return f"{title}: {summary}" if title and title.casefold() not in summary.casefold() else summary


@action(name="browser_read_page", category="media", description="Read and briefly summarize the real active browser page", capability="READ_ONLY")
def browser_read_page_action() -> ActionResult:
    target, selection = _browser_target_window()
    if target is None:
        reason = "nenhum navegador em primeiro plano" if selection == "NO_BROWSER" else "mais de um navegador possível"
        return ActionResult(success=False, error=f"Não consegui identificar uma aba ativa com segurança: {reason}.", data={"status": selection, "verified": False})
    title = _window_text(target).strip()
    if _protected_room_title(title):
        return ActionResult(success=False, error="A ZARA Room está protegida e não será lida por esta ação.", data={"status": "PROTECTED_ROOM", "verified": False})
    url, content = _browser_accessible_page(target)
    if not content:
        return ActionResult(success=False, error="Consegui identificar a aba, mas não ler o conteúdo real da página.", data={"status": "CONTENT_UNAVAILABLE", "title": title, "url": url, "verified": False})
    summary = _brief_page_summary(title, content)
    return ActionResult(success=True, output=summary, data={"status": "CONTENT_READ", "title": title, "url": url, "content_chars": len(content), "summary": summary, "verified": True, "selection": selection})


@action(name="youtube_search", category="media", description="Search YouTube in the default browser", capability="LOCAL_PC_CONTROL")
def youtube_search_action(query: str) -> ActionResult:
    value = _safe_query(query)
    if value is None:
        return ActionResult(success=False, error="Pesquisa do YouTube inválida.")
    url = f"https://www.youtube.com/results?search_query={quote_plus(value)}"
    result = _send_url_to_default_browser(url)
    if result.success:
        result.output = f"Pesquisa por “{value}” enviada ao YouTube."
        result.data = {**(result.data or {}), "service": "youtube", "query": value}
    return result


@action(name="youtube_open", category="media", description="Open the fixed YouTube home destination", capability="LOCAL_PC_CONTROL")
def youtube_open_action() -> ActionResult:
    result = _send_url_to_default_browser("https://www.youtube.com/")
    if result.success:
        result.output = "YouTube enviado ao navegador padrão."
        result.data = {**(result.data or {}), "service": "youtube", "route": "home"}
    return result


@action(name="spotify_search", category="media", description="Search Spotify in the default browser", capability="LOCAL_PC_CONTROL")
def spotify_search_action(query: str) -> ActionResult:
    value = _safe_query(query)
    if value is None:
        return ActionResult(success=False, error="Pesquisa do Spotify inválida.")
    url = f"https://open.spotify.com/search/{quote(value, safe='')}"
    result = _send_url_to_default_browser(url)
    if result.success:
        result.output = f"Pesquisa por “{value}” enviada ao Spotify."
        result.data = {**(result.data or {}), "service": "spotify", "query": value}
    return result


class _InvokeControl:
    def __init__(self, pattern, name: str):
        self._pattern = pattern
        self.name = name

    def invoke(self) -> bool:
        try:
            self._pattern.Invoke()
            return True
        except Exception:
            return False


def _normalized(value: str) -> str:
    folded = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join(
        "".join(char for char in folded if not unicodedata.combining(char)).casefold().split()
    )


def _invoke_pattern(element, UIA) -> _InvokeControl | None:
    try:
        pattern = element.GetCurrentPattern(UIA.UIA_InvokePatternId)
        pattern = pattern.QueryInterface(UIA.IUIAutomationInvokePattern)
        return _InvokeControl(pattern, str(element.CurrentName or ""))
    except Exception:
        return None


def _uia_client():
    try:
        import comtypes.client

        try:
            from comtypes.gen import UIAutomationClient as UIA
        except Exception:
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen import UIAutomationClient as UIA
        automation = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}",
            interface=UIA.IUIAutomation,
        )
        return automation, UIA
    except Exception:
        return None, None


def _belongs_to_youtube_browser(element, automation) -> bool:
    try:
        import psutil

        process_name = psutil.Process(int(element.CurrentProcessId)).name().casefold()
        if process_name not in _BROWSER_PROCESSES:
            return False
        walker = automation.ControlViewWalker
        current = element
        for _ in range(16):
            name = str(current.CurrentName or "").casefold()
            if "youtube" in name:
                return True
            current = walker.GetParentElement(current)
            if current is None:
                break
    except Exception:
        return False
    return False


def _find_youtube_skip_button(timeout: float = 1.5) -> _InvokeControl | None:
    automation, UIA = _uia_client()
    if automation is None:
        return None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root = automation.GetRootElement()
        for name in _YOUTUBE_SKIP_NAMES:
            try:
                condition = automation.CreatePropertyCondition(UIA.UIA_NamePropertyId, name)
                element = root.FindFirst(UIA.TreeScope_Descendants, condition)
                if element is None or not _belongs_to_youtube_browser(element, automation):
                    continue
                pattern = element.GetCurrentPattern(UIA.UIA_InvokePatternId)
                pattern = pattern.QueryInterface(UIA.IUIAutomationInvokePattern)
                return _InvokeControl(pattern, name)
            except Exception:
                continue
        time.sleep(0.15)
    return None


def _find_youtube_video_result(
    query: str, timeout: float = 8.0, exclude_title: str | None = None
) -> _InvokeControl | None:
    """Find the best accessible organic YouTube result without coordinates."""
    value = _safe_query(query)
    if value is None:
        return None
    query_tokens = {token for token in _normalized(value).split() if len(token) > 1}
    automation, UIA = _uia_client()
    if automation is None:
        return None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            root = automation.GetRootElement()
            condition = automation.CreatePropertyCondition(
                UIA.UIA_AutomationIdPropertyId, "video-title"
            )
            elements = root.FindAll(UIA.TreeScope_Descendants, condition)
            candidates = []
            for index in range(int(elements.Length)):
                element = elements.GetElement(index)
                if element is None or not _belongs_to_youtube_browser(element, automation):
                    continue
                name = str(element.CurrentName or "").strip()
                normalized_name = _normalized(name)
                excluded = _normalized(exclude_title or "")
                if excluded and (excluded in normalized_name or normalized_name in excluded):
                    continue
                if any(marker in normalized_name for marker in _YOUTUBE_SPONSORED_MARKERS):
                    continue
                matched = sum(token in normalized_name for token in query_tokens)
                if matched == 0:
                    continue
                control = _invoke_pattern(element, UIA)
                if control is not None:
                    coverage = matched / max(1, len(query_tokens))
                    candidates.append((coverage, matched, -index, control))
            if candidates:
                candidates.sort(key=lambda item: item[:3], reverse=True)
                return candidates[0][3]
        except Exception:
            pass
        time.sleep(0.2)
    return None


def _find_youtube_button(prefixes: tuple[str, ...], timeout: float = 1.5) -> _InvokeControl | None:
    automation, UIA = _uia_client()
    if automation is None:
        return None
    normalized_prefixes = tuple(_normalized(prefix) for prefix in prefixes)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            root = automation.GetRootElement()
            condition = automation.CreatePropertyCondition(
                UIA.UIA_ControlTypePropertyId, UIA.UIA_ButtonControlTypeId
            )
            elements = root.FindAll(UIA.TreeScope_Descendants, condition)
            for index in range(int(elements.Length)):
                element = elements.GetElement(index)
                if element is None or not _belongs_to_youtube_browser(element, automation):
                    continue
                try:
                    if bool(element.CurrentIsOffscreen) or not bool(element.CurrentIsEnabled):
                        continue
                except Exception:
                    continue
                name = _normalized(str(element.CurrentName or ""))
                if name.startswith(normalized_prefixes):
                    control = _invoke_pattern(element, UIA)
                    if control is not None:
                        return control
        except Exception:
            pass
        time.sleep(0.15)
    return None


def _find_youtube_playback_control(timeout: float = 0.0) -> tuple[str, _InvokeControl | None]:
    """Return the semantic YouTube player state and its play/pause control."""
    automation, UIA = _uia_client()
    if automation is None:
        return "UNAVAILABLE", None
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        try:
            root = automation.GetRootElement()
            condition = automation.CreatePropertyCondition(
                UIA.UIA_ControlTypePropertyId, UIA.UIA_ButtonControlTypeId
            )
            elements = root.FindAll(UIA.TreeScope_Descendants, condition)
            for index in range(int(elements.Length)):
                element = elements.GetElement(index)
                if element is None or not _belongs_to_youtube_browser(element, automation):
                    continue
                try:
                    if bool(element.CurrentIsOffscreen) or not bool(element.CurrentIsEnabled):
                        continue
                except Exception:
                    continue
                name = _normalized(str(element.CurrentName or ""))
                if name.startswith(("pausa", "pausar", "pause")):
                    return "PLAYING", _invoke_pattern(element, UIA)
                if name.startswith(("reproduzir", "play")):
                    return "PAUSED", _invoke_pattern(element, UIA)
        except Exception:
            pass
        if time.monotonic() >= deadline:
            return "UNKNOWN", None
        time.sleep(0.2)


def _ensure_youtube_playing(timeout: float = 10.0) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout
    tried_play = False
    play_invoked_at = 0.0
    shortcut_tried = False
    last_state = "UNKNOWN"
    while time.monotonic() < deadline:
        state, control = _find_youtube_playback_control(timeout=0.0)
        last_state = state
        if state == "PLAYING":
            return True, state
        if state == "PAUSED" and control is not None and not tried_play:
            tried_play = True
            control.invoke()
            play_invoked_at = time.monotonic()
        elif (
            state == "PAUSED"
            and tried_play
            and not shortcut_tried
            and time.monotonic() - play_invoked_at >= 0.8
        ):
            shortcut_tried = True
            target, _ = _youtube_target_window()
            if target is not None:
                _send_browser_hotkey(target, (0x4B,))
        time.sleep(0.2)
    return False, last_state


def _set_youtube_playback(desired_state: str, timeout: float = 3.0) -> ActionResult:
    state, control = _find_youtube_playback_control(timeout=1.5)
    if state == desired_state:
        label = "Pausado." if desired_state == "PAUSED" else "Continuando."
        return ActionResult(
            success=True,
            output=label,
            data={"status": desired_state, "verified": True, "coordinates_used": False},
        )
    if control is None or state not in {"PLAYING", "PAUSED"}:
        return ActionResult(
            success=False,
            error="Não encontrei um player do YouTube controlável na tela.",
            data={"status": "PLAYER_NOT_FOUND", "verified": False, "coordinates_used": False},
        )
    if not control.invoke():
        return ActionResult(
            success=False,
            error="O player do YouTube recusou o comando.",
            data={"status": "INVOKE_FAILED", "verified": False, "coordinates_used": False},
        )
    deadline = time.monotonic() + timeout
    observed = state
    while time.monotonic() < deadline:
        observed, _ = _find_youtube_playback_control(timeout=0.0)
        if observed == desired_state:
            label = "Pausado." if desired_state == "PAUSED" else "Continuando."
            return ActionResult(
                success=True,
                output=label,
                data={"status": desired_state, "verified": True, "coordinates_used": False},
            )
        time.sleep(0.15)
    target, selection = _youtube_target_window()
    if target is not None and _send_browser_hotkey(target, (0x4B,)):  # YouTube official K shortcut
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            observed, _ = _find_youtube_playback_control(timeout=0.0)
            if observed == desired_state:
                label = "Pausado." if desired_state == "PAUSED" else "Continuando."
                return ActionResult(
                    success=True,
                    output=label,
                    data={"status": desired_state, "verified": True, "method": "YOUTUBE_K", "selection": selection, "coordinates_used": False},
                )
            time.sleep(0.15)
    return ActionResult(
        success=False,
        error="Comando enviado, mas a mudança do player não pôde ser confirmada.",
        data={"status": "POSTCONDITION_FAILED", "observed": observed, "verified": False, "selection": selection, "coordinates_used": False},
    )


def _youtube_window_title() -> str | None:
    target, _ = _youtube_target_window()
    if target is None:
        return None
    title = _window_text(target).strip()
    normalized = _normalized(title)
    if "youtube" not in normalized:
        return None
    for suffix in (
        " - YouTube - Google Chrome",
        " - YouTube — Mozilla Firefox",
        " - YouTube - Microsoft Edge",
        " - YouTube",
    ):
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
            break
    return title or None


def _youtube_playback_position() -> float | None:
    """Read the YouTube seek slider through UI Automation, without coordinates."""
    automation, UIA = _uia_client()
    if automation is None:
        return None
    try:
        root = automation.GetRootElement()
        condition = automation.CreatePropertyCondition(UIA.UIA_IsRangeValuePatternAvailablePropertyId, True)
        elements = root.FindAll(UIA.TreeScope_Descendants, condition)
        for index in range(int(elements.Length)):
            element = elements.GetElement(index)
            if element is None or not _belongs_to_youtube_browser(element, automation):
                continue
            name = _normalized(str(element.CurrentName or ""))
            if not any(marker in name for marker in ("controle deslizante", "seek", "progresso", "progress")):
                continue
            pattern = element.GetCurrentPattern(UIA.UIA_RangeValuePatternId).QueryInterface(UIA.IUIAutomationRangeValuePattern)
            value, maximum = float(pattern.CurrentValue), float(pattern.CurrentMaximum)
            if maximum > 0 and 0 <= value <= maximum:
                return value
    except Exception:
        return None
    return None


@action(name="youtube_seek", category="media", description="Seek the visible YouTube player and verify its real position", capability="LOCAL_PC_CONTROL")
def youtube_seek_action(offset_seconds: int = 0, restart: bool = False) -> ActionResult:
    before = _youtube_playback_position()
    target, selection = _youtube_target_window()
    if target is None or before is None:
        return ActionResult(success=False, error="Não encontrei um player do YouTube com posição legível.", data={"status": selection if target is None else "POSITION_UNAVAILABLE", "verified": False, "coordinates_used": False})
    requested = int(offset_seconds)
    if restart:
        keys = (0x24,)
    else:
        if requested == 0 or abs(requested) > 3600 or abs(requested) % 5:
            return ActionResult(success=False, error="O avanço deve ser múltiplo de 5 segundos, entre -3600 e 3600.")
        key = 0x27 if requested > 0 else 0x25
        keys = tuple(key for _ in range(abs(requested) // 5))
    if not _send_browser_hotkey(target, keys):
        return ActionResult(success=False, error="Não consegui focar e controlar o player com segurança.", data={"status": "FOCUS_FAILED", "verified": False})
    deadline, after = time.monotonic() + 2.5, before
    while time.monotonic() < deadline:
        observed = _youtube_playback_position()
        if observed is not None:
            after = observed
            changed = after <= 2.0 if restart else (after > before + 1.0 if requested > 0 else after < before - 1.0)
            if changed:
                label = "Recomecei do início." if restart else f"{'Avancei' if requested > 0 else 'Voltei'} {abs(requested)} segundos."
                return ActionResult(success=True, output=label, data={"status": "POSITION_CONFIRMED", "verified": True, "before_seconds": before, "after_seconds": after, "requested_seconds": requested, "selection": selection, "coordinates_used": False})
        time.sleep(0.15)
    return ActionResult(success=False, error="Comando enviado, mas a nova posição não pôde ser confirmada.", data={"status": "POSTCONDITION_FAILED", "before_seconds": before, "after_seconds": after, "verified": False, "coordinates_used": False})


@action(name="youtube_pause", category="media", description="Pause the visible YouTube player with a verified semantic control", capability="LOCAL_PC_CONTROL")
def youtube_pause_action() -> ActionResult:
    return _set_youtube_playback("PAUSED")


@action(name="youtube_resume", category="media", description="Resume the visible YouTube player with a verified semantic control", capability="LOCAL_PC_CONTROL")
def youtube_resume_action() -> ActionResult:
    return _set_youtube_playback("PLAYING")


@action(name="youtube_now_playing", category="media", description="Read the visible YouTube title and verified playback state", capability="LOCAL_PC_CONTROL")
def youtube_now_playing_action() -> ActionResult:
    state, _ = _find_youtube_playback_control(timeout=1.0)
    title = _youtube_window_title()
    if state not in {"PLAYING", "PAUSED"} or not title:
        return ActionResult(
            success=False,
            error="Não consegui confirmar o vídeo atual e o estado do player.",
            data={"status": state, "verified": False, "coordinates_used": False},
        )
    output = f"Tocando {title}." if state == "PLAYING" else f"Pausado em {title}."
    return ActionResult(
        success=True,
        output=output,
        data={"status": state, "title": title, "verified": True, "coordinates_used": False},
    )


@action(name="youtube_next", category="media", description="Select the next YouTube item and verify the title changed", capability="LOCAL_PC_CONTROL")
def youtube_next_action() -> ActionResult:
    before = _youtube_window_title()
    if not before:
        return ActionResult(success=False, error="Não encontrei um vídeo ativo do YouTube.")
    control = _find_youtube_button(("Próximo", "Next"))
    invoked = bool(control and control.invoke())
    if not invoked:
        target, _ = _youtube_target_window()
        invoked = bool(target and _send_browser_hotkey(target, (0x10, 0x4E)))  # Shift+N
    if not invoked:
        return ActionResult(
            success=False,
            error="Não consegui acionar o próximo item do YouTube.",
            data={"status": "INVOKE_FAILED", "before_title": before, "coordinates_used": False},
        )
    deadline = time.monotonic() + 7.0
    after = before
    while time.monotonic() < deadline:
        observed = _youtube_window_title()
        if observed and observed != before:
            after = observed
            playing, _ = _ensure_youtube_playing(timeout=2.0)
            if playing:
                return ActionResult(
                    success=True,
                    output=f"Próxima: {after}.",
                    data={"status": "CHANGED_PLAYING", "before_title": before, "title": after, "coordinates_used": False},
                )
        time.sleep(0.2)
    return ActionResult(
        success=False,
        error="Comando enviado, mas a troca de música não pôde ser confirmada.",
        data={"status": "POSTCONDITION_FAILED", "before_title": before, "after_title": after, "coordinates_used": False},
    )


@action(name="youtube_another_by_artist", category="media", description="Play another YouTube result from the current artist", capability="LOCAL_PC_CONTROL")
def youtube_another_by_artist_action() -> ActionResult:
    current = _youtube_window_title()
    if not current or " - " not in current:
        return ActionResult(
            success=False,
            error="Não consegui identificar com segurança o artista atual.",
            data={"status": "ARTIST_CONTEXT_MISSING", "coordinates_used": False},
        )
    artist = current.split(" - ", 1)[0].strip()
    searched = youtube_search_action(artist)
    if not searched.success:
        return searched
    control = _find_youtube_video_result(artist, exclude_title=current)
    if control is None or not control.invoke():
        return ActionResult(
            success=False,
            error=f"Não encontrei outra música acessível de {artist}.",
            data={"status": "ALTERNATIVE_NOT_FOUND", "artist": artist, "coordinates_used": False},
        )
    playing, observed_state = _ensure_youtube_playing()
    selected = control.name
    if not playing:
        return ActionResult(
            success=False,
            error="A alternativa foi selecionada, mas a reprodução não pôde ser confirmada.",
            data={"status": "POSTCONDITION_FAILED", "artist": artist, "selected_title": selected, "playback_state": observed_state, "coordinates_used": False},
        )
    return ActionResult(
        success=True,
        output=f"Coloquei outra de {artist}: {selected}.",
        data={"status": "PLAYING_CONFIRMED", "artist": artist, "selected_title": selected, "playback_state": "PLAYING", "coordinates_used": False},
    )


@action(name="youtube_play_by_name", category="media", description="Search, select and play a named YouTube result semantically", capability="LOCAL_PC_CONTROL")
def youtube_play_by_name_action(query: str) -> ActionResult:
    value = _safe_query(query)
    if value is None:
        return ActionResult(success=False, error="Pedido de música inválido.")
    searched = youtube_search_action(value)
    if not searched.success:
        return searched
    result_control = _find_youtube_video_result(value)
    if result_control is None:
        return ActionResult(
            success=False,
            error="A pesquisa abriu, mas não encontrei um resultado acessível e inequívoco.",
            data={"status": "RESULT_NOT_FOUND", "query": value, "coordinates_used": False},
        )
    selected_title = result_control.name
    if not result_control.invoke():
        return ActionResult(
            success=False,
            error="Encontrei o vídeo, mas o controle acessível recusou a seleção.",
            data={"status": "SELECT_FAILED", "query": value, "selected_title": selected_title, "coordinates_used": False},
        )
    playing, observed_state = _ensure_youtube_playing()
    if not playing:
        return ActionResult(
            success=False,
            error="O vídeo foi selecionado, mas a reprodução não pôde ser confirmada.",
            data={"status": "POSTCONDITION_FAILED", "query": value, "selected_title": selected_title, "playback_state": observed_state, "coordinates_used": False},
        )
    return ActionResult(
        success=True,
        output=f"Tocando {selected_title}.",
        data={"status": "PLAYING_CONFIRMED", "query": value, "selected_title": selected_title, "playback_state": "PLAYING", "coordinates_used": False},
    )


@action(name="youtube_skip_ad", category="media", description="Invoke the visible YouTube skip-ad button semantically", capability="LOCAL_PC_CONTROL")
def youtube_skip_ad_action() -> ActionResult:
    control = _find_youtube_skip_button()
    if control is None:
        return ActionResult(
            success=False,
            error="Não encontrei um botão acessível de anúncio pulável no YouTube.",
            data={"status": "NOT_AVAILABLE", "coordinates_used": False},
        )
    if not control.invoke():
        return ActionResult(
            success=False,
            error="O botão de pular anúncio recusou a ação.",
            data={"status": "INVOKE_FAILED", "button": control.name, "coordinates_used": False},
        )
    disappeared = _find_youtube_skip_button(timeout=1.0) is None
    if not disappeared:
        return ActionResult(
            success=False,
            error="Clique enviado, mas o anúncio não pôde ser confirmado como pulado.",
            data={"status": "POSTCONDITION_FAILED", "button": control.name, "coordinates_used": False},
        )
    return ActionResult(
        success=True,
        output="Anúncio pulado e botão removido da tela.",
        data={"status": "CONFIRMED", "button": control.name, "coordinates_used": False},
    )
