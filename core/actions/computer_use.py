"""Small Windows desktop controls for Zoe's observe-act-observe loop.

Every input action is gated by the existing Supercerebro PC_CONTROL switch.
It also requires the foreground window handle observed by the caller so a
window change cannot silently redirect a click or key press.
"""
from __future__ import annotations

import ctypes
import os
import re
import time
from ctypes import wintypes

from core.action_registry import ActionResult, action


def _safe_pyautogui():
    import pyautogui
    if pyautogui.FAILSAFE is not True:
        raise RuntimeError('O failsafe do mouse precisa permanecer ligado')
    pyautogui.failSafeCheck()
    return pyautogui


def _type_observed_text(text: str) -> bool:
    gui = _safe_pyautogui()
    if text.isascii():
        gui.write(text, interval=0)
        return True
    from core.actions.os_ops import _send_unicode_text
    return _send_unicode_text(text)


def _foreground() -> dict[str, object] | None:
    if os.name != "nt":
        return None
    user32 = ctypes.windll.user32
    hwnd = int(user32.GetForegroundWindow())
    if not hwnd or not user32.IsWindowVisible(hwnd):
        return None
    length = int(user32.GetWindowTextLengthW(hwnd))
    title_buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, title_buffer, length + 1)
    rect = wintypes.RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return {
        "hwnd": hwnd,
        "title": title_buffer.value,
        "rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
    }


def _target(expected_hwnd: int, x: int | None = None, y: int | None = None) -> tuple[dict[str, object] | None, str]:
    current = _foreground()
    if current is None:
        return None, "Janela ativa indisponível."
    if isinstance(expected_hwnd, bool) or int(expected_hwnd) <= 0 or current["hwnd"] != int(expected_hwnd):
        return None, "A janela ativa mudou. Observe a tela novamente antes de agir."
    if x is not None and y is not None:
        rect = current["rect"]
        if not (rect["left"] <= x < rect["right"] and rect["top"] <= y < rect["bottom"]):
            return None, "Ponto fora da janela ativa."
    return current, ""


@action(name="computer_foreground", category="computer", description="Lê a janela ativa para orientar um passo de Use Computer", capability="READ_ONLY")
def computer_foreground_action() -> ActionResult:
    current = _foreground()
    if current is None:
        return ActionResult(False, error="Janela ativa indisponível.")
    return ActionResult(True, output=f"Janela ativa: {current['title']}", data=current)


@action(name="computer_list_windows", category="computer", description="Lista janelas visíveis para escolher onde agir", capability="READ_ONLY")
def computer_list_windows_action() -> ActionResult:
    if os.name != "nt":
        return ActionResult(False, error="Lista de janelas disponível somente no Windows.")
    user32 = ctypes.windll.user32
    windows: list[dict[str, object]] = []

    def collect(hwnd: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        length = int(user32.GetWindowTextLengthW(hwnd))
        if not length:
            return True
        title_buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title_buffer, length + 1)
        title = title_buffer.value.strip()
        if title:
            windows.append({"hwnd": int(hwnd), "title": title})
        return len(windows) < 80

    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    callback = callback_type(collect)
    user32.EnumWindows(callback, 0)
    return ActionResult(True, output=f"{len(windows)} janelas visíveis.", data={"windows": windows})


@action(name="computer_focus_window", category="computer", description="Traz uma janela visível escolhida para a frente", capability="PC_CONTROL")
def computer_focus_window_action(hwnd: int) -> ActionResult:
    if isinstance(hwnd, bool) or not isinstance(hwnd, int) or hwnd <= 0:
        return ActionResult(False, error="Janela inválida.", verificado=False)
    listed = computer_list_windows_action()
    if not listed.success or hwnd not in {item["hwnd"] for item in listed.data["windows"]}:
        return ActionResult(False, error="Janela não está visível; liste novamente.", verificado=False)
    from core.actions.os_ops import _focus_window_verified

    focused = _focus_window_verified(hwnd)
    current = _foreground()
    if not focused or current is None or current["hwnd"] != hwnd:
        return ActionResult(False, error="Não consegui colocar a janela em primeiro plano.", verificado=False)
    return ActionResult(True, output=f"Janela ativa: {current['title']}", data=current, verificado=True)


@action(name="computer_click", category="computer", description="Clica uma vez em um ponto da janela ativa observada", capability="PC_CONTROL")
def computer_click_action(x: int, y: int, expected_hwnd: int) -> ActionResult:
    if any(isinstance(value, bool) or not isinstance(value, int) for value in (x, y, expected_hwnd)):
        return ActionResult(False, error="Coordenadas ou janela inválidas.", verificado=False)
    current, error = _target(expected_hwnd, x, y)
    if current is None:
        return ActionResult(False, error=error, verificado=False)
    try:
        gui = _safe_pyautogui()
        if _target(expected_hwnd, x, y)[0] is None:
            return ActionResult(False, error='A janela mudou antes do clique.', verificado=False)
        gui.click(x, y)
    except Exception as exc:
        return ActionResult(False, error=f'Clique interrompido: {type(exc).__name__}', verificado=False)
    return ActionResult(True, output="Clique enviado; observe a tela para conferir o efeito.", data={"x": x, "y": y, "hwnd": expected_hwnd}, verificado=False)


@action(name="computer_scroll", category="computer", description="Rola a janela ativa observada", capability="PC_CONTROL")
def computer_scroll_action(x: int, y: int, steps: int, expected_hwnd: int) -> ActionResult:
    if any(isinstance(value, bool) or not isinstance(value, int) for value in (x, y, steps, expected_hwnd)) or not -5 <= steps <= 5 or steps == 0:
        return ActionResult(False, error="Rolagem inválida.", verificado=False)
    current, error = _target(expected_hwnd, x, y)
    if current is None:
        return ActionResult(False, error=error, verificado=False)
    try:
        gui = _safe_pyautogui()
        if _target(expected_hwnd, x, y)[0] is None:
            return ActionResult(False, error='A janela mudou antes da rolagem.', verificado=False)
        gui.scroll(steps, x=x, y=y)
    except Exception as exc:
        return ActionResult(False, error=f'Rolagem interrompida: {type(exc).__name__}', verificado=False)
    return ActionResult(True, output="Rolagem enviada; observe a tela para conferir o efeito.", data={"steps": steps, "hwnd": expected_hwnd}, verificado=False)


_KEYS = {
    "tab": 0x09, "enter": 0x0D, "escape": 0x1B, "space": 0x20,
    "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "backspace": 0x08, "delete": 0x2E,
}


@action(name="computer_press_key", category="computer", description="Pressiona uma tecla permitida na janela ativa observada", capability="PC_CONTROL")
def computer_press_key_action(key: str, expected_hwnd: int) -> ActionResult:
    canonical = str(key or "").strip().casefold()
    if canonical not in _KEYS:
        return ActionResult(False, error="Tecla indisponível.", verificado=False)
    if isinstance(expected_hwnd, bool) or not isinstance(expected_hwnd, int):
        return ActionResult(False, error="Janela inválida.", verificado=False)
    current, error = _target(expected_hwnd)
    if current is None:
        return ActionResult(False, error=error, verificado=False)
    try:
        gui = _safe_pyautogui()
        if _target(expected_hwnd)[0] is None:
            return ActionResult(False, error='A janela mudou antes da tecla.', verificado=False)
        gui.press(canonical)
    except Exception as exc:
        return ActionResult(False, error=f'Tecla interrompida: {type(exc).__name__}', verificado=False)
    return ActionResult(True, output="Tecla enviada; observe a tela para conferir o efeito.", data={"key": canonical, "hwnd": expected_hwnd}, verificado=False)


_BLOCKED_INPUT_TITLE = re.compile(r"(?i)(password|senha|login|pagamento|payment|checkout|terminal|powershell|command prompt|prompt de comando)")


@action(name="computer_type_text", category="computer", description="Digita texto em um campo visível e confirma o conteúdo", capability="PC_CONTROL")
def computer_type_text_action(text: str, expected_hwnd: int) -> ActionResult:
    value = str(text or "")
    if not value or len(value) > 2000 or any(ord(char) < 32 for char in value):
        return ActionResult(False, error="Texto inválido para digitação.", verificado=False)
    if isinstance(expected_hwnd, bool) or not isinstance(expected_hwnd, int):
        return ActionResult(False, error="Janela inválida.", verificado=False)
    current, error = _target(expected_hwnd)
    if current is None:
        return ActionResult(False, error=error, verificado=False)
    if _BLOCKED_INPUT_TITLE.search(str(current["title"])):
        return ActionResult(False, error="Esta janela não aceita digitação remota.", verificado=False)
    try:
        import comtypes.client
        try:
            from comtypes.gen import UIAutomationClient as UIA
        except ImportError:
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen import UIAutomationClient as UIA
        from core.actions.os_ops import _uia_field_text

        automation = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=UIA.IUIAutomation
        )
        field = automation.GetFocusedElement()
        pid = wintypes.DWORD()
        ctypes.windll.user32.GetWindowThreadProcessId(expected_hwnd, ctypes.byref(pid))
        if (field is None or int(field.CurrentProcessId or 0) != pid.value
                or bool(field.CurrentIsPassword)
                or int(field.CurrentControlType or 0) not in {
                    int(UIA.UIA_EditControlTypeId), int(UIA.UIA_DocumentControlTypeId)
                }):
            return ActionResult(False, error="Não identifiquei um campo de texto seguro nesta janela.", verificado=False)
        state = {"automation": automation, "UIA": UIA, "element": field}
        before = _uia_field_text(state)
        if before is None or _target(expected_hwnd)[0] is None or not _type_observed_text(value):
            return ActionResult(False, error="Não consegui digitar no campo observado.", verificado=False)
        time.sleep(0.15)
        after = _uia_field_text(state)
        # Some Windows edit controls expose an implicit final CRLF through UIA.
        before_visible = before.rstrip("\r\n")
        after_visible = after.rstrip("\r\n") if after is not None else None
        if after_visible not in (before_visible + value, value):
            # Fallback: UIA nao le campos do Chromium/Electron; confirma via OCR.
            try:
                from core.actions.vision_actions import _ocr_words as _ocr_fb
                from core.actions.vision_actions import _capture as _cap_fb
                _shot = _cap_fb()
                if _shot.success:
                    _words, _ = _ocr_fb(_shot.data["path"], "por+eng")
                    _seen = " ".join(w["text"] for w in _words).lower()
                    _needle = value.strip().lower()[:24]
                    if _needle and _needle in _seen:
                        return ActionResult(True, output="Texto digitado e confirmado via OCR.", data={"hwnd": expected_hwnd, "characters": len(value)}, verificado=True)
            except Exception:
                pass
            return ActionResult(False, error="A digitação não pôde ser confirmada.", verificado=False)
        return ActionResult(True, output="Texto digitado e confirmado.", data={"hwnd": expected_hwnd, "characters": len(value)}, verificado=True)
    except Exception as exc:
        return ActionResult(False, error=f"Digitação indisponível: {type(exc).__name__}", verificado=False)
