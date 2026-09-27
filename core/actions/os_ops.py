from __future__ import annotations

import platform
import subprocess

from core.action_registry import ActionResult, action


@action(name="os_volume", category="os", description="Get or set system volume", capability="PC_CONTROL")
def os_volume_action(level: int = None, mute: bool = None) -> ActionResult:
    """Get or set system volume."""
    try:
        system = platform.system()

        if system == "Windows":
            # Use nircmd or Windows API
            if level is not None:
                # Use nircmd if available, otherwise use Windows API
                try:
                    subprocess.run(["nircmd.exe", "setsysvolume", str(int(level * 65535 / 100))], check=True, capture_output=True)
                except FileNotFoundError:
                    # Use pycaw if available
                    try:
                        from comtypes import CLSCTX_ALL, CoInitialize, CoUninitialize
                        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                        CoInitialize()
                        try:
                            devices = AudioUtilities.GetSpeakers()
                            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                            volume = interface.QueryInterface(IAudioEndpointVolume)
                            volume.SetMasterVolumeLevelScalar(level / 100, None)
                        finally:
                            CoUninitialize()
                    except ImportError:
                        return ActionResult(success=False, error="pycaw or nircmd required for volume control")

            if mute is not None:
                try:
                    subprocess.run(["nircmd.exe", "mutesysvolume", "1" if mute else "0"], check=True, capture_output=True)
                except FileNotFoundError:
                    # Use pycaw if available
                    try:
                        from comtypes import CLSCTX_ALL, CoInitialize, CoUninitialize
                        from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
                        CoInitialize()
                        try:
                            devices = AudioUtilities.GetSpeakers()
                            interface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
                            volume = interface.QueryInterface(IAudioEndpointVolume)
                            volume.SetMute(mute, None)
                        finally:
                            CoUninitialize()
                    except ImportError:
                        return ActionResult(success=False, error="pycaw or nircmd required for mute control")

        elif system == "Linux":
            # Use pactl or amixer
            if level is not None:
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"], check=True)
            if mute is not None:
                subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1" if mute else "0"], check=True)

        elif system == "Darwin":
            # Use osascript
            if level is not None:
                subprocess.run(["osascript", "-e", f"set volume output volume {level}"], check=True)
            if mute is not None:
                subprocess.run(["osascript", "-e", f"set volume output muted {str(mute).lower()}"], check=True)

        return ActionResult(success=True, output="Volume adjusted")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(name="os_brightness", category="os", description="Get or set screen brightness", capability="PC_CONTROL")
def os_brightness_action(level: int = None) -> ActionResult:
    """Get or set screen brightness (Windows only)."""
    try:
        system = platform.system()
        if system != "Windows":
            return ActionResult(success=False, error="Brightness control only implemented for Windows")

        if level is None:
            return ActionResult(success=False, error="Level required")

        # Use WMI to set brightness
        try:
            import wmi
            w = wmi.WMI(namespace="wmi")
            for monitor in w.WmiMonitorBrightnessMethods():
                monitor.WmiSetBrightness(level, 0)
            return ActionResult(success=True, output=f"Brightness set to {level}%")
        except ImportError:
            return ActionResult(success=False, error="wmi module required for brightness control")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(name="os_power", category="os", description="Power management: shutdown, restart, sleep, hibernate", risk="HIGH", capability="SYSTEM_POWER")
def os_power_action(action_type: str) -> ActionResult:
    """Power management actions."""
    try:
        system = platform.system()
        action_type = action_type.lower()

        if action_type in ("shutdown", "poweroff"):
            if system == "Windows":
                subprocess.run(["shutdown", "/s", "/t", "0"], check=True)
            elif system == "Linux":
                subprocess.run(["systemctl", "poweroff"], check=True)
            elif system == "Darwin":
                subprocess.run(["osascript", "-e", "tell app \"System Events\" to shut down"], check=True)
        elif action_type in ("restart", "reboot"):
            if system == "Windows":
                subprocess.run(["shutdown", "/r", "/t", "0"], check=True)
            elif system == "Linux":
                subprocess.run(["systemctl", "reboot"], check=True)
            elif system == "Darwin":
                subprocess.run(["osascript", "-e", "tell app \"System Events\" to restart"], check=True)
        elif action_type in ("sleep", "suspend"):
            if system == "Windows":
                subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], check=True)
            elif system == "Linux":
                subprocess.run(["systemctl", "suspend"], check=True)
            elif system == "Darwin":
                subprocess.run(["osascript", "-e", "tell app \"System Events\" to sleep"], check=True)
        elif action_type in ("hibernate",):
            if system == "Windows":
                subprocess.run(["shutdown", "/h"], check=True)
            elif system == "Linux":
                subprocess.run(["systemctl", "hibernate"], check=True)
            else:
                return ActionResult(success=False, error="Hibernate not supported on this OS")
        else:
            return ActionResult(success=False, error=f"Unknown power action: {action_type}")

        return ActionResult(success=True, output=f"Power action '{action_type}' initiated")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(name="os_clipboard", category="os", description="Get or set clipboard content", risk="MEDIUM", capability="PC_CONTROL")
def os_clipboard_action(text: str = None, get: bool = False) -> ActionResult:
    """Get or set clipboard content."""
    try:
        import pyperclip

        if get:
            content = pyperclip.paste()
            return ActionResult(success=True, output=content, data={"clipboard": content})

        if text is not None:
            pyperclip.copy(text)
            return ActionResult(success=True, output="Copied to clipboard")

        return ActionResult(success=False, error="Either 'text' or 'get=true' required")
    except ImportError:
        return ActionResult(success=False, error="pyperclip not installed")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(name="os_notify", category="os", description="Show system notification")
def os_notify_action(title: str, message: str = "", timeout: int = 5) -> ActionResult:
    """Show system notification."""
    try:
        system = platform.system()

        if system == "Windows":
            try:
                import win10toast
                toaster = win10toast.ToastNotifier()
                toaster.show_toast(title, message, duration=timeout)
                return ActionResult(success=True, output="Notification sent")
            except ImportError:
                # Fallback to PowerShell
                ps_script = f"""
                Add-Type -AssemblyName System.Windows.Forms
                $notify = New-Object System.Windows.Forms.NotifyIcon
                $notify.Icon = [System.Drawing.SystemIcons]::Information
                $notify.Visible = $true
                $notify.ShowBalloonTip({timeout * 1000}, "{title}", "{message}", [System.Windows.Forms.ToolTipIcon]::Info)
                """
                subprocess.run(["powershell", "-Command", ps_script], check=True)
                return ActionResult(success=True, output="Notification sent (PowerShell fallback)")

        elif system == "Linux":
            subprocess.run(["notify-send", "-t", str(timeout * 1000), title, message], check=True)
            return ActionResult(success=True, output="Notification sent")

        elif system == "Darwin":
            script = f'display notification "{message}" with title "{title}"'
            subprocess.run(["osascript", "-e", script], check=True)
            return ActionResult(success=True, output="Notification sent")

        return ActionResult(success=False, error="Notifications not supported on this OS")
    except Exception as e:
        return ActionResult(success=False, error=str(e))
