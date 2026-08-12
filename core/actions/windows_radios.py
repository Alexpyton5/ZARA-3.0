"""Silent Windows Wi-Fi/Bluetooth control through the official WinRT Radio API."""
from __future__ import annotations

import json
import platform
import subprocess
from typing import Any

from core.action_registry import ActionResult, action


_RADIO_KINDS = {"wifi": "WiFi", "bluetooth": "Bluetooth"}
_RADIO_STATES = {True: "On", False: "Off"}

_RADIO_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[void][Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime]
[void][Windows.Devices.Radios.RadioAccessStatus,Windows.System.Devices,ContentType=WindowsRuntime]
[void][Windows.Devices.Radios.RadioState,Windows.System.Devices,ContentType=WindowsRuntime]
$asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 } |
    Select-Object -First 1
function Await-WinRt($operation, $resultType) {
    $task = $asTask.MakeGenericMethod($resultType).Invoke($null, @($operation))
    $task.Wait()
    return $task.Result
}
function Emit($value) {
    Write-Output ($value | ConvertTo-Json -Compress)
}
$access = Await-WinRt ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus])
if ($access -ne [Windows.Devices.Radios.RadioAccessStatus]::Allowed) {
    Emit @{ success = $false; status = 'ACCESS_DENIED'; access = $access.ToString() }
    exit 0
}
$listType = [System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]]
$radios = Await-WinRt ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) $listType
$radio = $radios | Where-Object { $_.Kind.ToString() -eq '__KIND__' } | Select-Object -First 1
if ($null -eq $radio) {
    Emit @{ success = $false; status = 'UNSUPPORTED'; kind = '__KIND__' }
    exit 0
}
$before = $radio.State.ToString()
$desiredName = '__DESIRED__'
if ($desiredName -eq '') {
    Emit @{ success = $true; status = 'AVAILABLE'; kind = '__KIND__'; before = $before; after = $before; changed = $false }
    exit 0
}
if ($before -eq $desiredName) {
    Emit @{ success = $true; status = 'AVAILABLE'; kind = '__KIND__'; before = $before; after = $before; changed = $false }
    exit 0
}
$desiredState = [System.Enum]::Parse([Windows.Devices.Radios.RadioState], $desiredName)
$setResult = Await-WinRt ($radio.SetStateAsync($desiredState)) ([Windows.Devices.Radios.RadioAccessStatus])
if ($setResult -ne [Windows.Devices.Radios.RadioAccessStatus]::Allowed) {
    Emit @{ success = $false; status = 'CHANGE_DENIED'; kind = '__KIND__'; before = $before; after = $radio.State.ToString() }
    exit 0
}
$deadline = [DateTime]::UtcNow.AddSeconds(5)
do {
    Start-Sleep -Milliseconds 100
    $after = $radio.State.ToString()
} while ($after -ne $desiredName -and [DateTime]::UtcNow -lt $deadline)
$ok = $after -eq $desiredName
Emit @{ success = $ok; status = $(if ($ok) { 'AVAILABLE' } else { 'POSTCONDITION_FAILED' }); kind = '__KIND__'; before = $before; after = $after; changed = $ok }
"""


def _run_radio_command(kind: str, desired: bool | None = None) -> dict[str, Any]:
    if platform.system() != "Windows":
        return {"success": False, "status": "UNSUPPORTED", "kind": kind}
    winrt_kind = _RADIO_KINDS.get(str(kind).casefold())
    if winrt_kind is None:
        return {"success": False, "status": "INVALID_KIND", "kind": kind}
    desired_name = "" if desired is None else _RADIO_STATES[bool(desired)]
    script = _RADIO_SCRIPT.replace("__KIND__", winrt_kind).replace("__DESIRED__", desired_name)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            creationflags=creationflags,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"success": False, "status": "RUNTIME_ERROR", "error": type(exc).__name__}
    if completed.returncode != 0:
        return {"success": False, "status": "RUNTIME_ERROR", "error": "PowerShell failed"}
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    try:
        result = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        return {"success": False, "status": "INVALID_RESPONSE"}
    return result if isinstance(result, dict) else {"success": False, "status": "INVALID_RESPONSE"}


def _radio_result(label: str, desired: bool) -> ActionResult:
    observed = _run_radio_command(label.casefold(), desired)
    if not observed.get("success"):
        return ActionResult(
            success=False,
            error=f"{label} indisponível: {observed.get('status', 'UNKNOWN')}",
            data=observed,
        )
    state = "ligado" if observed.get("after") == "On" else "desligado"
    verb = "permaneceu" if not observed.get("changed") else "ficou"
    return ActionResult(
        success=True,
        output=f"{label} {verb} {state}. Estado confirmado.",
        data=observed,
    )


@action(name="os_wifi_status", category="os", description="Read Wi-Fi radio state silently")
def os_wifi_status_action() -> ActionResult:
    observed = _run_radio_command("wifi")
    if not observed.get("success"):
        return ActionResult(success=False, error=f"Wi-Fi indisponível: {observed.get('status')}", data=observed)
    return ActionResult(success=True, output=f"Wi-Fi: {observed.get('after')}.", data=observed)


@action(name="os_wifi_on", category="os", description="Enable Wi-Fi silently with readback", capability="LOCAL_PC_CONTROL")
def os_wifi_on_action() -> ActionResult:
    return _radio_result("WiFi", True)


@action(name="os_wifi_off", category="os", description="Disable Wi-Fi silently with readback", capability="LOCAL_PC_CONTROL")
def os_wifi_off_action() -> ActionResult:
    return _radio_result("WiFi", False)


@action(name="os_bluetooth_status", category="os", description="Read Bluetooth radio state silently")
def os_bluetooth_status_action() -> ActionResult:
    observed = _run_radio_command("bluetooth")
    if not observed.get("success"):
        return ActionResult(success=False, error=f"Bluetooth indisponível: {observed.get('status')}", data=observed)
    return ActionResult(success=True, output=f"Bluetooth: {observed.get('after')}.", data=observed)


@action(name="os_bluetooth_on", category="os", description="Enable Bluetooth silently with readback", capability="LOCAL_PC_CONTROL")
def os_bluetooth_on_action() -> ActionResult:
    return _radio_result("Bluetooth", True)


@action(name="os_bluetooth_off", category="os", description="Disable Bluetooth silently with readback", capability="LOCAL_PC_CONTROL")
def os_bluetooth_off_action() -> ActionResult:
    return _radio_result("Bluetooth", False)
