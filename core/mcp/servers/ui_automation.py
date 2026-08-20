"""
ZARA 3.0 - MCP UI Automation Server
MCP server for Windows UI Automation operations.
"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from core.mcp.base_server import StdioMCPServer


class UIAutomationMCPServer(StdioMCPServer):
    """MCP server for Windows UI Automation."""

    def __init__(self):
        super().__init__("zara-ui-automation", "1.0.0")
        self._register_tools()

    def _register_tools(self):
        """Register UI Automation tools."""

        # Windows API constants
        self._user32 = ctypes.windll.user32
        self._kernel32 = ctypes.windll.kernel32

        # Virtual key codes
        self._VK = {
            "BACK": 0x08, "TAB": 0x09, "ENTER": 0x0D, "SHIFT": 0x10, "CTRL": 0x11, "ALT": 0x12,
            "PAUSE": 0x13, "CAPSLOCK": 0x14, "ESCAPE": 0x1B, "SPACE": 0x20,
            "PAGEUP": 0x21, "PAGEDOWN": 0x22, "END": 0x23, "HOME": 0x24,
            "LEFT": 0x25, "UP": 0x26, "RIGHT": 0x27, "DOWN": 0x28,
            "SELECT": 0x29, "PRINT": 0x2A, "EXECUTE": 0x2B, "SNAPSHOT": 0x2C,
            "INSERT": 0x2D, "DELETE": 0x2E, "HELP": 0x2F,
            "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34, "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
            "A": 0x41, "B": 0x42, "C": 0x43, "D": 0x44, "E": 0x45, "F": 0x46, "G": 0x47, "H": 0x48, "I": 0x49, "J": 0x4A,
            "K": 0x4B, "L": 0x4C, "M": 0x4D, "N": 0x4E, "O": 0x4F, "P": 0x50, "Q": 0x51, "R": 0x52, "S": 0x53, "T": 0x54,
            "U": 0x55, "V": 0x56, "W": 0x57, "X": 0x58, "Y": 0x59, "Z": 0x5A,
            "LWIN": 0x5B, "RWIN": 0x5C, "APPS": 0x5D,
            "NUMPAD0": 0x60, "NUMPAD1": 0x61, "NUMPAD2": 0x62, "NUMPAD3": 0x63, "NUMPAD4": 0x64,
            "NUMPAD5": 0x65, "NUMPAD6": 0x66, "NUMPAD7": 0x67, "NUMPAD8": 0x68, "NUMPAD9": 0x69,
            "MULTIPLY": 0x6A, "ADD": 0x6B, "SEPARATOR": 0x6C, "SUBTRACT": 0x6D, "DECIMAL": 0x6E, "DIVIDE": 0x6F,
            "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73, "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
            "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
            "VOLUME_MUTE": 0xAD, "VOLUME_DOWN": 0xAE, "VOLUME_UP": 0xAF,
            "MEDIA_NEXT": 0xB0, "MEDIA_PREV": 0xB1, "MEDIA_STOP": 0xB2, "MEDIA_PLAY_PAUSE": 0xB3,
        }

        @self.tool(
            name="ui_find_window",
            description="Find a window by title or class",
            input_schema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Window title (partial match)"},
                    "class_name": {"type": "string", "description": "Window class name"},
                    "exact": {"type": "boolean", "default": False, "description": "Exact title match"},
                },
            }
        )
        async def ui_find_window(title: str = "", class_name: str = "", exact: bool = False) -> dict:
            try:
                results = []

                def enum_windows_proc(hwnd, lparam):
                    if self._user32.IsWindowVisible(hwnd):
                        length = self._user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buff = ctypes.create_unicode_buffer(length + 1)
                            self._user32.GetWindowTextW(hwnd, buff, length + 1)
                            window_title = buff.value

                            match = False
                            if exact and title and window_title == title:
                                match = True
                            elif title and title.lower() in window_title.lower():
                                match = True
                            elif not title:
                                match = True

                            if match and class_name:
                                class_buff = ctypes.create_unicode_buffer(256)
                                self._user32.GetClassNameW(hwnd, class_buff, 256)
                                if class_name.lower() not in class_buff.value.lower():
                                    match = False

                            if match:
                                # Get process ID
                                pid = wintypes.DWORD()
                                self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

                                # Get window rect
                                rect = wintypes.RECT()
                                self._user32.GetWindowRect(hwnd, ctypes.byref(rect))

                                results.append({
                                    "hwnd": hwnd,
                                    "title": window_title,
                                    "class_name": class_buff.value if class_name else "",
                                    "pid": pid.value,
                                    "rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
                                    "visible": True,
                                })
                    return True

                enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(enum_windows_proc)
                self._user32.EnumWindows(enum_proc, 0)

                return {"success": True, "windows": results, "count": len(results)}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="ui_get_foreground_window",
            description="Get the currently active window",
            input_schema={
                "type": "object",
                "properties": {},
            }
        )
        async def ui_get_foreground_window() -> dict:
            try:
                hwnd = self._user32.GetForegroundWindow()
                if not hwnd:
                    return {"success": False, "error": "No foreground window"}

                length = self._user32.GetWindowTextLengthW(hwnd)
                title = ""
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    self._user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value

                class_buff = ctypes.create_unicode_buffer(256)
                self._user32.GetClassNameW(hwnd, class_buff, 256)

                pid = wintypes.DWORD()
                self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

                rect = wintypes.RECT()
                self._user32.GetWindowRect(hwnd, ctypes.byref(rect))

                return {
                    "success": True,
                    "hwnd": hwnd,
                    "title": title,
                    "class_name": class_buff.value,
                    "pid": pid.value,
                    "rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="ui_set_foreground_window",
            description="Bring a window to foreground",
            input_schema={
                "type": "object",
                "properties": {
                    "hwnd": {"type": "integer", "description": "Window handle"},
                },
                "required": ["hwnd"],
            }
        )
        async def ui_set_foreground_window(hwnd: int) -> dict:
            try:
                if not self._user32.IsWindow(hwnd):
                    return {"success": False, "error": "Invalid window handle"}

                # Try to bring to front
                self._user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                result = self._user32.SetForegroundWindow(hwnd)

                return {"success": result != 0, "hwnd": hwnd}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="ui_click",
            description="Click at coordinates",
            input_schema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"], "default": "left"},
                    "clicks": {"type": "integer", "default": 1, "description": "Number of clicks"},
                },
                "required": ["x", "y"],
            }
        )
        async def ui_click(x: int, y: int, button: str = "left", clicks: int = 1) -> dict:
            try:
                # Move cursor
                self._user32.SetCursorPos(x, y)
                time.sleep(0.05)

                button_map = {
                    "left": (0x0002, 0x0004),  # DOWN, UP
                    "right": (0x0008, 0x0010),
                    "middle": (0x0020, 0x0040),
                }

                down, up = button_map.get(button, button_map["left"])

                for _ in range(clicks):
                    self._user32.mouse_event(down, 0, 0, 0, 0)
                    time.sleep(0.02)
                    self._user32.mouse_event(up, 0, 0, 0, 0)
                    time.sleep(0.05)

                return {"success": True, "x": x, "y": y, "button": button, "clicks": clicks}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="ui_type_text",
            description="Type text using SendInput",
            input_schema={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to type"},
                    "delay": {"type": "integer", "default": 10, "description": "Delay between keystrokes in ms"},
                },
                "required": ["text"],
            }
        )
        async def ui_type_text(text: str, delay: int = 10) -> dict:
            try:
                # Use SendInput for Unicode text
                for char in text:
                    # Key down
                    input_struct = self._make_keyboard_input(char, 0)
                    self._user32.SendInput(1, ctypes.byref(input_struct), ctypes.sizeof(input_struct))
                    time.sleep(delay / 1000)
                    # Key up
                    input_struct = self._make_keyboard_input(char, 0x0002)  # KEYEVENTF_KEYUP
                    self._user32.SendInput(1, ctypes.byref(input_struct), ctypes.sizeof(input_struct))
                    time.sleep(delay / 1000)

                return {"success": True, "text": text, "length": len(text)}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="ui_send_key",
            description="Send a key combination",
            input_schema={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Key name (e.g., 'A', 'ENTER', 'F1', 'LWIN')"},
                    "modifiers": {"type": "array", "items": {"type": "string", "enum": ["shift", "ctrl", "alt", "win"]}, "default": [], "description": "Modifier keys"},
                },
                "required": ["key"],
            }
        )
        async def ui_send_key(key: str, modifiers: list[str] = None) -> dict:
            try:
                modifiers = modifiers or []
                key_upper = key.upper()

                if key_upper not in self._VK:
                    return {"success": False, "error": f"Unknown key: {key}"}

                vk = self._VK[key_upper]

                # Press modifiers
                mod_vks = []
                for mod in modifiers:
                    mod_upper = mod.upper()
                    if mod_upper in self._VK:
                        mod_vks.append(self._VK[mod_upper])
                        input_struct = self._make_keyboard_input_vk(mod_vks[-1], 0)
                        self._user32.SendInput(1, ctypes.byref(input_struct), ctypes.sizeof(input_struct))

                # Press main key
                input_struct = self._make_keyboard_input_vk(vk, 0)
                self._user32.SendInput(1, ctypes.byref(input_struct), ctypes.sizeof(input_struct))
                time.sleep(0.05)

                # Release main key
                input_struct = self._make_keyboard_input_vk(vk, 0x0002)
                self._user32.SendInput(1, ctypes.byref(input_struct), ctypes.sizeof(input_struct))

                # Release modifiers in reverse
                for mod_vk in reversed(mod_vks):
                    input_struct = self._make_keyboard_input_vk(mod_vk, 0x0002)
                    self._user32.SendInput(1, ctypes.byref(input_struct), ctypes.sizeof(input_struct))

                return {"success": True, "key": key, "modifiers": modifiers}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="ui_get_cursor_pos",
            description="Get current cursor position",
            input_schema={
                "type": "object",
                "properties": {},
            }
        )
        async def ui_get_cursor_pos() -> dict:
            try:
                point = wintypes.POINT()
                self._user32.GetCursorPos(ctypes.byref(point))
                return {"success": True, "x": point.x, "y": point.y}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="ui_set_cursor_pos",
            description="Set cursor position",
            input_schema={
                "type": "object",
                "properties": {
                    "x": {"type": "integer", "description": "X coordinate"},
                    "y": {"type": "integer", "description": "Y coordinate"},
                },
                "required": ["x", "y"],
            }
        )
        async def ui_set_cursor_pos(x: int, y: int) -> dict:
            try:
                self._user32.SetCursorPos(x, y)
                return {"success": True, "x": x, "y": y}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="ui_window_rect",
            description="Get window rectangle",
            input_schema={
                "type": "object",
                "properties": {
                    "hwnd": {"type": "integer", "description": "Window handle"},
                },
                "required": ["hwnd"],
            }
        )
        async def ui_window_rect(hwnd: int) -> dict:
            try:
                if not self._user32.IsWindow(hwnd):
                    return {"success": False, "error": "Invalid window handle"}

                rect = wintypes.RECT()
                self._user32.GetWindowRect(hwnd, ctypes.byref(rect))

                client_rect = wintypes.RECT()
                self._user32.GetClientRect(hwnd, ctypes.byref(client_rect))

                return {
                    "success": True,
                    "hwnd": hwnd,
                    "screen_rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
                    "client_rect": {"left": client_rect.left, "top": client_rect.top, "right": client_rect.right, "bottom": client_rect.bottom},
                    "width": rect.right - rect.left,
                    "height": rect.bottom - rect.top,
                }
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="ui_window_move_resize",
            description="Move and resize a window",
            input_schema={
                "type": "object",
                "properties": {
                    "hwnd": {"type": "integer", "description": "Window handle"},
                    "x": {"type": "integer", "description": "New X position"},
                    "y": {"type": "integer", "description": "New Y position"},
                    "width": {"type": "integer", "description": "New width"},
                    "height": {"type": "integer", "description": "New height"},
                },
                "required": ["hwnd", "x", "y", "width", "height"],
            }
        )
        async def ui_window_move_resize(hwnd: int, x: int, y: int, width: int, height: int) -> dict:
            try:
                if not self._user32.IsWindow(hwnd):
                    return {"success": False, "error": "Invalid window handle"}

                result = self._user32.MoveWindow(hwnd, x, y, width, height, True)
                return {"success": result != 0, "hwnd": hwnd, "x": x, "y": y, "width": width, "height": height}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="ui_window_minimize",
            description="Minimize a window",
            input_schema={
                "type": "object",
                "properties": {
                    "hwnd": {"type": "integer", "description": "Window handle"},
                },
                "required": ["hwnd"],
            }
        )
        async def ui_window_minimize(hwnd: int) -> dict:
            try:
                if not self._user32.IsWindow(hwnd):
                    return {"success": False, "error": "Invalid window handle"}

                self._user32.ShowWindow(hwnd, 6)  # SW_MINIMIZE
                return {"success": True, "hwnd": hwnd}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="ui_window_maximize",
            description="Maximize a window",
            input_schema={
                "type": "object",
                "properties": {
                    "hwnd": {"type": "integer", "description": "Window handle"},
                },
                "required": ["hwnd"],
            }
        )
        async def ui_window_maximize(hwnd: int) -> dict:
            try:
                if not self._user32.IsWindow(hwnd):
                    return {"success": False, "error": "Invalid window handle"}

                self._user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
                return {"success": True, "hwnd": hwnd}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="ui_window_restore",
            description="Restore a minimized/maximized window",
            input_schema={
                "type": "object",
                "properties": {
                    "hwnd": {"type": "integer", "description": "Window handle"},
                },
                "required": ["hwnd"],
            }
        )
        async def ui_window_restore(hwnd: int) -> dict:
            try:
                if not self._user32.IsWindow(hwnd):
                    return {"success": False, "error": "Invalid window handle"}

                self._user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                return {"success": True, "hwnd": hwnd}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="ui_window_close",
            description="Close a window (WM_CLOSE)",
            input_schema={
                "type": "object",
                "properties": {
                    "hwnd": {"type": "integer", "description": "Window handle"},
                },
                "required": ["hwnd"],
            }
        )
        async def ui_window_close(hwnd: int) -> dict:
            try:
                if not self._user32.IsWindow(hwnd):
                    return {"success": False, "error": "Invalid window handle"}

                self._user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
                return {"success": True, "hwnd": hwnd}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="ui_list_process_windows",
            description="List all windows for a process",
            input_schema={
                "type": "object",
                "properties": {
                    "pid": {"type": "integer", "description": "Process ID"},
                },
                "required": ["pid"],
            }
        )
        async def ui_list_process_windows(pid: int) -> dict:
            try:
                results = []

                def enum_windows_proc(hwnd, lparam):
                    window_pid = wintypes.DWORD()
                    self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))

                    if window_pid.value == pid and self._user32.IsWindowVisible(hwnd):
                        length = self._user32.GetWindowTextLengthW(hwnd)
                        title = ""
                        if length > 0:
                            buff = ctypes.create_unicode_buffer(length + 1)
                            self._user32.GetWindowTextW(hwnd, buff, length + 1)
                            title = buff.value

                        class_buff = ctypes.create_unicode_buffer(256)
                        self._user32.GetClassNameW(hwnd, class_buff, 256)

                        rect = wintypes.RECT()
                        self._user32.GetWindowRect(hwnd, ctypes.byref(rect))

                        results.append({
                            "hwnd": hwnd,
                            "title": title,
                            "class_name": class_buff.value,
                            "rect": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom},
                        })
                    return True

                enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(enum_windows_proc)
                self._user32.EnumWindows(enum_proc, 0)

                return {"success": True, "pid": pid, "windows": results, "count": len(results)}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="ui_screenshot_window",
            description="Capture screenshot of a window",
            input_schema={
                "type": "object",
                "properties": {
                    "hwnd": {"type": "integer", "description": "Window handle"},
                    "path": {"type": "string", "description": "Output file path"},
                },
                "required": ["hwnd", "path"],
            }
        )
        async def ui_screenshot_window(hwnd: int, path: str) -> dict:
            try:
                if not self._user32.IsWindow(hwnd):
                    return {"success": False, "error": "Invalid window handle"}

                # Get window DC
                hwnd_dc = self._user32.GetWindowDC(hwnd)
                if not hwnd_dc:
                    return {"success": False, "error": "Failed to get window DC"}

                try:
                    # Get window rect
                    rect = wintypes.RECT()
                    self._user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    width = rect.right - rect.left
                    height = rect.bottom - rect.top

                    # Create compatible DC and bitmap
                    mfc_dc = ctypes.windll.gdi32.CreateCompatibleDC(hwnd_dc)
                    bitmap = ctypes.windll.gdi32.CreateCompatibleBitmap(hwnd_dc, width, height)
                    ctypes.windll.gdi32.SelectObject(mfc_dc, bitmap)

                    # Copy window content
                    ctypes.windll.gdi32.BitBlt(mfc_dc, 0, 0, width, height, hwnd_dc, 0, 0, 0x00CC0020)  # SRCCOPY

                    # Save bitmap to file
                    self._save_bitmap(bitmap, mfc_dc, width, height, path)

                    # Cleanup
                    ctypes.windll.gdi32.DeleteObject(bitmap)
                    ctypes.windll.gdi32.DeleteDC(mfc_dc)

                    return {"success": True, "path": path, "width": width, "height": height}
                finally:
                    self._user32.ReleaseDC(hwnd, hwnd_dc)
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="ui_get_window_text",
            description="Get text content of a window/control",
            input_schema={
                "type": "object",
                "properties": {
                    "hwnd": {"type": "integer", "description": "Window/control handle"},
                },
                "required": ["hwnd"],
            }
        )
        async def ui_get_window_text(hwnd: int) -> dict:
            try:
                if not self._user32.IsWindow(hwnd):
                    return {"success": False, "error": "Invalid window handle"}

                length = self._user32.GetWindowTextLengthW(hwnd)
                if length == 0:
                    return {"success": True, "hwnd": hwnd, "text": ""}

                buff = ctypes.create_unicode_buffer(length + 1)
                self._user32.GetWindowTextW(hwnd, buff, length + 1)

                return {"success": True, "hwnd": hwnd, "text": buff.value}
            except Exception as e:
                return {"success": False, "error": str(e)}

        @self.tool(
            name="ui_set_window_text",
            description="Set text of a window/control",
            input_schema={
                "type": "object",
                "properties": {
                    "hwnd": {"type": "integer", "description": "Window/control handle"},
                    "text": {"type": "string", "description": "Text to set"},
                },
                "required": ["hwnd", "text"],
            }
        )
        async def ui_set_window_text(hwnd: int, text: str) -> dict:
            try:
                if not self._user32.IsWindow(hwnd):
                    return {"success": False, "error": "Invalid window handle"}

                result = self._user32.SetWindowTextW(hwnd, text)
                return {"success": result != 0, "hwnd": hwnd, "text": text}
            except Exception as e:
                return {"success": False, "error": str(e)}

    def _make_keyboard_input(self, char: str, flags: int):
        """Create keyboard input structure for Unicode character."""
        from ctypes import wintypes

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", wintypes.ULONG_PTR),
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [
                ("type", wintypes.DWORD),
                ("ki", KEYBDINPUT),
            ]

        input_struct = INPUT()
        input_struct.type = 1  # INPUT_KEYBOARD
        input_struct.ki.wVk = 0
        input_struct.ki.wScan = ord(char)
        input_struct.ki.dwFlags = flags | 0x0004  # KEYEVENTF_UNICODE
        input_struct.ki.time = 0
        input_struct.ki.dwExtraInfo = 0
        return input_struct

    def _make_keyboard_input_vk(self, vk: int, flags: int):
        """Create keyboard input structure for virtual key."""
        from ctypes import wintypes

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", wintypes.WORD),
                ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD),
                ("dwExtraInfo", wintypes.ULONG_PTR),
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [
                ("type", wintypes.DWORD),
                ("ki", KEYBDINPUT),
            ]

        input_struct = INPUT()
        input_struct.type = 1  # INPUT_KEYBOARD
        input_struct.ki.wVk = vk
        input_struct.ki.wScan = 0
        input_struct.ki.dwFlags = flags
        input_struct.ki.time = 0
        input_struct.ki.dwExtraInfo = 0
        return input_struct

    def _save_bitmap(self, hbitmap, hdc, width, height, filepath):
        """Save bitmap to file."""
        import struct

        # Get bitmap info
        bmi = ctypes.create_string_buffer(40)
        ctypes.windll.gdi32.GetDIBits(hdc, hbitmap, 0, 0, None, ctypes.byref(ctypes.c_void_p.from_buffer(bmi)), 0)

        # Create bitmap file header
        bmfh = struct.pack('<2sIHHI', b'BM', 54 + width * height * 4, 0, 0, 54)

        # Get bitmap bits
        bits = ctypes.create_string_buffer(width * height * 4)
        ctypes.windll.gdi32.GetDIBits(hdc, hbitmap, 0, height, bits, ctypes.byref(ctypes.c_void_p.from_buffer(bmi)), 0)

        with open(filepath, 'wb') as f:
            f.write(bmfh)
            f.write(bmi)
            f.write(bits)


def main():
    """Entry point for running the server."""
    import asyncio
    server = UIAutomationMCPServer()
    asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()
