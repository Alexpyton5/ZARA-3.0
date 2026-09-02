"""Advanced, closed Windows actions with honest post-condition reporting."""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import json
import re
import subprocess
import time
from typing import Any

from core.action_registry import ActionResult, action

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_PS = ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command"]


def _run(argv: list[str], timeout: float = 20.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_CREATE_NO_WINDOW,
        check=False,
    )


def _failure(message: str, proc: subprocess.CompletedProcess[str] | None = None) -> ActionResult:
    detail = ""
    if proc is not None:
        detail = (proc.stderr or proc.stdout or "").strip()
    return ActionResult(success=False, error=f"{message}{': ' + detail if detail else ''}")


def _powershell_json(script: str, timeout: float = 20.0) -> tuple[Any | None, str | None]:
    proc = _run([*_PS, "$ErrorActionPreference='Stop'; " + script], timeout)
    if proc.returncode != 0:
        return None, (proc.stderr or proc.stdout or "PowerShell falhou").strip()
    raw = proc.stdout.strip()
    if not raw:
        return [], None
    try:
        return json.loads(raw), None
    except json.JSONDecodeError:
        return None, "O Windows devolveu dados em formato inesperado."


def _ps_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _json_result(data: Any, label: str) -> ActionResult:
    if isinstance(data, dict):
        data = [data]
    count = len(data) if isinstance(data, list) else 1
    return ActionResult(success=True, output=f"{label}: {count}", data=data)


@action(name="os_service_list", category="system", description="Lista servicos do Windows")
def os_service_list_action() -> ActionResult:
    data, error = _powershell_json(
        "Get-Service | Sort-Object DisplayName | Select-Object Name,DisplayName,Status,StartType | ConvertTo-Json -Compress"
    )
    return _failure("Nao consegui listar os servicos", None) if error else _json_result(data or [], "Servicos encontrados")


def _service_state(name: str) -> str | None:
    data, error = _powershell_json(
        f"Get-Service -Name {_ps_quote(name)} | Select-Object -ExpandProperty Status | ConvertTo-Json -Compress"
    )
    return None if error else str(data)


@action(name="os_service_start", category="system", risk="HIGH", capability="LOCAL_PC_CONTROL", description="Inicia um servico do Windows")
def os_service_start_action(name: str) -> ActionResult:
    proc = _run([*_PS, f"$ErrorActionPreference='Stop'; Start-Service -Name {_ps_quote(name)}"])
    if proc.returncode != 0:
        return _failure("Nao consegui iniciar o servico", proc)
    state = _service_state(name)
    if state != "Running":
        return _failure(f"O servico nao ficou em execucao (estado observado: {state or 'desconhecido'})")
    return ActionResult(True, f"Servico {name} iniciado e verificado.", data={"name": name, "status": state})


@action(name="os_service_stop", category="system", risk="HIGH", capability="LOCAL_PC_CONTROL", description="Para um servico do Windows")
def os_service_stop_action(name: str) -> ActionResult:
    proc = _run([*_PS, f"$ErrorActionPreference='Stop'; Stop-Service -Name {_ps_quote(name)}"])
    if proc.returncode != 0:
        return _failure("Nao consegui parar o servico", proc)
    state = _service_state(name)
    if state != "Stopped":
        return _failure(f"O servico nao ficou parado (estado observado: {state or 'desconhecido'})")
    return ActionResult(True, f"Servico {name} parado e verificado.", data={"name": name, "status": state})


@action(name="os_task_list", category="system", description="Lista tarefas agendadas do Windows")
def os_task_list_action() -> ActionResult:
    data, error = _powershell_json(
        "Get-ScheduledTask | Sort-Object TaskPath,TaskName | Select-Object TaskName,TaskPath,State | ConvertTo-Json -Compress"
    )
    return _failure(f"Nao consegui listar as tarefas: {error}") if error else _json_result(data or [], "Tarefas encontradas")


def _task_exists(name: str) -> bool:
    return _run(["schtasks.exe", "/Query", "/TN", name]).returncode == 0


@action(name="os_task_run", category="system", risk="MEDIUM", capability="LOCAL_PC_CONTROL", description="Executa uma tarefa agendada existente")
def os_task_run_action(name: str) -> ActionResult:
    if not _task_exists(name):
        return _failure(f"A tarefa agendada {name!r} nao existe")
    proc = _run(["schtasks.exe", "/Run", "/TN", name])
    if proc.returncode != 0:
        return _failure("Nao consegui solicitar a execucao da tarefa", proc)
    return ActionResult(True, f"Execucao da tarefa {name} solicitada; o resultado interno da tarefa nao pode ser confirmado.", verificado=False)


@action(name="os_task_create", category="system", risk="HIGH", capability="LOCAL_PC_CONTROL", description="Cria uma tarefa agendada fechada")
def os_task_create_action(name: str, command: str, trigger: str = "ONCE", start_time: str = "23:59") -> ActionResult:
    schedule = str(trigger).strip().upper()
    if schedule not in {"ONCE", "DAILY", "WEEKLY", "ONLOGON", "ONSTART"}:
        return _failure("Gatilho invalido; use ONCE, DAILY, WEEKLY, ONLOGON ou ONSTART")
    argv = ["schtasks.exe", "/Create", "/TN", name, "/TR", command, "/SC", schedule, "/F"]
    if schedule in {"ONCE", "DAILY", "WEEKLY"}:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", start_time):
            return _failure("Horario invalido; use HH:MM no formato de 24 horas")
        argv.extend(["/ST", start_time])
    proc = _run(argv)
    if proc.returncode != 0:
        return _failure("Nao consegui criar a tarefa", proc)
    if not _task_exists(name):
        return _failure("O Windows nao confirmou a tarefa depois da criacao")
    return ActionResult(True, f"Tarefa {name} criada e verificada.", data={"name": name, "trigger": schedule})


def _power_plans() -> tuple[list[dict[str, Any]], str | None]:
    proc = _run(["powercfg.exe", "/LIST"])
    if proc.returncode != 0:
        return [], (proc.stderr or proc.stdout).strip()
    plans = []
    for line in proc.stdout.splitlines():
        match = re.search(r"([0-9a-fA-F-]{36})\s+\((.+?)\)\s*(\*)?", line)
        if match:
            plans.append({"guid": match.group(1).lower(), "name": match.group(2), "active": bool(match.group(3))})
    return plans, None


@action(name="os_power_plan_list", category="system", description="Lista planos de energia")
def os_power_plan_list_action() -> ActionResult:
    plans, error = _power_plans()
    return _failure(f"Nao consegui listar planos de energia: {error}") if error else _json_result(plans, "Planos encontrados")


@action(name="os_power_plan_set", category="system", risk="MEDIUM", capability="LOCAL_PC_CONTROL", description="Ativa um plano de energia")
def os_power_plan_set_action(name: str) -> ActionResult:
    plans, error = _power_plans()
    if error:
        return _failure(f"Nao consegui consultar os planos: {error}")
    target = next((p for p in plans if p["guid"] == name.lower() or p["name"].casefold() == name.casefold()), None)
    if target is None:
        return _failure(f"Plano de energia {name!r} nao encontrado")
    proc = _run(["powercfg.exe", "/SETACTIVE", target["guid"]])
    if proc.returncode != 0:
        return _failure("Nao consegui ativar o plano", proc)
    current, _ = _power_plans()
    if not any(p["guid"] == target["guid"] and p["active"] for p in current):
        return _failure("O Windows nao confirmou o plano como ativo")
    return ActionResult(True, f"Plano {target['name']} ativado e verificado.", data=target)


@action(name="os_sleep", category="system", risk="HIGH", capability="SYSTEM_POWER", description="Suspende ou hiberna o computador")
def os_sleep_action(mode: str = "sleep") -> ActionResult:
    normalized = str(mode).strip().lower()
    if normalized not in {"sleep", "hibernate"}:
        return _failure("Modo invalido; use sleep ou hibernate")
    if normalized == "hibernate":
        proc = _run(["shutdown.exe", "/h"], timeout=5)
    else:
        proc = _run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], timeout=5)
    if proc.returncode != 0:
        return _failure("O Windows recusou a solicitacao de energia", proc)
    return ActionResult(True, f"Solicitacao de {normalized} enviada; a suspensao nao pode ser observada por este processo.", verificado=False)


@action(name="os_network_adapters", category="system", description="Lista adaptadores de rede")
def os_network_adapters_action() -> ActionResult:
    data, error = _powershell_json(
        "Get-NetAdapter | Sort-Object Name | Select-Object Name,InterfaceDescription,Status,LinkSpeed,MacAddress | ConvertTo-Json -Compress"
    )
    return _failure(f"Nao consegui listar adaptadores: {error}") if error else _json_result(data or [], "Adaptadores encontrados")


def _netsh_profiles() -> tuple[list[str], str | None]:
    proc = _run(["netsh.exe", "wlan", "show", "profiles"])
    if proc.returncode != 0:
        return [], (proc.stderr or proc.stdout).strip()
    profiles = []
    for line in proc.stdout.splitlines():
        if ":" in line and re.search(r"profile|perfil", line, re.I):
            value = line.split(":", 1)[1].strip()
            if value:
                profiles.append(value)
    return sorted(set(profiles)), None


@action(name="os_wifi_profiles", category="system", description="Lista perfis Wi-Fi salvos")
def os_wifi_profiles_action() -> ActionResult:
    profiles, error = _netsh_profiles()
    return _failure(f"Nao consegui listar perfis Wi-Fi: {error}") if error else _json_result(profiles, "Perfis encontrados")


@action(name="os_wifi_connect", category="system", risk="MEDIUM", capability="LOCAL_PC_CONTROL", description="Conecta a um perfil Wi-Fi salvo")
def os_wifi_connect_action(profile: str) -> ActionResult:
    profiles, error = _netsh_profiles()
    if error or profile.casefold() not in {p.casefold() for p in profiles}:
        return _failure(f"Perfil Wi-Fi {profile!r} nao encontrado")
    proc = _run(["netsh.exe", "wlan", "connect", f"name={profile}"])
    if proc.returncode != 0:
        return _failure("Nao consegui conectar ao Wi-Fi", proc)
    time.sleep(1.0)
    state = _run(["netsh.exe", "wlan", "show", "interfaces"])
    observed = state.stdout.casefold()
    if profile.casefold() not in observed or not re.search(r"(?:state|estado)\s*:\s*(?:connected|conectado)", observed):
        return _failure("A conexao foi solicitada, mas o Windows nao confirmou esse perfil como conectado")
    return ActionResult(True, f"Wi-Fi {profile} conectado e verificado.")


@action(name="os_hotspot_toggle", category="system", risk="MEDIUM", capability="LOCAL_PC_CONTROL", description="Liga ou desliga o hotspot hospedado")
def os_hotspot_toggle_action(enabled: bool) -> ActionResult:
    if isinstance(enabled, str):
        normalized_enabled = enabled.strip().lower()
        if normalized_enabled not in {"on", "off", "true", "false", "1", "0"}:
            return _failure("Estado invalido para o hotspot; use on ou off")
        enabled = normalized_enabled in {"on", "true", "1"}
    verb = "start" if bool(enabled) else "stop"
    proc = _run(["netsh.exe", "wlan", verb, "hostednetwork"])
    if proc.returncode != 0:
        return _failure("Este Windows nao conseguiu alterar o hotspot", proc)
    state = _run(["netsh.exe", "wlan", "show", "hostednetwork"])
    active = bool(re.search(r"(?:status|estado)\s*:\s*(?:started|iniciado)", state.stdout, re.I))
    if active != bool(enabled):
        return _failure("O Windows nao confirmou o estado solicitado para o hotspot")
    return ActionResult(True, f"Hotspot {'ligado' if enabled else 'desligado'} e verificado.")


@action(name="os_vpn_list", category="system", description="Lista conexoes VPN configuradas")
def os_vpn_list_action() -> ActionResult:
    data, error = _powershell_json(
        "Get-VpnConnection -AllUserConnection:$false | Select-Object Name,ServerAddress,TunnelType,ConnectionStatus | ConvertTo-Json -Compress"
    )
    return _failure(f"Nao consegui listar VPNs: {error}") if error else _json_result(data or [], "VPNs encontradas")


@action(name="os_vpn_connect", category="system", risk="MEDIUM", capability="LOCAL_PC_CONTROL", description="Conecta uma VPN configurada")
def os_vpn_connect_action(name: str) -> ActionResult:
    proc = _run(["rasdial.exe", name])
    if proc.returncode != 0:
        return _failure("Nao consegui conectar a VPN", proc)
    data, error = _powershell_json(
        f"Get-VpnConnection -Name {_ps_quote(name)} | Select-Object -ExpandProperty ConnectionStatus | ConvertTo-Json -Compress"
    )
    if error or str(data).lower() != "connected":
        return _failure("A VPN foi acionada, mas nao ficou conectada")
    return ActionResult(True, f"VPN {name} conectada e verificada.")


@action(name="os_clipboard_history", category="system", description="Consulta o historico da area de transferencia")
def os_clipboard_history_action() -> ActionResult:
    return _failure("O Windows nao expoe o historico da area de transferencia a este processo de forma confiavel")


@action(name="os_clipboard_pin", category="system", risk="MEDIUM", capability="LOCAL_PC_CONTROL", description="Fixa item no historico da area de transferencia")
def os_clipboard_pin_action(item: str) -> ActionResult:
    del item
    return _failure("Fixar itens no historico da area de transferencia nao esta disponivel pela API local instalada")


def _recycle_items() -> tuple[list[dict[str, str]], str | None]:
    script = (
        "$s=New-Object -ComObject Shell.Application; $b=$s.Namespace(10); "
        "@($b.Items() | ForEach-Object {[pscustomobject]@{Name=$_.Name;Path=$_.Path}}) | ConvertTo-Json -Compress"
    )
    data, error = _powershell_json(script)
    if error:
        return [], error
    if isinstance(data, dict):
        data = [data]
    return list(data or []), None


@action(name="os_recycle_bin_list", category="system", description="Lista itens da Lixeira")
def os_recycle_bin_list_action() -> ActionResult:
    items, error = _recycle_items()
    return _failure(f"Nao consegui ler a Lixeira: {error}") if error else _json_result(items, "Itens na Lixeira")


@action(name="os_recycle_bin_restore", category="system", risk="MEDIUM", capability="LOCAL_PC_CONTROL", description="Restaura um item da Lixeira")
def os_recycle_bin_restore_action(name: str) -> ActionResult:
    before, error = _recycle_items()
    if error:
        return _failure(f"Nao consegui ler a Lixeira: {error}")
    matches = [x for x in before if str(x.get("Name", "")).casefold() == name.casefold()]
    if len(matches) != 1:
        return _failure("Informe um nome que identifique exatamente um item da Lixeira")
    script = (
        "$s=New-Object -ComObject Shell.Application; $b=$s.Namespace(10); "
        f"$i=@($b.Items() | Where-Object {{$_.Name -eq {_ps_quote(matches[0]['Name'])}}}); "
        "if($i.Count -ne 1){throw 'item ambiguo'}; $i[0].InvokeVerb('RESTORE')"
    )
    proc = _run([*_PS, "$ErrorActionPreference='Stop'; " + script])
    if proc.returncode != 0:
        return _failure("Nao consegui restaurar o item", proc)
    time.sleep(0.5)
    after, _ = _recycle_items()
    if any(str(x.get("Path")) == str(matches[0].get("Path")) for x in after):
        return _failure("O item ainda aparece na Lixeira depois da restauracao")
    return ActionResult(True, f"{name} restaurado e verificado.", data=matches[0])


@action(name="os_recycle_bin_empty", category="system", risk="HIGH", capability="FILES_MUTATE", description="Esvazia a Lixeira")
def os_recycle_bin_empty_action() -> ActionResult:
    flags = 0x1 | 0x2 | 0x4
    code = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
    if code != 0:
        return _failure(f"O Windows recusou esvaziar a Lixeira (codigo {code})")
    items, error = _recycle_items()
    if error or items:
        return _failure("Nao foi possivel confirmar que a Lixeira ficou vazia")
    return ActionResult(True, "Lixeira esvaziada e verificada.")


def _send_hotkey(*keys: int) -> None:
    for key in keys:
        ctypes.windll.user32.keybd_event(key, 0, 0, 0)
    for key in reversed(keys):
        ctypes.windll.user32.keybd_event(key, 0, 2, 0)


def _foreground_rect() -> tuple[int, int, int, int] | None:
    hwnd = ctypes.windll.user32.GetForegroundWindow()
    rect = ctypes.wintypes.RECT()
    if not hwnd or not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return rect.left, rect.top, rect.right, rect.bottom


@action(name="window_snap", category="window", capability="LOCAL_PC_CONTROL", description="Encaixa a janela ativa")
def window_snap_action(side: str) -> ActionResult:
    keys = {"left": 0x25, "right": 0x27, "up": 0x26, "down": 0x28}
    normalized = str(side).strip().lower()
    if normalized not in keys:
        return _failure("Lado invalido; use left, right, up ou down")
    before = _foreground_rect()
    _send_hotkey(0x5B, keys[normalized])
    time.sleep(0.25)
    after = _foreground_rect()
    if before is None or after is None or before == after:
        return _failure("O Windows nao confirmou mudanca na geometria da janela")
    return ActionResult(True, f"Janela encaixada em {normalized} e verificada.", data={"before": before, "after": after})


@action(name="window_virtual_desktop_create", category="window", capability="LOCAL_PC_CONTROL", description="Cria um desktop virtual")
def window_virtual_desktop_create_action() -> ActionResult:
    _send_hotkey(0x5B, 0x11, 0x44)
    return ActionResult(True, "Atalho para criar desktop virtual enviado; o Windows nao oferece confirmacao estavel aqui.", verificado=False)


@action(name="window_virtual_desktop_switch", category="window", capability="LOCAL_PC_CONTROL", description="Troca para desktop virtual adjacente")
def window_virtual_desktop_switch_action(direction: str = "right", index: int | None = None) -> ActionResult:
    if index is not None:
        index = int(index)
        if index < 1 or index > 20:
            return _failure("Indice do desktop deve estar entre 1 e 20")
        for _ in range(20):
            _send_hotkey(0x5B, 0x11, 0x25)
        for _ in range(index - 1):
            _send_hotkey(0x5B, 0x11, 0x27)
        return ActionResult(True, f"Atalhos enviados para o desktop {index}; a troca nao pode ser confirmada por esta API.", verificado=False)
    normalized = str(direction).strip().lower()
    key = {"left": 0x25, "previous": 0x25, "right": 0x27, "next": 0x27}.get(normalized)
    if key is None:
        return _failure("Direcao invalida; use left/right ou previous/next")
    _send_hotkey(0x5B, 0x11, key)
    return ActionResult(True, "Atalho de troca de desktop enviado; a troca nao pode ser confirmada por esta API.", verificado=False)


@action(name="window_virtual_desktop_move", category="window", capability="LOCAL_PC_CONTROL", description="Move a janela ao desktop virtual adjacente")
def window_virtual_desktop_move_action(direction: str = "right", desktop_id: int | None = None) -> ActionResult:
    if desktop_id is not None:
        desktop_id = int(desktop_id)
        if desktop_id < 1 or desktop_id > 20:
            return _failure("Indice do desktop deve estar entre 1 e 20")
        for _ in range(20):
            _send_hotkey(0x5B, 0x11, 0x10, 0x25)
        for _ in range(desktop_id - 1):
            _send_hotkey(0x5B, 0x11, 0x10, 0x27)
        return ActionResult(True, f"Atalhos enviados para mover ao desktop {desktop_id}; o destino nao pode ser confirmado.", verificado=False)
    normalized = str(direction).strip().lower()
    key = {"left": 0x25, "previous": 0x25, "right": 0x27, "next": 0x27}.get(normalized)
    if key is None:
        return _failure("Direcao invalida; use left/right ou previous/next")
    _send_hotkey(0x5B, 0x11, 0x10, key)
    return ActionResult(True, "Atalho para mover a janela enviado; o destino nao pode ser confirmado por esta API.", verificado=False)


@action(name="window_minimize_all", category="window", capability="LOCAL_PC_CONTROL", description="Minimiza todas as janelas")
def window_minimize_all_action() -> ActionResult:
    _send_hotkey(0x5B, 0x4D)
    return ActionResult(True, "Comando para minimizar todas as janelas enviado; estado global nao verificavel.", verificado=False)


@action(name="window_show_desktop", category="window", capability="LOCAL_PC_CONTROL", description="Mostra a area de trabalho")
def window_show_desktop_action() -> ActionResult:
    _send_hotkey(0x5B, 0x44)
    return ActionResult(True, "Comando para mostrar a area de trabalho enviado; estado global nao verificavel.", verificado=False)
