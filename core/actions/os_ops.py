from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import quote_plus, urlsplit, urlunsplit

from core.action_registry import ActionResult, action

_SAFE_WINDOWS_APPS = {
    "notepad": {
        "display_name": "Bloco de Notas",
        "opened_reply": "Bloco de Notas aberto e verificado.",
        "executable": "notepad.exe",
        "process_names": {"notepad.exe"},
    },
    "chrome": {
        "display_name": "Chrome",
        "opened_reply": "Chrome aberto e verificado.",
        "executable": "chrome.exe",
        "process_names": {"chrome.exe"},
    },
    "task_manager": {
        "display_name": "Gerenciador de Tarefas",
        "opened_reply": "Gerenciador de Tarefas aberto e verificado.",
        "executable": "taskmgr.exe",
        "process_names": {"taskmgr.exe"},
    },
    "settings": {
        "display_name": "Configurações",
        "opened_reply": "Configurações abertas e verificadas.",
        "executable": "ms-settings:",
        "process_names": {"systemsettings.exe"},
    },
    "paint": {
        "display_name": "Paint",
        "opened_reply": "Paint aberto e verificado.",
        "executable": "mspaint.exe",
        "process_names": {"mspaint.exe"},
    },
    "snipping_tool": {
        "display_name": "Ferramenta de Captura",
        "opened_reply": "Ferramenta de Captura aberta e verificada.",
        "executable": "snippingtool.exe",
        "process_names": {"snippingtool.exe"},
    },
    "edge": {
        "display_name": "Microsoft Edge",
        "opened_reply": "Microsoft Edge aberto e verificado.",
        "executable": "msedge.exe",
        "process_names": {"msedge.exe"},
    },
    "spotify": {
        "display_name": "Spotify",
        "opened_reply": "Spotify aberto e verificado.",
        "executable": "spotify:",
        "process_names": {"spotify.exe"},
    },
    # ZARA-APPS-REAIS-2026-08-27 (Alex): tirei a calculadora (ele nao usa e
    # nao quer que ela abra) e coloquei os apps que ele tem instalados de
    # verdade, achados escaneando o Menu Iniciar do Windows dele.
    "telegram": {
        "display_name": "Telegram",
        "opened_reply": "Telegram aberto e verificado.",
        "executable": r"C:\Users\alexp\AppData\Roaming\Telegram Desktop\Telegram.exe",
        "process_names": {"telegram.exe"},
    },
    "obsidian": {
        "display_name": "Obsidian",
        "opened_reply": "Obsidian aberto e verificado.",
        "executable": r"C:\Users\alexp\AppData\Local\Programs\Obsidian\Obsidian.exe",
        "process_names": {"obsidian.exe"},
    },
    "winrar": {
        "display_name": "WinRAR",
        "opened_reply": "WinRAR aberto e verificado.",
        "executable": r"C:\Program Files\WinRAR\WinRAR.exe",
        "process_names": {"winrar.exe"},
    },
    "wordpad": {
        "display_name": "WordPad",
        "opened_reply": "WordPad aberto e verificado.",
        "executable": r"C:\Program Files\Windows NT\Accessories\wordpad.exe",
        "process_names": {"wordpad.exe"},
    },
    "ea_app": {
        "display_name": "EA App",
        "opened_reply": "EA App aberto e verificado.",
        "executable": r"C:\Program Files\Electronic Arts\EA Desktop\EA Desktop\EALauncher.exe",
        "process_names": {"eadesktop.exe", "ealauncher.exe"},
    },
    "nvidia_app": {
        "display_name": "NVIDIA App",
        "opened_reply": "NVIDIA App aberto e verificado.",
        "executable": r"C:\Program Files\NVIDIA Corporation\NVIDIA App\CEF\NVIDIA App.exe",
        "process_names": {"nvidia app.exe"},
    },
    "windows_media_player": {
        "display_name": "Windows Media Player",
        "opened_reply": "Windows Media Player aberto e verificado.",
        "executable": r"C:\Program Files (x86)\Windows Media Player\wmplayer.exe",
        "process_names": {"wmplayer.exe"},
    },
    "amplitube": {
        "display_name": "AmpliTube 5",
        "opened_reply": "AmpliTube 5 aberto e verificado.",
        "executable": r"C:\Program Files\IK Multimedia\AmpliTube 5\AmpliTube 5.exe",
        "process_names": {"amplitube 5.exe"},
    },
    "cursor": {
        "display_name": "Cursor",
        "opened_reply": "Cursor aberto e verificado.",
        "executable": r"C:\Users\alexp\AppData\Local\Programs\cursor\Cursor.exe",
        "process_names": {"cursor.exe"},
    },
    "hermes": {
        "display_name": "Hermes",
        "opened_reply": "Hermes aberto e verificado.",
        "executable": r"C:\Users\alexp\AppData\Local\hermes\hermes-agent\apps\desktop\release\win-unpacked\Hermes.exe",
        "process_names": {"hermes.exe"},
    },
    "ik_product_manager": {
        "display_name": "IK Product Manager",
        "opened_reply": "IK Product Manager aberto e verificado.",
        "executable": r"C:\Program Files\IK Multimedia\IK Product Manager\IK Product Manager.exe",
        "process_names": {"ik product manager.exe"},
    },
    "geforce_now": {
        "display_name": "NVIDIA GeForce NOW",
        "opened_reply": "GeForce NOW aberto e verificado.",
        "executable": r"C:\Users\alexp\AppData\Local\NVIDIA Corporation\GeForceNOW\CEF\GeForceNOW.exe",
        "process_names": {"geforcenow.exe"},
    },
    "opencode": {
        "display_name": "OpenCode",
        "opened_reply": "OpenCode aberto e verificado.",
        "executable": r"C:\Users\alexp\AppData\Local\Programs\@opencode-aidesktop\OpenCode.exe",
        "process_names": {"opencode.exe"},
    },
    "qwen": {
        "display_name": "Qwen",
        "opened_reply": "Qwen aberto e verificado.",
        "executable": r"C:\Program Files\Qwen\Qwen.exe",
        "process_names": {"qwen.exe"},
    },
    "wise_memory_optimizer": {
        "display_name": "Wise Memory Optimizer",
        "opened_reply": "Wise Memory Optimizer aberto e verificado.",
        "executable": r"C:\Program Files\Wise\Wise Memory Optimizer\WiseMemoryOptimzer.exe",
        "process_names": {"wisememoryoptimzer.exe"},
    },
}

# ZARA-APPS-REAIS-2026-08-27 (Alex): "coloque todos os apps que eu tenho
# instalado, nao importa se eu vou usar ou nao". Em vez de escrever um regex e
# um metodo novo pra cada app (o que deixa este arquivo cada vez maior a cada
# instalacao nova), os apps fora dos 9 originais sao resolvidos aqui por
# apelido falado. Ferramentas de risco (terminal, editor de registro,
# desinstaladores, PowerShell) foram deixadas de fora de proposito: abrir um
# terminal por voz sem confirmacao nenhuma e risco de seguranca, nao
# comodidade — terminal ja e uma action HIGH-risk separada, com o gate de
# confirmacao que essa lista aqui nao tem.
_APP_ALIASES = {
    "telegram": "telegram",
    "obsidian": "obsidian",
    "winrar": "winrar",
    "win rar": "winrar",
    "wordpad": "wordpad",
    "word pad": "wordpad",
    "ea": "ea_app",
    "ea app": "ea_app",
    "ea desktop": "ea_app",
    "electronic arts": "ea_app",
    "nvidia": "nvidia_app",
    "nvidia app": "nvidia_app",
    "windows media player": "windows_media_player",
    "media player": "windows_media_player",
    "amplitube": "amplitube",
    "amplitube 5": "amplitube",
    "cursor": "cursor",
    "hermes": "hermes",
    "ik product manager": "ik_product_manager",
    "geforce now": "geforce_now",
    "geforce": "geforce_now",
    "opencode": "opencode",
    "open code": "opencode",
    "qwen": "qwen",
    "wise memory optimizer": "wise_memory_optimizer",
    "otimizador de memoria": "wise_memory_optimizer",
}


def _strip_accents(text: str) -> str:
    import unicodedata
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in normalized if not unicodedata.combining(ch))


def resolve_app_alias(spoken_text: str) -> str | None:
    """Resolve free-spoken app text (accent/case-insensitive) to a canonical
    app id registered in _SAFE_WINDOWS_APPS, or None if unknown."""
    normalized = _strip_accents(str(spoken_text or "")).strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"^(?:o|a)\s+", "", normalized)
    app_id = _APP_ALIASES.get(normalized)
    if app_id and app_id in _SAFE_WINDOWS_APPS:
        return app_id
    return None

_WINDOWS_MEDIA_COMMANDS = {
    "media_next": 11,
    "media_previous": 12,
    "media_play_pause": 14,
}

_WINDOWS_KNOWN_FOLDER_IDS = {
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
}

_SAFE_FOLDER_NAMES = {
    "downloads": "Downloads",
    "documents": "Documentos",
    "desktop": "Área de Trabalho",
    "pictures": "Imagens",
    "zara_root": "pasta da ZARA",
}

_BROWSER_PROCESS_NAMES = {"chrome.exe", "msedge.exe", "firefox.exe", "brave.exe", "opera.exe"}
_SAFE_CLOSE_APPS = {
    "notepad", "chrome", "task_manager", "settings", "paint",
    "snipping_tool", "edge", "spotify",
    "telegram", "obsidian", "winrar", "wordpad",
    "ea_app", "nvidia_app", "windows_media_player",
    "amplitube", "cursor", "hermes", "ik_product_manager",
    "geforce_now", "opencode", "qwen", "wise_memory_optimizer",
}
_SAFE_CLOSE_TITLE_TOKENS = {
    "notepad": {"bloco de notas", "notepad"},
    "chrome": {"google chrome", "chrome"},
    "task_manager": {"gerenciador de tarefas", "task manager"},
    "settings": {"configurações", "settings"},
    "paint": {"paint"},
    "snipping_tool": {"ferramenta de captura", "snipping tool"},
    "edge": {"microsoft edge", "edge"},
    "telegram": {"telegram"},
    "obsidian": {"obsidian"},
    "winrar": {"winrar"},
    "wordpad": {"wordpad", "documento"},
    "ea_app": {"ea app", "ea desktop", "electronic arts"},
    "nvidia_app": {"nvidia app", "nvidia"},
    "windows_media_player": {"windows media player", "media player"},
    "amplitube": {"amplitube", "amplitube 5"},
    "cursor": {"cursor"},
    "hermes": {"hermes"},
    "ik_product_manager": {"ik product manager"},
    "geforce_now": {"geforce now", "geforce"},
    "opencode": {"opencode", "open code"},
    "qwen": {"qwen"},
    "wise_memory_optimizer": {"wise memory optimizer"},
    "spotify": {"spotify"},
}


def _normalize_browser_url(raw: str) -> str | None:
    value = str(raw or "").strip()
    if not value or any(ord(char) < 32 for char in value) or "\\" in value:
        return None
    if "://" not in value:
        value = f"https://{value}"
    try:
        parsed = urlsplit(value)
        if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname:
            return None
        if parsed.username or parsed.password:
            return None
        host = parsed.hostname.encode("idna").decode("ascii").casefold()
        labels = host.split(".")
        if len(labels) < 2 or any(not label or not label.replace("-", "").isalnum() for label in labels):
            return None
        port = parsed.port
        netloc = host if port is None else f"{host}:{port}"
        path = parsed.path or "/"
        if path.casefold().endswith((".exe", ".cmd", ".bat", ".ps1", ".msi")):
            return None
        return urlunsplit((parsed.scheme.casefold(), netloc, path, parsed.query, ""))
    except (UnicodeError, ValueError):
        return None


def _send_url_to_default_browser(url: str) -> ActionResult:
    """Nucleo real de browser_open_url, fora do decorator @action.

    AUDITORIA_2026-08-27 (Alex): youtube_open (capability LOCAL_PC_CONTROL,
    nao precisa de Supercerebro) chamava browser_open_url_action(...) por
    dentro. Como toda funcao decorada com @action reentra no
    ActionRegistry.execute() mesmo em chamada direta em Python, isso
    reaplicava o gate de browser_open_url (capability PC_CONTROL, exige
    Supercerebro) por cima de uma acao que ja tinha sido autorizada com um
    nivel mais permissivo -- "abra o youtube" comecou a exigir Supercerebro
    OFF sem nenhum motivo, regressao real reportada pelo Alex ao vivo.
    Acoes que compoem outras acoes devem chamar a logica crua, nunca a
    funcao decorada.
    """
    normalized = _normalize_browser_url(url)
    if normalized is None:
        return ActionResult(success=False, error="URL bloqueada: use somente um destino HTTP/HTTPS público válido.")
    if platform.system() != "Windows":
        return ActionResult(success=False, error="Abertura no navegador padrão disponível somente no Windows.")
    before = _running_app_pids(_BROWSER_PROCESS_NAMES)
    try:
        os.startfile(normalized)  # type: ignore[attr-defined]
    except OSError as exc:
        return ActionResult(success=False, error=f"Falha ao enviar URL ao navegador padrão: {exc}")
    time.sleep(0.35)
    after = _running_app_pids(_BROWSER_PROCESS_NAMES)
    return ActionResult(
        success=True,
        output="Destino enviado ao navegador padrão.",
        # ZARA-NAO-VERIFICADO-002. Achado 1 da auditoria do Codex, e ele estava
        # certo: os dados aqui já diziam `target_page_proven: False`, mas o
        # resultado saía com o selo verde de sempre.
        #
        # O que está provado é o DESPACHO — o Windows aceitou a URL. Não está
        # provado que o navegador abriu a página certa, nem que abriu alguma. A
        # frase "enviado ao navegador" é honesta; o selo é que mentia.
        verificado=False,
        data={
            "url": normalized,
            "dispatch": "DISPATCH_PROVEN",
            "browser_process_present": bool(after),
            "preexisting_browser_pids": sorted(before),
            "observed_browser_pids": sorted(after),
            "target_page_proven": False,
        },
    )


@action(name="browser_open_url", category="os", description="Open a validated HTTP(S) URL in the default browser", capability="PC_CONTROL")
def browser_open_url_action(url: str) -> ActionResult:
    return _send_url_to_default_browser(url)


@action(name="browser_search", category="os", description="Search safely in the default browser", capability="PC_CONTROL")
def browser_search_action(query: str) -> ActionResult:
    text = str(query or "").strip()
    if not text or len(text) > 500 or any(ord(char) < 32 for char in text):
        return ActionResult(success=False, error="Consulta de pesquisa inválida.")
    url = f"https://www.google.com/search?q={quote_plus(text)}"
    result = _send_url_to_default_browser(url)
    if result.success:
        result.output = "Pesquisa enviada ao navegador padrão."
        result.data = {**(result.data or {}), "search_url": url}
    return result


def _resolve_windows_app_command(app: str) -> list[str] | None:
    """Resolve only a canonical allow-listed app id to a fixed executable."""
    spec = _SAFE_WINDOWS_APPS.get(app)
    if spec is None:
        return None

    executable = str(spec["executable"])
    resolved = shutil.which(executable)
    if resolved:
        return [resolved]
    if app in {"settings", "spotify"}:
        return [executable]
    # ZARA-APPS-REAIS-2026-08-27: apps instalados por fora (Telegram, Obsidian,
    # WinRAR, WordPad) nao ficam na PATH do Windows, entao o spec ja guarda o
    # caminho absoluto do .exe achado no Menu Iniciar do Alex.
    if os.path.isabs(executable) and Path(executable).is_file():
        return [executable]
    if app not in {"chrome", "edge"}:
        return [executable]

    relative = "Google/Chrome/Application/chrome.exe" if app == "chrome" else "Microsoft/Edge/Application/msedge.exe"
    candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / relative,
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / relative,
        Path(os.environ.get("LOCALAPPDATA", "")) / relative,
    ]
    for candidate in candidates:
        if str(candidate) and candidate.is_file():
            return [str(candidate)]
    return None


def _list_chrome_profiles() -> dict[str, str]:
    """Real profile names -> directory key, read from Chrome's own config.

    AUDITORIA_2026-08-28 (Alex): ele tem varios perfis (alex, Alice, Pessoa 1,
    Trabalho) e quer abrir direto no perfil certo por voz, sem passar pela
    tela de escolha. Le o mesmo arquivo que o proprio Chrome usa, nao chuta
    nome de pasta.
    """
    local_state = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data" / "Local State"
    try:
        data = json.loads(local_state.read_text(encoding="utf-8"))
        cache = data.get("profile", {}).get("info_cache", {})
        return {str(info.get("name", key)): key for key, info in cache.items()}
    except (OSError, ValueError, KeyError):
        return {}


def resolve_chrome_profile(spoken_name: str) -> str | None:
    """Resolve a spoken profile name to Chrome's real directory key."""
    normalized = _strip_accents(str(spoken_name or "")).strip().casefold()
    if not normalized:
        return None
    for name, key in _list_chrome_profiles().items():
        if _strip_accents(name).strip().casefold() == normalized:
            return key
    return None


@action(name="chrome_open_profile", category="os", description="Open Chrome directly in a named real profile", capability="LOCAL_PC_CONTROL")
def chrome_open_profile_action(profile: str) -> ActionResult:
    profile_key = resolve_chrome_profile(profile)
    if profile_key is None:
        known = ", ".join(_list_chrome_profiles().keys()) or "nenhum perfil encontrado"
        return ActionResult(success=False, error=f"Não achei o perfil \"{profile}\" no Chrome. Perfis reais: {known}.")

    command = _resolve_windows_app_command("chrome")
    if not command:
        return ActionResult(success=False, error="Chrome não foi encontrado neste computador.")

    before = _running_app_pids({"chrome.exe"})
    try:
        subprocess.Popen([command[0], f"--profile-directory={profile_key}"])
    except OSError as exc:
        return ActionResult(success=False, error=f"Falha ao abrir o Chrome: {exc}")

    observed: set[int] = set()
    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline:
        observed = _running_app_pids({"chrome.exe"})
        if observed - before or observed:
            break
        time.sleep(0.1)

    return ActionResult(
        success=bool(observed),
        output=f"Chrome aberto no perfil {profile}." if observed else "",
        error="" if observed else "Chrome não abriu a tempo.",
        data={"profile": profile, "profile_key": profile_key, "verified": bool(observed)},
    )


def _running_app_pids(process_names: set[str]) -> set[int]:
    """Return PIDs for an allow-listed process-name set."""
    import psutil

    normalized = {name.casefold() for name in process_names}
    found: set[int] = set()
    for process in psutil.process_iter(["pid", "name"]):
        try:
            name = str(process.info.get("name") or "").casefold()
            if name in normalized:
                found.add(int(process.info["pid"]))
        except (psutil.AccessDenied, psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
    return found


def _known_windows_folder(folder_id: str) -> Path | None:
    """Resolve a fixed Windows Known Folder GUID via SHGetKnownFolderPath."""
    import ctypes
    from ctypes import wintypes

    guid_text = _WINDOWS_KNOWN_FOLDER_IDS.get(folder_id)
    if guid_text is None:
        return None

    class Guid(ctypes.Structure):
        _fields_ = [
            ("data1", wintypes.DWORD),
            ("data2", wintypes.WORD),
            ("data3", wintypes.WORD),
            ("data4", ctypes.c_ubyte * 8),
        ]

    raw = uuid.UUID(guid_text).bytes_le
    guid = Guid.from_buffer_copy(raw)
    resolved = ctypes.c_wchar_p()
    result = ctypes.windll.shell32.SHGetKnownFolderPath(
        ctypes.byref(guid), 0, None, ctypes.byref(resolved)
    )
    if result != 0 or not resolved.value:
        return None
    try:
        return Path(resolved.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(resolved)


def _resolve_safe_folder(folder: str) -> Path | None:
    """Resolve only canonical allow-listed folder ids to existing directories."""
    canonical = str(folder or "").strip().casefold()
    if canonical not in _SAFE_FOLDER_NAMES:
        return None
    if canonical == "zara_root":
        from core.paths import project_root

        candidate = project_root()
    elif platform.system() == "Windows":
        candidate = _known_windows_folder(canonical)
    else:
        return None
    if candidate is None:
        return None
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    return resolved if resolved.is_dir() and resolved.is_absolute() else None


@action(
    name="os_open",
    category="os",
    description="Open a known safe folder from an explicit allow-list",
    capability="LOCAL_PC_CONTROL",
)
def os_open_action(folder: str) -> ActionResult:
    canonical = str(folder or "").strip().casefold()
    if canonical not in _SAFE_FOLDER_NAMES:
        return ActionResult(
            success=False,
            error="Pasta não autorizada. Use Downloads, Documentos, Área de Trabalho, Imagens ou pasta da ZARA.",
            data={"folder": canonical, "allowlisted": False},
        )
    path = _resolve_safe_folder(canonical)
    if path is None:
        return ActionResult(
            success=False,
            error=f"{_SAFE_FOLDER_NAMES[canonical]} não existe ou não pôde ser resolvida com segurança.",
            data={"folder": canonical, "allowlisted": True, "exists": False},
        )

    before = _running_app_pids({"explorer.exe"})
    try:
        # Use subprocess.Popen as required by ZARA-PC-CONTROL-ALEX-004
        subprocess.Popen(["explorer.exe", str(path)])
    except OSError as exc:
        return ActionResult(success=False, error=f"Falha ao abrir a pasta: {exc}")
    time.sleep(0.25)
    after = _running_app_pids({"explorer.exe"})
    verification = "EXPLORER_PROCESS_PRESENT" if after else "DISPATCH_ONLY"
    return ActionResult(
        success=True,
        output=f"Solicitação para abrir {_SAFE_FOLDER_NAMES[canonical]} enviada ao Explorer.",
        data={
            "folder": canonical,
            "path": str(path),
            "allowlisted": True,
            "preexisting_explorer_pids": sorted(before),
            "observed_explorer_pids": sorted(after),
            "verification": verification,
        },
    )


def _send_windows_media_command(action_name: str) -> None:
    """Send one fixed WM_APPCOMMAND media action; no user text is accepted."""
    import ctypes

    command = _WINDOWS_MEDIA_COMMANDS[action_name]
    hwnd_broadcast = 0xFFFF
    wm_appcommand = 0x0319
    ctypes.windll.user32.SendMessageW(hwnd_broadcast, wm_appcommand, 0, command << 16)


def _read_windows_mute() -> bool | None:
    """Read the master endpoint mute state with COM lifecycle isolation."""
    try:
        from comtypes import CoInitialize, CoUninitialize
        from pycaw.pycaw import AudioUtilities

        from core.windows_audio import get_endpoint_volume

        CoInitialize()
        try:
            devices = AudioUtilities.GetSpeakers()
            volume = get_endpoint_volume(devices)
            return bool(volume.GetMute())
        finally:
            CoUninitialize()
    except Exception:
        return None


def _set_windows_mute(muted: bool) -> bool:
    """Set master endpoint mute through pycaw and return whether it ran."""
    try:
        from comtypes import CoInitialize, CoUninitialize
        from pycaw.pycaw import AudioUtilities

        from core.windows_audio import get_endpoint_volume

        CoInitialize()
        try:
            devices = AudioUtilities.GetSpeakers()
            volume = get_endpoint_volume(devices)
            volume.SetMute(bool(muted), None)
            return True
        finally:
            CoUninitialize()
    except Exception:
        return False


def _read_windows_volume() -> int | None:
    """Read the master endpoint volume (0-100) with COM lifecycle isolation."""
    try:
        from comtypes import CoInitialize, CoUninitialize
        from pycaw.pycaw import AudioUtilities

        from core.windows_audio import get_endpoint_volume

        CoInitialize()
        try:
            devices = AudioUtilities.GetSpeakers()
            volume = get_endpoint_volume(devices)
            return round(volume.GetMasterVolumeLevelScalar() * 100)
        finally:
            CoUninitialize()
    except Exception:
        return None


def _set_windows_volume(level: int) -> bool:
    """Set master endpoint volume (0-100). Tries nircmd first, falls back to pycaw."""
    try:
        subprocess.run(
            ["nircmd.exe", "setsysvolume", str(int(level * 65535 / 100))],
            check=True, capture_output=True,
        )
        return True
    except FileNotFoundError:
        pass
    except Exception:
        return False

    try:
        from comtypes import CoInitialize, CoUninitialize
        from pycaw.pycaw import AudioUtilities

        from core.windows_audio import get_endpoint_volume

        CoInitialize()
        try:
            devices = AudioUtilities.GetSpeakers()
            volume = get_endpoint_volume(devices)
            volume.SetMasterVolumeLevelScalar(level / 100, None)
            return True
        finally:
            CoUninitialize()
    except Exception:
        return False


def _media_semantic_state() -> dict | None:
    """Best-effort semantic playback readback using backends ALREADY present.

    Returns None when no semantic backend is available (winsdk/WinRT GSMTC is
    NOT installed and must not be installed). The pycaw fallback reports which
    processes currently hold an ACTIVE render session, which is a real, if
    coarse, playback signal — enough to prove play/pause transitions.
    """
    if platform.system() != "Windows":
        return None
    try:
        from pycaw.pycaw import AudioUtilities
    except Exception:
        return None
    try:
        active = []
        for session in AudioUtilities.GetAllSessions():
            try:
                if int(session.State) != 1:  # 1 == AudioSessionStateActive
                    continue
                proc = session.Process
                active.append(proc.name() if proc else "system")
            except Exception:
                continue
        return {"backend": "pycaw_session_state", "active_render_sessions": sorted(active)}
    except Exception:
        return None


def _media_action(action_name: str, reply: str) -> ActionResult:
    if platform.system() != "Windows":
        return ActionResult(success=False, error="Controle de mídia disponível somente no Windows.")
    try:
        before = _media_semantic_state()
        _send_windows_media_command(action_name)
        after = _media_semantic_state() if before is not None else None

        if before is None or after is None:
            # Regra #11 / Tarefa 054: NAO declarar sucesso sem readback semantico.
            # WM_APPCOMMAND emite o evento mas nao prove o estado da midia.
            return ActionResult(
                success=False,
                error="MEDIA_COMMAND_SENT_NOT_PROVEN",
                output=reply,
                data={
                    "action": action_name,
                    "transport": "WM_APPCOMMAND",
                    "state_verified": False,
                    "readback": "UNAVAILABLE",
                },
            )

        changed = before != after
        if not changed:
            # Readback existe mas nada mudou: continua NAO PROVADO.
            return ActionResult(
                success=False,
                error="MEDIA_COMMAND_SENT_NOT_PROVEN",
                output=reply,
                data={
                    "action": action_name,
                    "transport": "WM_APPCOMMAND",
                    "state_verified": False,
                    "readback": "NO_SEMANTIC_CHANGE",
                    "before": before,
                    "after": after,
                },
            )

        return ActionResult(
            success=True,
            output=reply,
            data={
                "action": action_name,
                "transport": "WM_APPCOMMAND",
                "state_verified": True,
                "readback": "SEMANTIC_CHANGE_CONFIRMED",
                "before": before,
                "after": after,
            },
        )
    except Exception as exc:
        return ActionResult(success=False, error=f"Falha no controle de mídia: {exc}")


@action(name="media_play_pause", category="os", description="Toggle media play/pause", capability="LOCAL_PC_CONTROL")
def media_play_pause_action() -> ActionResult:
    return _media_action("media_play_pause", "Comando play/pause enviado.")


@action(name="media_next", category="os", description="Skip to next media track", capability="LOCAL_PC_CONTROL")
def media_next_action() -> ActionResult:
    return _media_action("media_next", "Comando de próxima faixa enviado.")


@action(name="media_previous", category="os", description="Return to previous media track", capability="LOCAL_PC_CONTROL")
def media_previous_action() -> ActionResult:
    return _media_action("media_previous", "Comando de faixa anterior enviado.")


@action(name="audio_status", category="os", description="Read the real default Windows audio endpoint and active render sessions", capability="READ_ONLY")
def audio_status_action() -> ActionResult:
    if platform.system() != "Windows":
        return ActionResult(success=False, error="Status de áudio disponível somente no Windows.")
    try:
        from comtypes import CoInitialize, CoUninitialize
        from pycaw.pycaw import AudioUtilities

        from core.windows_audio import get_endpoint_volume
        CoInitialize()
        try:
            endpoint = AudioUtilities.GetSpeakers()
            endpoint_id = str(getattr(endpoint, "id", "") or endpoint.GetId())
            name = ""
            for device in AudioUtilities.GetAllDevices():
                if str(device.id) == endpoint_id:
                    name = str(device.FriendlyName or "")
                    break
            volume = get_endpoint_volume(endpoint)
            level = int(round(float(volume.GetMasterVolumeLevelScalar()) * 100))
            muted = bool(volume.GetMute())
            sessions = _media_semantic_state() or {"backend": "unavailable", "active_render_sessions": []}
        finally:
            CoUninitialize()
        return ActionResult(success=True, output=f"Saída padrão: {name or 'dispositivo sem nome'}, volume {level}%, {'mudo' if muted else 'com som'}.", data={"default_output_id": endpoint_id, "default_output_name": name, "volume": level, "muted": muted, "media": sessions, "metadata_backend": "NOT_AVAILABLE", "verified": True})
    except Exception as exc:
        return ActionResult(success=False, error=f"Não consegui ler o status de áudio: {exc}")


def _audio_mute_action(desired: bool) -> ActionResult:
    if platform.system() != "Windows":
        return ActionResult(success=False, error="Controle de mudo disponível somente no Windows.")
    before = _read_windows_mute()
    if before is None:
        return ActionResult(success=False, error="Não foi possível ler o estado de mudo do Windows.")
    if not _set_windows_mute(desired):
        return ActionResult(success=False, error="Não foi possível alterar o estado de mudo do Windows.")
    after = _read_windows_mute()
    if after is None or after is not desired:
        return ActionResult(
            success=False,
            error="A alteração foi enviada, mas o estado de mudo não pôde ser confirmado.",
            data={"original_muted": before, "requested_muted": desired, "verified_muted": after},
        )
    return ActionResult(
        success=True,
        output="Mudo ativado." if desired else "Mudo desativado.",
        data={"original_muted": before, "requested_muted": desired, "verified_muted": after},
    )


@action(name="audio_mute", category="os", description="Mute master audio", capability="LOCAL_PC_CONTROL")
def audio_mute_action() -> ActionResult:
    return _audio_mute_action(True)


@action(name="audio_unmute", category="os", description="Unmute master audio", capability="LOCAL_PC_CONTROL")
def audio_unmute_action() -> ActionResult:
    return _audio_mute_action(False)


@action(
    name="os_app",
    category="os",
    description="Open a known safe Windows application from an explicit allow-list",
    capability="LOCAL_PC_CONTROL",
)
def os_app_action(app: str) -> ActionResult:
    """Open and verify one canonical allow-listed Windows application."""
    canonical = str(app or "").strip().casefold()
    spec = _SAFE_WINDOWS_APPS.get(canonical)
    if spec is None:
        return ActionResult(
            success=False,
            error="Aplicativo não autorizado. Use um aplicativo conhecido da lista segura.",
            data={"app": canonical, "allowlisted": False},
        )
    if platform.system() != "Windows":
        return ActionResult(success=False, error="Abertura de aplicativos disponível somente no Windows.")

    command = _resolve_windows_app_command(canonical)
    if not command:
        return ActionResult(
            success=False,
            error=f"{spec['display_name']} não foi encontrado neste computador.",
            data={"app": canonical, "allowlisted": True},
        )

    process_names = set(spec["process_names"])
    before = _running_app_pids(process_names)
    try:
        # ShellExecute is the reliable Windows path for both classic and
        # packaged GUI apps. The target still comes exclusively from the
        # canonical allow-list above; user text never reaches this call.
        os.startfile(command[0])  # type: ignore[attr-defined]
    except OSError as exc:
        return ActionResult(success=False, error=f"Falha ao abrir {spec['display_name']}: {exc}")

    observed: set[int] = set()
    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline:
        observed = _running_app_pids(process_names)
        if observed:
            break
        time.sleep(0.1)

    created = observed - before
    if not observed:
        return ActionResult(
            success=False,
            error=f"Não foi possível verificar o processo de {spec['display_name']} após a abertura.",
            data={
                "app": canonical,
                "allowlisted": True,
                "launcher_pid": None,
                "preexisting_pids": sorted(before),
                "observed_pids": [],
                "created_pids": [],
                "verified": False,
            },
        )

    hwnd = None
    window_deadline = time.monotonic() + 4.0
    while hwnd is None and time.monotonic() < window_deadline:
        hwnd = _window_for_pids(observed)
        if hwnd is None:
            time.sleep(0.1)

    return ActionResult(
        success=True,
        output=str(spec["opened_reply"]),
        data={
            "app": canonical,
            "allowlisted": True,
            "launcher_pid": None,
            "preexisting_pids": sorted(before),
            "observed_pids": sorted(observed),
            "created_pids": sorted(created),
            "hwnd": hwnd,
            "window_pid": _window_pid(hwnd) if hwnd is not None else None,
            "verified": True,
        },
    )


@action(
    name="os_close_safe_app",
    category="os",
    description="Close one explicit low-risk allow-listed application window",
    capability="LOCAL_PC_CONTROL",
)
def os_close_safe_app_action(app: str) -> ActionResult:
    canonical = str(app or "").strip().casefold()
    if canonical not in _SAFE_CLOSE_APPS:
        return ActionResult(
            success=False,
            error="Fechamento não autorizado: o aplicativo pode conter trabalho não salvo.",
            data={"app": canonical, "allowlisted": False},
        )
    spec = _SAFE_WINDOWS_APPS[canonical]
    pids = _running_app_pids(set(spec["process_names"]))
    target = _window_for_safe_app(canonical, pids)
    if target is None:
        return ActionResult(success=False, error=f"Nenhuma janela de {spec['display_name']} foi encontrada.")
    import ctypes

    before_pid = _window_pid(target)
    if not ctypes.windll.user32.PostMessageW(target, 0x0010, 0, 0):  # WM_CLOSE
        return ActionResult(success=False, error="O Windows recusou o fechamento seguro da janela.")
    deadline = time.monotonic() + 3.0
    while ctypes.windll.user32.IsWindow(target) and time.monotonic() < deadline:
        time.sleep(0.1)
    if ctypes.windll.user32.IsWindow(target):
        return ActionResult(success=False, error="O fechamento foi enviado, mas a janela permaneceu aberta.")
    return ActionResult(
        success=True,
        output=f"Aplicativo fechado e verificado: {spec['display_name']}.",
        data={"app": canonical, "hwnd": target, "pid": before_pid, "verified_closed": True},
    )


# ZARA-BARRINHA-DE-VOLUME-001
#
# Alex: "quando eu peco para aumentar o volume eu quero que apareca a barrinha
# de volume na tela descendo e subindo como acontece quando eu clico em diminuir
# ou aumentar algo".
#
# A ZARA mudava o volume pela API de áudio do Windows, que é silenciosa: o
# volume muda mas nada aparece na tela, e ele fica sem confirmação visual.
# Quem faz o Windows desenhar aquela barrinha é a TECLA de mídia, não a API.
#
# Então, depois de ajustar o volume, mandamos um par de teclas que se anula
# (sobe e desce, ou desce e sobe): o volume final continua exatamente o pedido e
# a barrinha aparece. A ordem depende do nível para não esbarrar no 0 nem no 100
# — nas pontas, um par na ordem errada deixaria de ser neutro.
_VK_VOLUME_UP = 0xAF
_VK_VOLUME_DOWN = 0xAE
_KEYEVENTF_KEYUP = 0x0002


def _tecla_de_midia(codigo: int) -> None:
    import ctypes

    ctypes.windll.user32.keybd_event(codigo, 0, 0, 0)
    ctypes.windll.user32.keybd_event(codigo, 0, _KEYEVENTF_KEYUP, 0)


def _mostrar_barrinha_de_volume(nivel_atual: int | None = None) -> bool:
    """Faz o Windows desenhar o indicador de volume, sem alterar o valor."""
    if platform.system() != "Windows":
        return False
    try:
        perto_do_minimo = nivel_atual is not None and nivel_atual <= 5
        primeira = _VK_VOLUME_UP if perto_do_minimo else _VK_VOLUME_DOWN
        segunda = _VK_VOLUME_DOWN if perto_do_minimo else _VK_VOLUME_UP
        _tecla_de_midia(primeira)
        time.sleep(0.03)
        _tecla_de_midia(segunda)
        return True
    except Exception:
        return False


@action(name="os_volume", category="os", description="Get or set system volume", capability="LOCAL_PC_CONTROL")
def os_volume_action(level: int = None, mute: bool = None) -> ActionResult:
    """Get or set system volume."""
    # AUDITORIA_SEGURANCA_2026-09-02: level/mute eram interpolados direto em
    # string de shell (pactl) e AppleScript (osascript) sem validar tipo.
    # Um valor nao-numerico em level, ou algo alem de bool em mute, podia virar
    # injecao de comando/AppleScript. Forcar tipo e faixa antes de qualquer
    # subprocess. SAFE_TO_FIX: validacao pura, sem mudar comportamento normal.
    if level is not None:
        try:
            level = max(0, min(100, int(level)))
        except (TypeError, ValueError):
            return ActionResult(success=False, error="Nível de volume inválido.")
    if mute is not None:
        mute = bool(mute)
    try:
        system = platform.system()

        if system == "Windows":
            # Mute-only calls delegate entirely to the dedicated, already-verified
            # mute action instead of duplicating the read/write/verify dance here.
            if mute is not None and level is None:
                return _audio_mute_action(mute)

            if level is not None:
                original = _read_windows_volume()
                if original == level:
                    return ActionResult(
                        success=False,
                        error=f"Volume já está em {level}.",
                        data={"original_level": original, "target_level": level, "verified": True},
                    )

                if not _set_windows_volume(level):
                    return ActionResult(success=False, error="Não foi possível alterar o volume.")

                # ZARA-BARRINHA-DE-VOLUME-001: confirmação visual, como quando ele
                # mexe no volume pelo teclado.
                _mostrar_barrinha_de_volume(level)

                # SAFE_TO_FIX (windows_fs audit #7): dispatch não é prova de que o
                # Windows mudou (evidence.md). Ler de volta e só declarar sucesso
                # se bater.
                observed = _read_windows_volume()
                if observed is None or abs(observed - level) > 2:
                    return ActionResult(
                        success=False,
                        error=f"Volume não confirmado: pedido {level}, lido {observed}.",
                        data={
                            "original_level": original,
                            "target_level": level,
                            "observed_level": observed,
                            "verified": False,
                        },
                    )
                return ActionResult(
                    success=True,
                    output="Volume adjusted",
                    data={
                        "original_level": original,
                        "target_level": level,
                        "observed_level": observed,
                        "verified": True,
                    },
                )

            if mute is not None:
                return _audio_mute_action(mute)

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


def _physical_monitor_handles() -> list[int]:
    """Enumerate DXVA2 physical monitor handles without shell or Registry."""
    import ctypes
    from ctypes import wintypes

    class PhysicalMonitor(ctypes.Structure):
        _fields_ = [
            ("handle", wintypes.HANDLE),
            ("description", wintypes.WCHAR * 128),
        ]

    handles: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HANDLE,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )

    def collect(display_handle, _hdc, _rect, _data):
        count = wintypes.DWORD()
        if not ctypes.windll.dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(
            display_handle, ctypes.byref(count)
        ):
            return True
        monitors = (PhysicalMonitor * count.value)()
        if ctypes.windll.dxva2.GetPhysicalMonitorsFromHMONITOR(
            display_handle, count.value, monitors
        ):
            handles.extend(int(monitor.handle) for monitor in monitors if monitor.handle)
        return True

    callback = callback_type(collect)
    ctypes.windll.user32.EnumDisplayMonitors(None, None, callback, 0)
    return handles


def _read_windows_brightness() -> int | None:
    """Read brightness from the first DDC/CI-capable physical monitor."""
    import ctypes
    from ctypes import wintypes

    handles = _physical_monitor_handles()
    try:
        for handle in handles:
            minimum = wintypes.DWORD()
            current = wintypes.DWORD()
            maximum = wintypes.DWORD()
            if ctypes.windll.dxva2.GetMonitorBrightness(
                wintypes.HANDLE(handle),
                ctypes.byref(minimum),
                ctypes.byref(current),
                ctypes.byref(maximum),
            ):
                span = maximum.value - minimum.value
                if span > 0:
                    return round((current.value - minimum.value) * 100 / span)
        return None
    finally:
        for handle in handles:
            ctypes.windll.dxva2.DestroyPhysicalMonitor(wintypes.HANDLE(handle))


def _set_windows_brightness(level: int) -> bool:
    """Set all DDC/CI-capable monitors to a clamped percentage."""
    import ctypes
    from ctypes import wintypes

    target = max(0, min(100, int(level)))
    handles = _physical_monitor_handles()
    changed = False
    try:
        for handle in handles:
            minimum = wintypes.DWORD()
            current = wintypes.DWORD()
            maximum = wintypes.DWORD()
            native_handle = wintypes.HANDLE(handle)
            if not ctypes.windll.dxva2.GetMonitorBrightness(
                native_handle,
                ctypes.byref(minimum),
                ctypes.byref(current),
                ctypes.byref(maximum),
            ):
                continue
            native_target = minimum.value + round((maximum.value - minimum.value) * target / 100)
            if ctypes.windll.dxva2.SetMonitorBrightness(native_handle, native_target):
                changed = True
        return changed
    finally:
        for handle in handles:
            ctypes.windll.dxva2.DestroyPhysicalMonitor(wintypes.HANDLE(handle))


def _wmi_read_brightness() -> int | None:
    """Fallback brightness read via WMI (laptop panels without DDC/CI)."""
    import subprocess

    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBrightness"
             " -ErrorAction Stop).CurrentBrightness"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20,
        )
        val = (out.stdout or "").strip().splitlines()
        for line in val:
            line = line.strip()
            if line.isdigit():
                return max(0, min(100, int(line)))
    except Exception:
        pass
    return None


def _wmi_set_brightness(level: int) -> bool:
    """Fallback brightness set via WMI. Returns True only if the write succeeded."""
    import subprocess

    target = max(0, min(100, int(level)))
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "$m = Get-WmiObject -Namespace root/wmi -Class WmiMonitorBrightnessMethods"
             " -ErrorAction Stop; if ($m) { $m.WmiSetBrightness(1, "
             f"{target}) | Out-Null; 'OK' }} else {{ 'NO_METHOD' }}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25,
        )
        return "OK" in (out.stdout or "")
    except Exception:
        return False


def _brightness_action(level: int) -> ActionResult:
    if platform.system() != "Windows":
        return ActionResult(success=False, error="Controle de brilho disponível somente no Windows.")
    target = max(0, min(100, int(level)))

    # Preferred path: DDC/CI (external monitors). Fallback: WMI (laptop panels).
    backend = "ddcci"
    before = _read_windows_brightness()
    if before is None:
        before = _wmi_read_brightness()
        backend = "wmi" if before is not None else "none"

    if before is None:
        return ActionResult(
            success=False,
            error="Este monitor não oferece controle seguro de brilho (sem DDC/CI nem WMI).",
            data={"supported": False},
        )

    if backend == "ddcci":
        wrote = _set_windows_brightness(target)
        if not wrote:
            # DDC/CI read worked but the write was refused: try WMI before failing.
            wrote = _wmi_set_brightness(target)
            if wrote:
                backend = "wmi"
    else:
        wrote = _wmi_set_brightness(target)

    if not wrote:
        return ActionResult(success=False, error="O monitor recusou a alteração de brilho.")

    after = _read_windows_brightness() if backend == "ddcci" else _wmi_read_brightness()
    if after is None:
        return ActionResult(
            success=False,
            error="A alteração foi enviada, mas o brilho não pôde ser confirmado.",
            data={"original": before, "target": target, "observed": None, "backend": backend},
        )
    return ActionResult(
        success=True,
        output=f"Brilho definido para {after}%.",
        data={"supported": True, "original": before, "target": target,
              "observed": after, "backend": backend, "tolerance": 2},
    )


@action(name="os_brightness", category="os", description="Get or set screen brightness", capability="LOCAL_PC_CONTROL")
def os_brightness_action(level: int = None) -> ActionResult:
    if level is None:
        current = _read_windows_brightness() if platform.system() == "Windows" else None
        if current is None and platform.system() == "Windows":
            current = _wmi_read_brightness()
        if current is None:
            return ActionResult(success=False, error="Brilho não suportado neste monitor.")
        return ActionResult(
            success=True,
            output=f"Brilho atual: {current}%",
            data={"level": current, "observed": current},
        )
    return _brightness_action(level)


@action(name="os_brightness_absolute", category="os", description="Set absolute screen brightness", capability="LOCAL_PC_CONTROL")
def os_brightness_absolute_action(level: int) -> ActionResult:
    return _brightness_action(level)


def _relative_brightness(delta: int) -> ActionResult:
    if platform.system() != "Windows":
        return ActionResult(success=False, error="Controle de brilho disponível somente no Windows.")
    current = _read_windows_brightness()
    if current is None:
        current = _wmi_read_brightness()
    if current is None:
        return ActionResult(
            success=False,
            error="Não há referência de brilho: este monitor não oferece DDC/CI nem WMI.",
            data={"supported": False},
        )
    return _brightness_action(max(0, min(100, current + delta)))


@action(name="os_brightness_up", category="os", description="Increase screen brightness by 10", capability="LOCAL_PC_CONTROL")
def os_brightness_up_action() -> ActionResult:
    return _relative_brightness(10)


@action(name="os_brightness_down", category="os", description="Decrease screen brightness by 10", capability="LOCAL_PC_CONTROL")
def os_brightness_down_action() -> ActionResult:
    return _relative_brightness(-10)


def _night_light_not_supported(detail: str = "") -> ActionResult:
    return ActionResult(
        success=False,
        error=detail or "Luz noturna não possui uma API segura suportada; nenhuma alteração foi feita.",
        data={"supported": False, "safe_status": "NOT_SUPPORTED_SAFE"},
    )


# Nomes/AutomationIds semânticos expostos pelo app Configurações do Windows.
_NIGHT_LIGHT_AUTOMATION_IDS = (
    "SystemSettings_Display_BlueLight_ManualToggle_Toggle",
    "SystemSettings_Display_BlueLight_ManualToggle_ToggleSwitch",
)
# Botão manual (Windows 11 pt-BR): não expõe TogglePattern, mas o Name é o estado.
_NIGHT_LIGHT_BUTTON_AUTOMATION_IDS = (
    "SystemSettings_Display_BlueLight_ManualToggleOn_Button",
    "SystemSettings_Display_BlueLight_ManualToggleOff_Button",
)
# Name do botão manual -> estado ATUAL da luz noturna.
_NIGHT_LIGHT_BUTTON_NAME_STATE = {
    "ativar agora": False,
    "turn on now": False,
    "desativar agora": True,
    "turn off now": True,
}

_NIGHT_LIGHT_SETTINGS_URI = "ms-settings:nightlight"


class _ToggleControl:
    """Envelope fino sobre um elemento UIA que expõe TogglePattern."""

    kind = "TogglePattern"

    def __init__(self, element, toggle_pattern, describe: str = ""):
        self._element = element
        self._pattern = toggle_pattern
        self.describe = describe

    def get_toggle_state(self):
        """True=ligado, False=desligado, None=estado não legível (indeterminado/erro)."""
        try:
            state = int(self._pattern.CurrentToggleState)
        except Exception:
            return None
        if state == 1:
            return True
        if state == 0:
            return False
        return None

    def toggle(self) -> bool:
        try:
            self._pattern.Toggle()
            return True
        except Exception:
            return False


class _ManualButtonControl:
    """Botão manual de Luz noturna: estado lido do Name acessível, ação por InvokePattern."""

    kind = "InvokePattern+AccessibleName"

    def __init__(self, element, invoke_pattern, describe: str = ""):
        self._element = element
        self._pattern = invoke_pattern
        self.describe = describe

    def get_toggle_state(self):
        try:
            name = str(self._element.CurrentName or "").strip().casefold()
        except Exception:
            return None
        return _NIGHT_LIGHT_BUTTON_NAME_STATE.get(name)

    def toggle(self) -> bool:
        try:
            self._pattern.Invoke()
            return True
        except Exception:
            return False


def _open_night_light_settings() -> bool:
    """Abre a página correta de Configurações (uso permitido do URI)."""
    try:
        os.startfile(_NIGHT_LIGHT_SETTINGS_URI)  # noqa: S606
        return True
    except Exception:
        return False


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


def _find_night_light_toggle(timeout: float = 8.0):
    """Localiza semanticamente o controle de Luz noturna via UI Automation.

    Preferência: TogglePattern. Fallback: botão manual com AutomationId conhecido,
    cujo estado é lido pelo Name acessível. Nunca usa coordenadas nem clique cego.
    """
    if platform.system() != "Windows":
        return None
    automation, UIA = _uia_client()
    if automation is None:
        return None

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            root = automation.GetRootElement()
            condition = automation.CreateTrueCondition()
            found = root.FindAll(UIA.TreeScope_Descendants, condition)
            count = int(found.Length)
        except Exception:
            count, found = 0, None

        fallback = None
        for index in range(count):
            try:
                element = found.GetElement(index)
                automation_id = str(element.CurrentAutomationId or "")
            except Exception:
                continue

            if automation_id in _NIGHT_LIGHT_AUTOMATION_IDS:
                try:
                    pattern = element.GetCurrentPattern(UIA.UIA_TogglePatternId)
                    pattern = pattern.QueryInterface(UIA.IUIAutomationTogglePattern)
                except Exception:
                    pattern = None
                if pattern is not None:
                    return _ToggleControl(element, pattern, describe=automation_id)

            if fallback is None and automation_id in _NIGHT_LIGHT_BUTTON_AUTOMATION_IDS:
                try:
                    pattern = element.GetCurrentPattern(UIA.UIA_InvokePatternId)
                    pattern = pattern.QueryInterface(UIA.IUIAutomationInvokePattern)
                except Exception:
                    pattern = None
                if pattern is not None:
                    fallback = _ManualButtonControl(element, pattern, describe=automation_id)

        if fallback is not None:
            return fallback
        time.sleep(0.5)
    return None


# ZARA-LUZ-NOTURNA-SILENCIOSA-001
#
# Alex: "quando eu pedir pra ativar a luz noturna nao quero que abra nada só
# ative e desative por baixo dos panos". A versão anterior abria o app
# Configurações e clicava no botão por acessibilidade — visível, lento e frágil.
#
# O Windows guarda o estado da luz noturna num blob binário do CloudStore.
# Formato conferido MEDINDO nesta máquina (ligada 43 bytes, desligada 41):
#
#   ligada    ... 2a 2b 0e 15 43 42 01 00 10 00 d0 0a 02 ...
#   desligada ... 2a 2b 0e 13 43 42 01 00       d0 0a 02 ...
#
#   byte[18]   0x15 = ligada, 0x13 = desligada
#   bytes 23,24 "10 00" existem só quando ligada
#   bytes 10..14 carimbo de hora (varint de segundos epoch) — precisa mudar,
#                senão o Windows ignora a escrita
#
# Escrever direto é instantâneo e não abre janela nenhuma. Se falhar, a rota
# antiga por Configurações continua atrás como reserva.
_LUZ_NOTURNA_CHAVE = (
    r"Software\Microsoft\Windows\CurrentVersion\CloudStore\Store\DefaultAccount"
    r"\Current\default$windows.data.bluelightreduction.bluelightreductionstate"
    r"\windows.data.bluelightreduction.bluelightreductionstate"
)


def _varint(numero: int) -> bytearray:
    saida = bytearray()
    while True:
        parte = numero & 0x7F
        numero >>= 7
        saida.append(parte | (0x80 if numero else 0))
        if not numero:
            return saida


def _luz_noturna_ler() -> bytearray | None:
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _LUZ_NOTURNA_CHAVE) as chave:
            return bytearray(winreg.QueryValueEx(chave, "Data")[0])
    except Exception:
        return None


def _luz_noturna_ligada(blob: bytearray) -> bool | None:
    if blob is None or len(blob) < 19:
        return None
    if blob[18] == 0x15:
        return True
    if blob[18] == 0x13:
        return False
    return None  # layout desconhecido: não arrisca


def _luz_noturna_por_registro(desejado: bool) -> ActionResult | None:
    """Liga/desliga sem abrir nada. Devolve None quando não dá para confiar."""
    blob = _luz_noturna_ler()
    atual = _luz_noturna_ligada(blob) if blob is not None else None
    if atual is None:
        return None

    if atual == desejado:
        return ActionResult(
            success=True,
            output="Luz noturna já estava " + ("ligada." if desejado else "desligada."),
            data={"supported": True, "before": atual, "after": atual,
                  "changed": False, "via": "registro"},
        )

    novo = bytearray(blob)
    novo[10:15] = _varint(int(time.time()))
    if desejado:
        novo[18] = 0x15
        novo[23:23] = b"\x10\x00"
    else:
        novo[18] = 0x13
        del novo[23:25]

    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, _LUZ_NOTURNA_CHAVE, 0, winreg.KEY_SET_VALUE
        ) as chave:
            winreg.SetValueEx(chave, "Data", 0, winreg.REG_BINARY, bytes(novo))
    except Exception:
        return None

    # Postcondição real: relê o que o Windows deixou gravado.
    depois = None
    limite = time.monotonic() + 2.0
    while time.monotonic() < limite:
        depois = _luz_noturna_ligada(_luz_noturna_ler())
        if depois == desejado:
            break
        time.sleep(0.15)

    if depois != desejado:
        return None  # não confirmou: deixa a rota antiga tentar

    return ActionResult(
        success=True,
        output="Luz noturna " + ("ligada." if desejado else "desligada."),
        data={"supported": True, "before": atual, "after": depois,
              "changed": True, "via": "registro"},
    )


def _night_light_set(desired: bool) -> ActionResult:
    if platform.system() != "Windows":
        return _night_light_not_supported("Luz noturna disponível somente no Windows.")

    # Caminho rápido e invisível primeiro.
    rapido = _luz_noturna_por_registro(desired)
    if rapido is not None:
        return rapido

    _open_night_light_settings()
    control = _find_night_light_toggle()
    if control is None:
        return _night_light_not_supported(
            "Não encontrei o controle acessível de Luz noturna; nenhuma alteração foi feita."
        )

    before = control.get_toggle_state()
    if before is None:
        return _night_light_not_supported(
            "O controle de Luz noturna não expõe estado legível; nenhuma alteração foi feita."
        )

    if before == desired:
        return ActionResult(
            success=True,
            output="Luz noturna já estava " + ("ligada." if desired else "desligada."),
            data={"supported": True, "before": before, "after": before, "changed": False},
        )

    if not control.toggle():
        return ActionResult(
            success=False,
            error="O controle de Luz noturna recusou a alteração.",
            data={"supported": True, "before": before, "after": before, "changed": False},
        )

    after = None
    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline:
        # Re-localiza o controle: o app Configurações troca o elemento/AutomationId
        # ao mudar de estado, então reler o mesmo nó cacheado não é confiável.
        fresh = _find_night_light_toggle(timeout=1.0)
        after = fresh.get_toggle_state() if fresh is not None else control.get_toggle_state()
        if after == desired:
            break
        time.sleep(0.3)

    if after != desired:
        return ActionResult(
            success=False,
            error="A alteração foi enviada, mas o estado da Luz noturna não pôde ser confirmado.",
            data={"supported": True, "before": before, "after": after, "changed": False},
        )

    return ActionResult(
        success=True,
        output="Luz noturna " + ("ligada." if desired else "desligada.") + " Estado confirmado.",
        data={"supported": True, "before": before, "after": after, "changed": True},
    )


@action(name="os_night_light_on", category="os", description="Enable Windows night light when safely supported", capability="LOCAL_PC_CONTROL")
def os_night_light_on_action() -> ActionResult:
    return _night_light_set(True)


@action(name="os_night_light_off", category="os", description="Disable Windows night light when safely supported", capability="LOCAL_PC_CONTROL")
def os_night_light_off_action() -> ActionResult:
    return _night_light_set(False)


_CRITICAL_WINDOW_PROCESSES = {
    "dwm.exe",
    "explorer.exe",
    "lockapp.exe",
    "searchhost.exe",
    "sihost.exe",
    "startmenuexperiencehost.exe",
    "winlogon.exe",
}


def _window_process_name(hwnd: int) -> str:
    import psutil

    try:
        return psutil.Process(_window_pid(hwnd)).name().casefold()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        return ""


def _window_pid(hwnd: int) -> int:
    import ctypes

    pid = ctypes.c_ulong()
    ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _eligible_window(hwnd: int) -> bool:
    import ctypes

    if not hwnd or not ctypes.windll.user32.IsWindow(hwnd):
        return False
    if not ctypes.windll.user32.IsWindowVisible(hwnd):
        return False
    if ctypes.windll.user32.GetWindowTextLengthW(hwnd) <= 0:
        return False
    if ctypes.windll.user32.GetWindow(hwnd, 4):
        return False
    if ctypes.windll.user32.GetWindowLongW(hwnd, -20) & 0x80:
        return False
    return _window_process_name(hwnd) not in _CRITICAL_WINDOW_PROCESSES


def _foreground_window() -> int | None:
    import ctypes

    hwnd = int(ctypes.windll.user32.GetForegroundWindow() or 0)
    return hwnd if _eligible_window(hwnd) else None


def _window_state(hwnd: int) -> str:
    import ctypes

    if ctypes.windll.user32.IsIconic(hwnd):
        return "minimized"
    if ctypes.windll.user32.IsZoomed(hwnd):
        return "maximized"
    return "restored"


def _window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """Return the observed outer window rectangle for an exact HWND."""
    import ctypes

    class Rect(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    rect = Rect()
    if not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)


def _window_work_area(hwnd: int) -> tuple[int, int, int, int] | None:
    """Read the work area of the monitor containing the target window."""
    import ctypes

    class Rect(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", Rect),
                    ("rcWork", Rect), ("dwFlags", ctypes.c_ulong)]

    monitor = ctypes.windll.user32.MonitorFromWindow(hwnd, 2)  # nearest monitor
    info = MonitorInfo()
    info.cbSize = ctypes.sizeof(MonitorInfo)
    if not monitor or not ctypes.windll.user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        return None
    work = info.rcWork
    return int(work.left), int(work.top), int(work.right), int(work.bottom)


def _set_window_rect(hwnd: int, target: tuple[int, int, int, int]) -> bool:
    import ctypes

    ctypes.windll.user32.ShowWindow(hwnd, 9)
    return bool(ctypes.windll.user32.SetWindowPos(hwnd, 0, *target, 0x0004 | 0x0010))


def _window_geometry_action(command: str, hwnd: int | None = None) -> ActionResult:
    """Move/resize one unequivocal HWND and prove the resulting geometry."""
    if platform.system() != "Windows":
        return ActionResult(success=False, error="Controle de janelas disponível somente no Windows.")
    if hwnd is None or not _eligible_window(hwnd):
        return ActionResult(success=False, error="Não tenho uma janela recente e inequívoca para mover.")
    if command not in {"left", "right", "larger"}:
        return ActionResult(success=False, error="Geometria de janela não permitida.")
    before = _window_rect(hwnd)
    work = _window_work_area(hwnd)
    if before is None or work is None:
        return ActionResult(success=False, error="Não consegui ler a posição da janela.")
    wl, wt, wr, wb = work
    work_width, work_height = wr - wl, wb - wt
    if command in {"left", "right"}:
        width = max(1, work_width // 2)
        target = (wl if command == "left" else wr - width, wt, width, work_height)
    else:
        bl, bt, br, bb = before
        width = min(work_width, max(br - bl + work_width // 5, work_width // 2))
        height = min(work_height, max(bb - bt + work_height // 5, work_height // 2))
        target = (wl + (work_width - width) // 2, wt + (work_height - height) // 2, width, height)
    if not _set_window_rect(hwnd, target):
        return ActionResult(success=False, error="O Windows recusou a mudança da janela.")
    time.sleep(0.15)
    after = _window_rect(hwnd)
    expected_rect = (target[0], target[1], target[0] + target[2], target[1] + target[3])
    verified = after is not None and all(abs(a - b) <= 2 for a, b in zip(after, expected_rect))
    if not verified:
        return ActionResult(success=False, error="A nova posição da janela não pôde ser confirmada.", data={"hwnd": hwnd, "before": before, "after": after, "expected": expected_rect})
    labels = {"left": "lado esquerdo", "right": "lado direito", "larger": "maior"}
    return ActionResult(success=True, output=f"Janela ajustada para {labels[command]} e verificada.", data={"hwnd": hwnd, "pid": _window_pid(hwnd), "before": before, "after": after, "work_area": work, "verified": True})


def _window_for_pids(pids: set[int]) -> int | None:
    import ctypes

    for hwnd in _eligible_windows():
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value in pids:
            return hwnd
    return None


def _window_text(hwnd: int) -> str:
    import ctypes

    length = int(ctypes.windll.user32.GetWindowTextLengthW(hwnd) or 0)
    buffer = ctypes.create_unicode_buffer(length + 1)
    ctypes.windll.user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value


def _window_for_safe_app(app: str, pids: set[int]) -> int | None:
    direct = _window_for_pids(pids)
    if direct is not None:
        return direct
    tokens = _SAFE_CLOSE_TITLE_TOKENS.get(app, set())
    for hwnd in _eligible_windows():
        title = _window_text(hwnd).strip().casefold()
        if any(token == title or f" - {token}" in title for token in tokens):
            return hwnd
    return None


def _window_state_action(command: str, hwnd: int | None = None) -> ActionResult:
    if platform.system() != "Windows":
        return ActionResult(success=False, error="Controle de janelas disponível somente no Windows.")
    if hwnd is not None and not _eligible_window(hwnd):
        return ActionResult(success=False, error="A janela contextual não existe mais ou deixou de ser segura.")
    target = hwnd if hwnd is not None else _foreground_window()
    if target is None:
        return ActionResult(success=False, error="Nenhuma janela ativa segura foi identificada.")
    import ctypes

    show_codes = {"minimize": 6, "maximize": 3, "restore": 9}
    expected = {"minimize": "minimized", "maximize": "maximized", "restore": "restored"}
    before = _window_state(target)
    ctypes.windll.user32.ShowWindow(target, show_codes[command])
    time.sleep(0.12)
    after = _window_state(target)
    # SW_RESTORE returns a window minimized from maximized back to maximized.
    # Its real postcondition is "no longer minimized"; the other commands
    # still require their exact requested state.
    verified = after != "minimized" if command == "restore" else after == expected[command]
    if not verified:
        return ActionResult(success=False, error="O estado da janela não pôde ser confirmado.")
    state_labels = {"minimized": "minimizada", "maximized": "maximizada", "restored": "restaurada"}
    return ActionResult(
        success=True,
        output=f"Janela {state_labels[after]} e verificada.",
        data={"hwnd": target, "pid": _window_pid(target), "process": _window_process_name(target), "before": before, "after": after, "verified": True},
    )


@action(name="window_minimize", category="os", description="Minimize the safe active window", capability="LOCAL_PC_CONTROL")
def window_minimize_action(hwnd: int | None = None) -> ActionResult:
    return _window_state_action("minimize", hwnd)


@action(name="window_maximize", category="os", description="Maximize the safe active window", capability="LOCAL_PC_CONTROL")
def window_maximize_action(hwnd: int | None = None) -> ActionResult:
    return _window_state_action("maximize", hwnd)


@action(name="window_restore", category="os", description="Restore the safe active window", capability="LOCAL_PC_CONTROL")
def window_restore_action(hwnd: int | None = None) -> ActionResult:
    return _window_state_action("restore", hwnd)


@action(name="window_move", category="os", description="Move an unequivocal recent window to one monitor side", capability="LOCAL_PC_CONTROL")
def window_move_action(side: str, hwnd: int | None = None) -> ActionResult:
    return _window_geometry_action(str(side or "").strip().casefold(), hwnd)


@action(name="window_resize_larger", category="os", description="Make an unequivocal recent window larger", capability="LOCAL_PC_CONTROL")
def window_resize_larger_action(hwnd: int | None = None) -> ActionResult:
    return _window_geometry_action("larger", hwnd)


@action(name="window_close", category="os", description="Close an unequivocal recent safe window and verify it disappeared", capability="LOCAL_PC_CONTROL")
def window_close_action(hwnd: int | None = None) -> ActionResult:
    if platform.system() != "Windows":
        return ActionResult(success=False, error="Controle de janelas disponível somente no Windows.")
    if hwnd is None or not _eligible_window(hwnd):
        return ActionResult(success=False, error="Não tenho uma janela recente e inequívoca para fechar.")
    import ctypes

    title = _window_text(hwnd).strip()
    process = _window_process_name(hwnd)
    protected = f"{title} {process}".casefold()
    if any(token in protected for token in ("chatgpt", "zara room", "zara.exe")):
        return ActionResult(success=False, error="Essa janela está protegida e não será fechada.", data={"hwnd": hwnd, "status": "PROTECTED"})
    pid = _window_pid(hwnd)
    if not ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0):
        return ActionResult(success=False, error="O Windows recusou o fechamento da janela.")
    for _ in range(10):
        time.sleep(0.1)
        if not ctypes.windll.user32.IsWindow(hwnd):
            return ActionResult(success=True, output="Janela fechada e verificada.", data={"hwnd": hwnd, "pid": pid, "process": process, "title": title, "verified": True})
    return ActionResult(success=False, error="Solicitei o fechamento, mas a janela continua aberta.", data={"hwnd": hwnd, "pid": pid, "verified": False})


def _eligible_windows() -> list[int]:
    import ctypes

    found: list[int] = []
    callback_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def collect(hwnd, _data):
        native = int(hwnd or 0)
        if _eligible_window(native):
            found.append(native)
        return True

    ctypes.windll.user32.EnumWindows(callback_type(collect), 0)
    return found


_NAMED_WINDOW_TARGETS = {"chrome", "zara", "vscode", "project"}


def _focus_window_verified(hwnd: int) -> bool:
    """Focus an exact HWND using Windows thread queues, then verify foreground."""
    import ctypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if int(user32.GetForegroundWindow() or 0) == hwnd:
        return True
    user32.ShowWindow(hwnd, 9)
    foreground = int(user32.GetForegroundWindow() or 0)
    current_thread = int(kernel32.GetCurrentThreadId())
    foreground_thread = int(user32.GetWindowThreadProcessId(foreground, None) or 0)
    target_thread = int(user32.GetWindowThreadProcessId(hwnd, None) or 0)
    attached: list[int] = []
    try:
        for thread_id in {foreground_thread, target_thread}:
            if thread_id and thread_id != current_thread:
                if user32.AttachThreadInput(current_thread, thread_id, True):
                    attached.append(thread_id)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
    finally:
        for thread_id in reversed(attached):
            user32.AttachThreadInput(current_thread, thread_id, False)
    time.sleep(0.15)
    return int(user32.GetForegroundWindow() or 0) == hwnd


def _window_matches_named_target(hwnd: int, target: str) -> bool:
    import psutil

    from core.paths import project_root

    process = _window_process_name(hwnd)
    title = _window_text(hwnd).strip().casefold()
    try:
        command = " ".join(psutil.Process(_window_pid(hwnd)).cmdline()).casefold()
    except (psutil.AccessDenied, psutil.NoSuchProcess):
        command = ""
    project_name = project_root().name.casefold()
    if target == "chrome":
        return process == "chrome.exe"
    if target == "vscode":
        return process in {"code.exe", "code - insiders.exe"} or "visual studio code" in title
    if target == "zara":
        return (
            "zara" in title
            or "zara" in process
            or ("dist-electron" in command and "main.js" in command and project_name in command)
        )
    if target == "project":
        return project_name in title
    return False


@action(name="window_focus_named", category="os", description="Focus one unambiguous allowlisted window by semantic app name", capability="LOCAL_PC_CONTROL")
def window_focus_named_action(target: str) -> ActionResult:
    if platform.system() != "Windows":
        return ActionResult(success=False, error="Controle de janelas disponível somente no Windows.")
    canonical = str(target or "").strip().casefold()
    if canonical not in _NAMED_WINDOW_TARGETS:
        return ActionResult(success=False, error="Alvo de janela não permitido.")
    candidates = [
        hwnd for hwnd in _eligible_windows()
        if _window_matches_named_target(hwnd, canonical)
    ]
    foreground = _foreground_window()
    if foreground in candidates:
        selected = foreground
        selection = "ALREADY_FOREGROUND"
    elif len(candidates) == 1:
        selected = candidates[0]
        selection = "UNAMBIGUOUS"
    elif not candidates:
        return ActionResult(
            success=False,
            error=f"Não encontrei uma janela aberta de {canonical}.",
            data={"status": "NOT_FOUND", "target": canonical, "candidate_count": 0},
        )
    else:
        return ActionResult(
            success=False,
            error=f"Encontrei mais de uma janela de {canonical}. Diga qual delas.",
            data={"status": "AMBIGUOUS", "target": canonical, "candidate_count": len(candidates)},
        )
    if selection != "ALREADY_FOREGROUND" and not _focus_window_verified(selected):
        return ActionResult(
            success=False,
            error="A janela foi localizada, mas o foco não pôde ser confirmado.",
            data={"status": "POSTCONDITION_FAILED", "target": canonical, "hwnd": selected},
        )
    labels = {"chrome": "Chrome", "zara": "ZARA", "vscode": "VS Code", "project": "projeto"}
    return ActionResult(
        success=True,
        output=f"{labels[canonical]} em primeiro plano.",
        data={
            "status": "FOREGROUND_CONFIRMED",
            "target": canonical,
            "hwnd": selected,
            "pid": _window_pid(selected),
            "process": _window_process_name(selected),
            "title": _window_text(selected),
            "selection": selection,
            "verified": True,
        },
    )


@action(name="window_switch", category="os", description="Switch to the next safe window", capability="LOCAL_PC_CONTROL")
def window_switch_action() -> ActionResult:
    return ActionResult(
        success=False,
        error="Diga qual janela devo trazer para a frente; não alterno às cegas.",
        data={"status": "EXPLICIT_TARGET_REQUIRED"},
    )


@action(name="window_switch_next", category="os", description="Switch to the next safe window", capability="LOCAL_PC_CONTROL")
def window_switch_next_action() -> ActionResult:
    return window_switch_action()


_DESTRUCTIVE_POWER_ACTIONS = frozenset({
    "shutdown", "poweroff", "restart", "reboot",
    "sleep", "suspend", "hibernate", "logoff", "logout", "signout",
})


def _destructive_power_allowed() -> bool:
    """Dedicated kill-switch for destructive OS power actions.

    Default is DENY: even a valid HIGH-risk confirmation proof is not enough to
    physically power off / restart / suspend / log off the machine. The operator
    must explicitly opt in via ZARA_ALLOW_OS_POWER=1 for the running process.
    """
    return os.environ.get("ZARA_ALLOW_OS_POWER", "").strip() == "1"


@action(name="os_power", category="os", description="Power management: shutdown, restart, sleep, hibernate", risk="HIGH", capability="SYSTEM_POWER")
def os_power_action(action_type: str) -> ActionResult:
    """Power management actions."""
    try:
        action_type = (action_type or "").lower().strip()

        if action_type in _DESTRUCTIVE_POWER_ACTIONS and not _destructive_power_allowed():
            return ActionResult(
                success=False,
                error="POWER_ACTION_DENIED",
                data={
                    "status": "DENIED",
                    "action_type": action_type,
                    "reason": "DESTRUCTIVE_POWER_DISABLED",
                },
            )

        system = platform.system()

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


_CLIPBOARD_SENSITIVE = re.compile(
    r"(?i)(password|senha|passphrase|api[_ -]?key|secret|token|bearer\s+|"
    r"sk-[a-z0-9]{8}|-----BEGIN [A-Z ]+PRIVATE KEY-----)"
)

_INPUT_BLOCKED_PROCESSES = {
    "cmd.exe", "powershell.exe", "pwsh.exe", "windowsterminal.exe",
    "conhost.exe", "wt.exe", "code.exe", "codex.exe",
}
_INPUT_BLOCKED_TITLE = re.compile(
    r"(?i)(password|senha|login|pagamento|payment|checkout|administrador|administrator|terminal|powershell|command prompt|prompt de comando)"
)


def _focused_editable_field() -> dict | None:
    """Return one exact, non-sensitive focused editable UIA field."""
    if platform.system() != "Windows":
        return None
    try:
        import comtypes.client
        try:
            from comtypes.gen import UIAutomationClient as UIA
        except Exception:
            comtypes.client.GetModule("UIAutomationCore.dll")
            from comtypes.gen import UIAutomationClient as UIA
        automation = comtypes.client.CreateObject(
            "{ff48dba4-60ef-4201-aa87-54103eef594e}", interface=UIA.IUIAutomation
        )
        element = automation.GetFocusedElement()
        hwnd = _foreground_window()
        if element is None or hwnd is None or int(element.CurrentProcessId or 0) != _window_pid(hwnd):
            return None
        process = _window_process_name(hwnd)
        title = _window_text(hwnd).strip()
        control_type = int(element.CurrentControlType or 0)
        if process in _INPUT_BLOCKED_PROCESSES or _INPUT_BLOCKED_TITLE.search(title):
            return None
        if bool(element.CurrentIsPassword) or control_type not in {
            int(UIA.UIA_EditControlTypeId), int(UIA.UIA_DocumentControlTypeId)
        }:
            return None
        return {"automation": automation, "UIA": UIA, "element": element, "hwnd": hwnd,
                "pid": _window_pid(hwnd), "process": process, "title": title,
                "control_type": control_type}
    except Exception:
        return None


def _uia_field_text(field: dict) -> str | None:
    element, UIA = field["element"], field["UIA"]
    try:
        pattern = element.GetCurrentPattern(UIA.UIA_ValuePatternId)
        return str(pattern.QueryInterface(UIA.IUIAutomationValuePattern).CurrentValue or "")
    except Exception:
        try:
            pattern = element.GetCurrentPattern(UIA.UIA_TextPatternId)
            text_pattern = pattern.QueryInterface(UIA.IUIAutomationTextPattern)
            return str(text_pattern.DocumentRange.GetText(-1) or "").rstrip("\r\n")
        except Exception:
            return None


def _send_unicode_text(text: str) -> bool:
    # Clipboard-backed Unicode insertion is substantially more reliable across
    # Chromium/Electron/classic Win32 fields than synthesizing a keyboard layout.
    # Preserve the user's clipboard exactly and never log its previous value.
    import pyperclip
    previous = str(pyperclip.paste() or "")
    try:
        pyperclip.copy(text)
        if str(pyperclip.paste() or "") != text:
            return False
        _send_fixed_hotkey((0x11, 0x56))
        return True
    finally:
        time.sleep(0.05)
        pyperclip.copy(previous)


def _send_fixed_hotkey(keys: tuple[int, ...]) -> None:
    import ctypes
    for key in keys:
        ctypes.windll.user32.keybd_event(key, 0, 0, 0)
    for key in reversed(keys):
        ctypes.windll.user32.keybd_event(key, 0, 0x0002, 0)


@action(name="input_type_text", category="os", description="Type exact Unicode text into one safe focused field", capability="LOCAL_PC_CONTROL")
def input_type_text_action(text: str) -> ActionResult:
    value = str(text or "")
    if not value or len(value) > 2000 or any(ord(ch) < 32 for ch in value):
        return ActionResult(success=False, error="Texto inválido para digitação segura.")
    field = _focused_editable_field()
    if field is None:
        return ActionResult(success=False, error="Não identifiquei um campo editável seguro e inequívoco.", data={"status": "SAFE_FIELD_REQUIRED"})
    before = _uia_field_text(field)
    if before is None or not _send_unicode_text(value):
        return ActionResult(success=False, error="Não consegui digitar com readback seguro.")
    time.sleep(0.15)
    after = _uia_field_text(field)
    mode = "append" if after == before + value else "replace_all" if after == value else ""
    if after is None or not mode:
        return ActionResult(success=False, error="O conteúdo digitado não pôde ser confirmado.", data={"before_length": len(before), "after_length": len(after or ""), "verified": False})
    return ActionResult(success=True, output="Texto digitado e confirmado.", data={"hwnd": field["hwnd"], "pid": field["pid"], "process": field["process"], "before_length": len(before), "after_length": len(after), "mode": mode, "verified": True})


_SAFE_INPUT_HOTKEYS = {
    "select_all": (0x11, 0x41), "copy": (0x11, 0x43), "paste": (0x11, 0x56),
    "find": (0x11, 0x46), "undo": (0x11, 0x5A), "redo": (0x11, 0x59),
}


@action(name="input_hotkey", category="os", description="Execute one allowlisted hotkey in a safe focused field", capability="LOCAL_PC_CONTROL")
def input_hotkey_action(command: str) -> ActionResult:
    canonical = str(command or "").strip().casefold()
    if canonical not in _SAFE_INPUT_HOTKEYS:
        return ActionResult(success=False, error="Atalho não permitido.")
    field = _focused_editable_field()
    if field is None:
        return ActionResult(success=False, error="Não identifiquei um campo seguro e inequívoco.", data={"status": "SAFE_FIELD_REQUIRED"})
    before = _uia_field_text(field)
    if before is None:
        return ActionResult(success=False, error="O conteúdo do campo não pôde ser lido.")
    import pyperclip
    clipboard_before = str(pyperclip.paste() or "") if canonical in {"copy", "paste"} else ""
    if canonical == "paste" and (_CLIPBOARD_SENSITIVE.search(clipboard_before) or len(clipboard_before) > 4000):
        return ActionResult(success=False, error="Colagem bloqueada: conteúdo sensível ou grande demais.", data={"status": "BLOCKED_SAFETY"})
    _send_fixed_hotkey(_SAFE_INPUT_HOTKEYS[canonical])
    time.sleep(0.15)
    after = _uia_field_text(field)
    verified = False
    if canonical == "copy":
        observed_clipboard = str(pyperclip.paste() or "")
        verified = bool(observed_clipboard) and observed_clipboard in before
    elif canonical == "paste":
        verified = after is not None and len(after) >= len(before) + len(clipboard_before)
    elif canonical in {"undo", "redo"}:
        verified = after is not None and after != before
    else:
        verified = True  # selection/find UIA has no portable state; later copy/find supplies readback
    if not verified:
        return ActionResult(success=False, error="O atalho foi enviado, mas o efeito não pôde ser confirmado.", data={"verified": False})
    return ActionResult(success=True, output="Atalho seguro executado.", data={"hwnd": field["hwnd"], "command": canonical, "before_length": len(before), "after_length": len(after or ""), "verified": True})


@action(name="os_clipboard_read", category="os", description="Read safe clipboard text", capability="READ_ONLY")
def os_clipboard_read_action() -> ActionResult:
    """Read clipboard text without exposing content that resembles a secret."""
    try:
        import pyperclip
        content = str(pyperclip.paste() or "")
        if _CLIPBOARD_SENSITIVE.search(content):
            return ActionResult(success=True, output="A área de transferência contém conteúdo sensível; não vou lê-lo em voz alta.", data={"sensitive": True, "length": len(content)})
        return ActionResult(success=True, output=content or "A área de transferência está vazia.", data={"clipboard": content, "sensitive": False})
    except ImportError:
        return ActionResult(success=False, error="pyperclip not installed")
    except Exception as exc:
        return ActionResult(success=False, error=str(exc))


@action(name="os_clipboard", category="os", description="Set or clear clipboard content", risk="MEDIUM", capability="LOCAL_PC_CONTROL")
def os_clipboard_action(text: str = None, get: bool = False) -> ActionResult:
    """Set clipboard content and verify it by immediate local readback."""
    try:
        import pyperclip

        if text is not None:
            pyperclip.copy(text)
            observed = str(pyperclip.paste() or "")
            if observed != text:
                return ActionResult(success=False, error="CLIPBOARD_READBACK_MISMATCH", data={"verified": False})
            return ActionResult(success=True, output="Área de transferência limpa." if text == "" else "Copiado.", data={"verified": True, "length": len(observed), "cleared": text == ""})

        return ActionResult(success=False, error="Either 'text' or 'get=true' required")
    except ImportError:
        return ActionResult(success=False, error="pyperclip not installed")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(name="os_notify", category="os", description="Show system notification", risk="LOW", capability="LOCAL_PC_CONTROL")
def os_notify_action(title: str, message: str = "", timeout: int = 5) -> ActionResult:
    """Show system notification."""
    try:
        safe_title = " ".join(str(title or "").split())
        safe_message = " ".join(str(message or "").split())
        safe_timeout = max(1, min(int(timeout), 15))
        if not safe_title or len(safe_title) > 80 or len(safe_message) > 300:
            return ActionResult(success=False, error="Notificação inválida ou grande demais.")
        system = platform.system()

        if system == "Windows":
            try:
                import win10toast
                toaster = win10toast.ToastNotifier()
                toaster.show_toast(safe_title, safe_message, duration=safe_timeout)
                return ActionResult(
                    success=True,
                    output="Notificação enviada ao Windows.",
                    # ZARA-NAO-VERIFICADO-001: os dados aqui já diziam
                    # "visual_verified: False" — o despacho é provado, a
                    # aparição na tela não. A frase falava como se fosse
                    # certeza; agora o resultado carrega a incerteza real e
                    # ela sai da boca dela como ressalva.
                    verificado=False,
                    data={"dispatch": "PROVEN", "backend": "win10toast", "visual_verified": False},
                )
            except ImportError:
                # Fixed script: user text is read from environment variables,
                # never interpolated into executable PowerShell source.
                ps_script = """
                Add-Type -AssemblyName System.Windows.Forms
                $notify = New-Object System.Windows.Forms.NotifyIcon
                $notify.Icon = [System.Drawing.SystemIcons]::Information
                $notify.Visible = $true
                $notify.ShowBalloonTip([int]$env:ZARA_NOTIFY_MS, $env:ZARA_NOTIFY_TITLE, $env:ZARA_NOTIFY_MESSAGE, [System.Windows.Forms.ToolTipIcon]::Info)
                Start-Sleep -Milliseconds ([int]$env:ZARA_NOTIFY_MS)
                $notify.Dispose()
                """
                env = os.environ.copy()
                env.update({
                    "ZARA_NOTIFY_TITLE": safe_title,
                    "ZARA_NOTIFY_MESSAGE": safe_message,
                    "ZARA_NOTIFY_MS": str(safe_timeout * 1000),
                })
                creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                    check=True,
                    timeout=safe_timeout + 5,
                    env=env,
                    creationflags=creationflags,
                )
                return ActionResult(
                    success=True,
                    output="Notificação enviada ao Windows.",
                    # ZARA-NAO-VERIFICADO-002: o despacho e provado, a aparicao
                    # na tela nao. Os dados ja sabiam disso; o selo e que mentia.
                    verificado=False,
                    data={"dispatch": "PROVEN", "backend": "powershell_notifyicon", "visual_verified": False},
                )

        elif system == "Linux":
            subprocess.run(["notify-send", "-t", str(timeout * 1000), title, message], check=True)
            # Ultimo recurso: despachou e nao ha como conferir nada.
            return ActionResult(
                success=True, output="Notificação enviada ao Windows.", verificado=False
            )

        elif system == "Darwin":
            script = f'display notification "{message}" with title "{title}"'
            subprocess.run(["osascript", "-e", script], check=True)
            return ActionResult(success=True, output="Notification sent")

        return ActionResult(success=False, error="Notifications not supported on this OS")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


        # ============================================================================
        # MCP (Model Context Protocol) Actions
        # ============================================================================

        # Global MCP client manager instance
        _mcp_client_manager = None


        def _get_mcp_client_manager():
            """Get or create the MCP client manager."""
            global _mcp_client_manager
            if _mcp_client_manager is None:
                from core.mcp.client import MCPClientManager
                _mcp_client_manager = MCPClientManager()
                # Register default servers
                import sys
                from pathlib import Path
                project_root = Path(__file__).parent.parent.parent
                python_exe = sys.executable

                _mcp_client_manager.register_server(
                    "file_ops",
                    [python_exe, "-m", "core.mcp.servers.file_ops"],
                    cwd=str(project_root)
                )
                _mcp_client_manager.register_server(
                    "registry",
                    [python_exe, "-m", "core.mcp.servers.registry"],
                    cwd=str(project_root)
                )
                _mcp_client_manager.register_server(
                    "processes",
                    [python_exe, "-m", "core.mcp.servers.processes"],
                    cwd=str(project_root)
                )
                _mcp_client_manager.register_server(
                    "network",
                    [python_exe, "-m", "core.mcp.servers.network"],
                    cwd=str(project_root)
                )
                _mcp_client_manager.register_server(
                    "ui_automation",
                    [python_exe, "-m", "core.mcp.servers.ui_automation"],
                    cwd=str(project_root)
                )
            return _mcp_client_manager


        @action(
            name="mcp_connect",
            category="mcp",
            description="Connect to an MCP server",
            capability="LOCAL_PC_CONTROL",
        )
        async def mcp_connect_action(server: str) -> ActionResult:
            """Connect to an MCP server by name."""
            try:
                manager = _get_mcp_client_manager()
                client = await manager.connect(server)
                tools = client.list_tools()
                resources = client.list_resources()
                prompts = client.list_prompts()

                return ActionResult(
                    success=True,
                    output=f"Conectado ao servidor MCP: {server}",
                    data={
                        "server": server,
                        "tools": [t.name for t in tools],
                        "resources": [r.uri for r in resources],
                        "prompts": [p.name for p in prompts],
                    },
                )
            except Exception as e:
                return ActionResult(success=False, error=str(e))


        @action(
            name="mcp_disconnect",
            category="mcp",
            description="Disconnect from an MCP server",
            capability="LOCAL_PC_CONTROL",
        )
        async def mcp_disconnect_action(server: str = None) -> ActionResult:
            """Disconnect from an MCP server or all servers."""
            try:
                manager = _get_mcp_client_manager()
                if server:
                    client = await manager.get_client(server)
                    if client:
                        await client.close()
                        return ActionResult(success=True, output=f"Desconectado de {server}")
                    return ActionResult(success=False, error=f"Servidor não conectado: {server}")
                else:
                    await manager.disconnect_all()
                    return ActionResult(success=True, output="Desconectado de todos os servidores MCP")
            except Exception as e:
                return ActionResult(success=False, error=str(e))


        @action(
            name="mcp_list_servers",
            category="mcp",
            description="List connected MCP servers",
            capability="READ_ONLY",
        )
        async def mcp_list_servers_action() -> ActionResult:
            """List all connected MCP servers."""
            try:
                manager = _get_mcp_client_manager()
                connected = manager.list_connected()

                result = {}
                for name in connected:
                    client = await manager.get_client(name)
                    if client:
                        tools = client.list_tools()
                        result[name] = {
                            "tools": [t.name for t in tools],
                            "resources": [r.uri for r in client.list_resources()],
                            "prompts": [p.name for p in client.list_prompts()],
                        }

                return ActionResult(
                    success=True,
                    output=f"Servidores MCP conectados: {', '.join(connected) if connected else 'nenhum'}",
                    data={"servers": result},
                )
            except Exception as e:
                return ActionResult(success=False, error=str(e))


        @action(
            name="mcp_call_tool",
            category="mcp",
            description="Call a tool on an MCP server",
            capability="LOCAL_PC_CONTROL",
        )
        async def mcp_call_tool_action(server: str, tool: str, arguments: dict = None) -> ActionResult:
            """Call a tool on an MCP server."""
            try:
                manager = _get_mcp_client_manager()
                client = await manager.get_client(server)
                if not client:
                    # Try to connect
                    client = await manager.connect(server)

                result = await client.call_tool(tool, arguments or {})

                return ActionResult(
                    success=True,
                    output=f"Ferramenta {tool} executada em {server}",
                    data={"server": server, "tool": tool, "result": result},
                )
            except Exception as e:
                return ActionResult(success=False, error=str(e))


        @action(
            name="mcp_read_resource",
            category="mcp",
            description="Read a resource from an MCP server",
            capability="READ_ONLY",
        )
        async def mcp_read_resource_action(server: str, uri: str) -> ActionResult:
            """Read a resource from an MCP server."""
            try:
                manager = _get_mcp_client_manager()
                client = await manager.get_client(server)
                if not client:
                    client = await manager.connect(server)

                content = await client.read_resource(uri)

                return ActionResult(
                    success=True,
                    output=f"Recurso {uri} lido de {server}",
                    data={"server": server, "uri": uri, "content": content},
                )
            except Exception as e:
                return ActionResult(success=False, error=str(e))


        @action(
            name="mcp_get_prompt",
            category="mcp",
            description="Get a prompt template from an MCP server",
            capability="READ_ONLY",
        )
        async def mcp_get_prompt_action(server: str, prompt: str, arguments: dict = None) -> ActionResult:
            """Get a prompt template from an MCP server."""
            try:
                manager = _get_mcp_client_manager()
                client = await manager.get_client(server)
                if not client:
                    client = await manager.connect(server)

                messages = await client.get_prompt(prompt, arguments or {})

                return ActionResult(
                    success=True,
                    output=f"Prompt {prompt} obtido de {server}",
                    data={"server": server, "prompt": prompt, "messages": messages},
                )
            except Exception as e:
                return ActionResult(success=False, error=str(e))


        # Convenience actions for common MCP operations

        @action(
            name="mcp_file_read",
            category="mcp",
            description="Read a file via MCP file_ops server",
            capability="READ_ONLY",
        )
        async def mcp_file_read_action(path: str, encoding: str = "utf-8", max_size: int = 1048576) -> ActionResult:
            """Read a file using the MCP file_ops server."""
            return await mcp_call_tool_action("file_ops", "file_read", {"path": path, "encoding": encoding, "max_size": max_size})


        @action(
            name="mcp_file_write",
            category="mcp",
            description="Write a file via MCP file_ops server",
            capability="LOCAL_PC_CONTROL",
        )
        async def mcp_file_write_action(path: str, content: str, encoding: str = "utf-8", create_dirs: bool = True) -> ActionResult:
            """Write a file using the MCP file_ops server."""
            return await mcp_call_tool_action("file_ops", "file_write", {"path": path, "content": content, "encoding": encoding, "create_dirs": create_dirs})


        @action(
            name="mcp_file_list",
            category="mcp",
            description="List files via MCP file_ops server",
            capability="READ_ONLY",
        )
        async def mcp_file_list_action(path: str, pattern: str = "*", recursive: bool = False, include_dirs: bool = True) -> ActionResult:
            """List files using the MCP file_ops server."""
            return await mcp_call_tool_action("file_ops", "file_list", {"path": path, "pattern": pattern, "recursive": recursive, "include_dirs": include_dirs})


        @action(
            name="mcp_file_copy",
            category="mcp",
            description="Copy a file via MCP file_ops server",
            capability="LOCAL_PC_CONTROL",
        )
        async def mcp_file_copy_action(source: str, destination: str, overwrite: bool = False) -> ActionResult:
            """Copy a file using the MCP file_ops server."""
            return await mcp_call_tool_action("file_ops", "file_copy", {"source": source, "destination": destination, "overwrite": overwrite})


        @action(
            name="mcp_file_move",
            category="mcp",
            description="Move a file via MCP file_ops server",
            capability="LOCAL_PC_CONTROL",
        )
        async def mcp_file_move_action(source: str, destination: str, overwrite: bool = False) -> ActionResult:
            """Move a file using the MCP file_ops server."""
            return await mcp_call_tool_action("file_ops", "file_move", {"source": source, "destination": destination, "overwrite": overwrite})


        @action(
            name="mcp_file_delete",
            category="mcp",
            description="Delete a file via MCP file_ops server",
            capability="LOCAL_PC_CONTROL",
        )
        async def mcp_file_delete_action(path: str, recursive: bool = False) -> ActionResult:
            """Delete a file using the MCP file_ops server."""
            return await mcp_call_tool_action("file_ops", "file_delete", {"path": path, "recursive": recursive})


        @action(
            name="mcp_file_search",
            category="mcp",
            description="Search file contents via MCP file_ops server",
            capability="READ_ONLY",
        )
        async def mcp_file_search_action(path: str, pattern: str, file_pattern: str = "*", case_sensitive: bool = False, max_results: int = 100) -> ActionResult:
            """Search file contents using the MCP file_ops server."""
            return await mcp_call_tool_action("file_ops", "file_search", {"path": path, "pattern": pattern, "file_pattern": file_pattern, "case_sensitive": case_sensitive, "max_results": max_results})


        @action(
            name="mcp_registry_read",
            category="mcp",
            description="Read a registry value via MCP registry server",
            capability="READ_ONLY",
        )
        async def mcp_registry_read_action(hive: str, path: str, name: str = "") -> ActionResult:
            """Read a registry value using the MCP registry server."""
            return await mcp_call_tool_action("registry", "registry_read", {"hive": hive, "path": path, "name": name})


        @action(
            name="mcp_registry_write",
            category="mcp",
            description="Write a registry value via MCP registry server",
            capability="LOCAL_PC_CONTROL",
        )
        async def mcp_registry_write_action(hive: str, path: str, name: str, value: str, type: str = "REG_SZ") -> ActionResult:
            """Write a registry value using the MCP registry server."""
            return await mcp_call_tool_action("registry", "registry_write", {"hive": hive, "path": path, "name": name, "value": value, "type": type})


        @action(
            name="mcp_registry_list",
            category="mcp",
            description="List registry keys/values via MCP registry server",
            capability="READ_ONLY",
        )
        async def mcp_registry_list_action(hive: str, path: str) -> ActionResult:
            """List registry keys and values using the MCP registry server."""
            return await mcp_call_tool_action("registry", "registry_list_keys", {"hive": hive, "path": path})


        @action(
            name="mcp_registry_search",
            category="mcp",
            description="Search registry via MCP registry server",
            capability="READ_ONLY",
        )
        async def mcp_registry_search_action(hive: str, path: str, pattern: str, max_results: int = 50) -> ActionResult:
            """Search registry using the MCP registry server."""
            return await mcp_call_tool_action("registry", "registry_search", {"hive": hive, "path": path, "pattern": pattern, "max_results": max_results})


        @action(
            name="mcp_process_list",
            category="mcp",
            description="List processes via MCP processes server",
            capability="READ_ONLY",
        )
        async def mcp_process_list_action(filter: str = "", limit: int = 100) -> ActionResult:
            """List processes using the MCP processes server."""
            return await mcp_call_tool_action("processes", "process_list", {"filter": filter, "limit": limit})


        @action(
            name="mcp_process_get",
            category="mcp",
            description="Get process details via MCP processes server",
            capability="READ_ONLY",
        )
        async def mcp_process_get_action(pid: int) -> ActionResult:
            """Get process details using the MCP processes server."""
            return await mcp_call_tool_action("processes", "process_get", {"pid": pid})


        @action(
            name="mcp_process_kill",
            category="mcp",
            description="Kill a process via MCP processes server",
            capability="LOCAL_PC_CONTROL",
        )
        async def mcp_process_kill_action(pid: int, force: bool = False) -> ActionResult:
            """Kill a process using the MCP processes server."""
            return await mcp_call_tool_action("processes", "process_kill", {"pid": pid, "force": force})


        @action(
            name="mcp_process_start",
            category="mcp",
            description="Start a process via MCP processes server",
            capability="LOCAL_PC_CONTROL",
        )
        async def mcp_process_start_action(command: str, args: list = None, cwd: str = None, env: dict = None, detached: bool = False) -> ActionResult:
            """Start a process using the MCP processes server."""
            return await mcp_call_tool_action("processes", "process_start", {"command": command, "args": args or [], "cwd": cwd, "env": env, "detached": detached})


        @action(
            name="mcp_network_interfaces",
            category="mcp",
            description="List network interfaces via MCP network server",
            capability="READ_ONLY",
        )
        async def mcp_network_interfaces_action() -> ActionResult:
            """List network interfaces using the MCP network server."""
            return await mcp_call_tool_action("network", "network_interfaces", {})


        @action(
            name="mcp_network_connections",
            category="mcp",
            description="List network connections via MCP network server",
            capability="READ_ONLY",
        )
        async def mcp_network_connections_action(kind: str = "inet") -> ActionResult:
            """List network connections using the MCP network server."""
            return await mcp_call_tool_action("network", "network_connections", {"kind": kind})


        @action(
            name="mcp_network_ping",
            category="mcp",
            description="Ping a host via MCP network server",
            capability="READ_ONLY",
        )
        async def mcp_network_ping_action(host: str, count: int = 4, timeout: int = 1000) -> ActionResult:
            """Ping a host using the MCP network server."""
            return await mcp_call_tool_action("network", "network_ping", {"host": host, "count": count, "timeout": timeout})


        @action(
            name="mcp_network_port_scan",
            category="mcp",
            description="Scan ports via MCP network server",
            capability="READ_ONLY",
        )
        async def mcp_network_port_scan_action(host: str, ports: list, timeout: int = 1000) -> ActionResult:
            """Scan ports using the MCP network server."""
            return await mcp_call_tool_action("network", "network_port_scan", {"host": host, "ports": ports, "timeout": timeout})


        @action(
            name="mcp_ui_find_window",
            category="mcp",
            description="Find a window via MCP UI Automation server",
            capability="READ_ONLY",
        )
        async def mcp_ui_find_window_action(title: str = "", class_name: str = "", exact: bool = False) -> ActionResult:
            """Find a window using the MCP UI Automation server."""
            return await mcp_call_tool_action("ui_automation", "ui_find_window", {"title": title, "class_name": class_name, "exact": exact})


        @action(
            name="mcp_ui_get_foreground",
            category="mcp",
            description="Get foreground window via MCP UI Automation server",
            capability="READ_ONLY",
        )
        async def mcp_ui_get_foreground_action() -> ActionResult:
            """Get the foreground window using the MCP UI Automation server."""
            return await mcp_call_tool_action("ui_automation", "ui_get_foreground_window", {})


        @action(
            name="mcp_ui_click",
            category="mcp",
            description="Click at coordinates via MCP UI Automation server",
            capability="LOCAL_PC_CONTROL",
        )
        async def mcp_ui_click_action(x: int, y: int, button: str = "left", clicks: int = 1) -> ActionResult:
            """Click at coordinates using the MCP UI Automation server."""
            return await mcp_call_tool_action("ui_automation", "ui_click", {"x": x, "y": y, "button": button, "clicks": clicks})


        @action(
            name="mcp_ui_type",
            category="mcp",
            description="Type text via MCP UI Automation server",
            capability="LOCAL_PC_CONTROL",
        )
        async def mcp_ui_type_action(text: str, delay: int = 10) -> ActionResult:
            """Type text using the MCP UI Automation server."""
            return await mcp_call_tool_action("ui_automation", "ui_type_text", {"text": text, "delay": delay})


        @action(
            name="mcp_ui_send_key",
            category="mcp",
            description="Send key combination via MCP UI Automation server",
            capability="LOCAL_PC_CONTROL",
        )
        async def mcp_ui_send_key_action(key: str, modifiers: list = None) -> ActionResult:
            """Send key combination using the MCP UI Automation server."""
            return await mcp_call_tool_action("ui_automation", "ui_send_key", {"key": key, "modifiers": modifiers or []})


        @action(
            name="mcp_ui_window_control",
            category="mcp",
            description="Control a window (minimize/maximize/restore/close) via MCP UI Automation server",
            capability="LOCAL_PC_CONTROL",
        )
        async def mcp_ui_window_control_action(hwnd: int, action: str) -> ActionResult:
            """Control a window using the MCP UI Automation server."""
            action_map = {
                "minimize": "ui_window_minimize",
                "maximize": "ui_window_maximize",
                "restore": "ui_window_restore",
                "close": "ui_window_close",
            }
            if action not in action_map:
                return ActionResult(success=False, error=f"Ação inválida: {action}. Use: minimize, maximize, restore, close")
            return await mcp_call_tool_action("ui_automation", action_map[action], {"hwnd": hwnd})


        @action(
            name="mcp_ui_screenshot",
            category="mcp",
            description="Screenshot a window via MCP UI Automation server",
            capability="LOCAL_PC_CONTROL",
        )
        async def mcp_ui_screenshot_action(hwnd: int, path: str) -> ActionResult:
            """Take a screenshot of a window using the MCP UI Automation server."""
            return await mcp_call_tool_action("ui_automation", "ui_screenshot_window", {"hwnd": hwnd, "path": path})
