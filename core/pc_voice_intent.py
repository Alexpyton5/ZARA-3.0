#!/usr/bin/env python3
"""
ZARA-PC-CONTROL-VOICE-BINDING-001

PC voice intent detector. Maps natural language Windows commands to existing PC control actions.
With Supercerebro OFF, detected intents are blocked (BLOCKED_PC_CONTROL).
"""

import re
from dataclasses import dataclass

_LOCAL_DETERMINISTIC_ACTIONS = frozenset({
    "os_app", "os_open", "os_volume", "audio_mute", "audio_unmute",
    "os_brightness_absolute", "os_brightness_up", "os_brightness_down",
    "os_night_light_on", "os_night_light_off", "os_wifi_on", "os_wifi_off",
    "os_bluetooth_on", "os_bluetooth_off", "media_play_pause", "youtube_pause", "youtube_resume", "youtube_seek", "youtube_now_playing", "youtube_next", "youtube_another_by_artist", "media_next",
    "media_previous", "window_minimize", "window_maximize", "window_restore", "window_focus_named",
    "window_move", "window_resize_larger", "window_close",
    "window_switch", "window_switch_next", "youtube_open", "youtube_search", "youtube_play_by_name", "spotify_search",
    "youtube_skip_ad", "browser_new_tab", "browser_back", "browser_forward", "browser_read_page", "browser_scroll", "browser_close_tab",
    "vision_screenshot", "os_notify",
    "os_close_safe_app",
    "system_time", "system_info", "system_metrics", "system_processes", "os_clipboard", "os_clipboard_read",
    "input_type_text", "input_hotkey",
    "audio_status",
})


@dataclass
class PcVoiceResult:
    is_pc_intent: bool
    action: str = ""
    param: str = ""
    blocked: bool = False
    physical_effect: int = 0
    reply: str = ""
    contextual: bool = False


class PcVoiceIntentDetector:
    """Detect PC control voice commands and map to existing actions."""

    def __init__(
        self,
        pc_control_allowed: bool = False,
        volume_context_level: int | None = None,
        window_context_available: bool = False,
        folder_context: str | None = None,
    ):
        self.pc_control_allowed = pc_control_allowed
        self.volume_context_level = volume_context_level
        self.window_context_available = window_context_available
        self.folder_context = folder_context

        # Intent patterns
        self.patterns = [
            # Clipboard writes stay MEDIUM and are confirmed conversationally by IPCHandler.
            (r'^(?:zara[,\s]+)?(?:o\s+que\s+(?:est[áa]|tem)|leia\s+o\s+que\s+est[áa])\s+(?:na\s+)?(?:área|area)\s+de\s+transfer[êe]ncia\s*[.!?]*$',
             self._clipboard_read, "os_clipboard_read", "read"),
            (r'^(?:zara[,\s]+)?(?:limpe|limpa|esvazie)\s+(?:a\s+)?(?:área|area)\s+de\s+transfer[êe]ncia\s*[.!?]*$',
             self._clipboard_clear, "os_clipboard", "__CLEAR__"),
            (r'^(?:zara[,\s]+)?(?:coloque|coloca|copie|copia)\s+(.+?)\s+(?:na|para\s+a)\s+(?:área|area)\s+de\s+transfer[êe]ncia\s*[.!?]*$',
             self._clipboard_text, "os_clipboard", None),
            # Open apps
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|inicie|inicia|iniciar|executa|execute|executar|quero\s+abrir)\s+'
             r'(?:a\s+)?(?:calculadora|calc|calculator)\s*[.!?]*$',
             self._open_calc, "os_app", "calculator"),
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|inicie|inicia|iniciar|executa|execute|executar|quero\s+abrir)\s+'
             r'(?:o\s+)?(?:bloco\s+de\s+notas|notepad)\s*[.!?]*$',
             self._open_notepad, "os_app", "notepad"),
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|inicie|inicia|iniciar|executa|execute|executar|quero\s+abrir)\s+'
             r'(?:o\s+)?(?:google\s+chrome|chrome)\s*[.!?]*$',
             self._open_chrome, "os_app", "chrome"),
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|inicie|inicia|iniciar|execute)\s+'
             r'(?:o\s+)?(?:gerenciador\s+de\s+tarefas|task\s*manager)\s*[.!?]*$',
             self._open_task_manager, "os_app", "task_manager"),
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|inicie|execute)\s+(?:as\s+)?configurações\s*[.!?]*$',
             self._open_settings, "os_app", "settings"),
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|inicie|execute)\s+(?:o\s+)?paint\s*[.!?]*$',
             self._open_paint, "os_app", "paint"),
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|inicie|execute)\s+(?:a\s+)?(?:ferramenta\s+de\s+captura|snipping\s*tool)\s*[.!?]*$',
             self._open_snipping_tool, "os_app", "snipping_tool"),
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|inicie|execute)\s+(?:o\s+)?(?:microsoft\s+)?edge\s*[.!?]*$',
             self._open_edge, "os_app", "edge"),
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|inicie|execute)\s+(?:o\s+)?spotify\s*[.!?]*$',
             self._open_spotify, "os_app", "spotify"),
            (r'^(?:zara[,\s]+)?(?:feche|fecha|fechar)\s+(?:a\s+)?calculadora\s*[.!?]*$',
             self._close_calculator, "os_close_safe_app", "calculator"),
            (r'^(?:zara[,\s]+)?(?:feche|fecha|fechar)\s+(?:o\s+)?gerenciador\s+de\s+tarefas\s*[.!?]*$',
             self._close_task_manager, "os_close_safe_app", "task_manager"),
            (r'^(?:zara[,\s]+)?(?:feche|fecha|fechar)\s+(?:as\s+)?configurações\s*[.!?]*$',
             self._close_settings, "os_close_safe_app", "settings"),
            (r'^(?:zara[,\s]+)?(?:feche|fecha|fechar)\s+(?:o\s+)?spotify\s*[.!?]*$',
             self._close_spotify, "os_close_safe_app", "spotify"),
            (r'^(?:zara[,\s]+)?(?:feche|fecha|fechar)\s+(?:o\s+)?(?:bloco\s+de\s+notas|notepad)\s*[.!?]*$',
             self._close_notepad, "os_close_safe_app", "notepad"),
            (r'^(?:zara[,\s]+)?(?:feche|fecha|fechar)\s+(?:o\s+)?paint\s*[.!?]*$',
             self._close_paint, "os_close_safe_app", "paint"),
            (r'^(?:zara[,\s]+)?(?:feche|fecha|fechar)\s+(?:a\s+)?(?:ferramenta\s+de\s+captura|snipping\s*tool)\s*[.!?]*$',
             self._close_snipping_tool, "os_close_safe_app", "snipping_tool"),
            (r'^(?:zara[,\s]+)?(?:feche|fecha|fechar)\s+(?:o\s+)?(?:google\s+chrome|chrome)\s*[.!?]*$',
             self._close_chrome, "os_close_safe_app", "chrome"),
            (r'^(?:zara[,\s]+)?(?:feche|fecha|fechar)\s+(?:o\s+)?(?:microsoft\s+)?edge\s*[.!?]*$',
             self._close_edge, "os_close_safe_app", "edge"),
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|mostre|v[áa]\s+para)\s+(?:meus?\s+)?downloads\s*[.!?]*$',
             self._open_downloads, "os_open", "downloads"),
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|mostre|v[áa]\s+para)\s+(?:meus?\s+)?(?:documentos|documents)\s*[.!?]*$',
             self._open_documents, "os_open", "documents"),
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|mostre|v[áa]\s+para)\s+(?:a\s+)?(?:área\s+de\s+trabalho|desktop)\s*[.!?]*$',
             self._open_desktop, "os_open", "desktop"),
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|mostre|v[áa]\s+para)\s+(?:minhas?\s+)?(?:imagens|pictures)\s*[.!?]*$',
             self._open_pictures, "os_open", "pictures"),
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|mostre|v[áa]\s+para)\s+(?:a\s+)?(?:pasta\s+da\s+zara|zara\s+folder)\s*[.!?]*$',
             self._open_zara_folder, "os_open", "zara_root"),

            # Browser destinations remain data passed to closed actions.
            (r'^(?:zara[,\s]+)?(?:abra|abre|acesse)\s+(?:o\s+)?site\s+da\s+openai\s*[.!?]*$',
             self._open_openai, "browser_open_url", "https://openai.com/"),
            (r'^(?:zara[,\s]+)?(?:abra|abre|acesse|v[áa]\s+para)\s+((?:https?://)?[^\s]+\.[^\s]+)\s*[.!?]*$',
             self._open_url, "browser_open_url", None),

            # Closed media destinations; query is data and the host is fixed.
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|acesse|v[Ã¡a]\s+para)\s+(?:o\s+)?youtube\s*[.!?]*$',
             self._browser_native, "youtube_open", "youtube"),
            (r'^(?:zara[,\s]+)?(?:pesquise?|procure|busque?)\s+(.+?)\s+(?:no|na)\s+youtube\s*[.!?]*$',
             self._media_query, "youtube_search", None),
            (r'^(?:zara[,\s]+)?(?:toque|toca|coloque|bote|quero\s+ouvir)\s+(.+?)\s*[.!?]*$',
             self._media_query, "youtube_play_by_name", None),
            (r'^(?:zara[,\s]+)?(?:o\s+que\s+(?:est[áa]\s+tocando|est[áa]\s+passando)|qual\s+(?:m[úu]sica|v[íi]deo)\s+est[áa]\s+tocando)\s*[.!?]*$',
             self._youtube_now_playing, "youtube_now_playing", "current"),
            (r'^(?:zara[,\s]+)?(?:(?:n[ãa]o\s+gostei(?:\s+dessa\s+m[úu]sica)?[,\s]+)?(?:coloque|coloca|bote|bota)\s+outra\s+(?:dele|dela|desse\s+artista)|outra\s+desse\s+artista)\s*[.!?]*$',
             self._youtube_another, "youtube_another_by_artist", "current_artist"),
            (r'^(?:zara[,\s]+)?(?:pesquise?|procure|busque?)\s+(.+?)\s+(?:no|na)\s+spotify\s*[.!?]*$',
             self._media_query, "spotify_search", None),
            (r'^(?:zara[,\s]+)?(?:pule|pular)\s+(?:o\s+)?an[úu]ncio\s*[.!?]*$',
             self._youtube_skip_ad, "youtube_skip_ad", "skip"),
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir)\s+(?:uma\s+)?nova\s+(?:guia|aba)\s*[.!?]*$',
             self._browser_native, "browser_new_tab", "new_tab"),
            (r'^(?:zara[,\s]+)?(?:volte|voltar)\s+(?:no|pelo)\s+navegador\s*[.!?]*$',
             self._browser_native, "browser_back", "back"),
            (r'^(?:zara[,\s]+)?(?:avance|avançar)\s+(?:no|pelo)\s+navegador\s*[.!?]*$',
             self._browser_native, "browser_forward", "forward"),
            (r'^(?:zara[,\s]+)?(?:feche|fecha)\s+(?:essa|esta|a)\s+(?:guia|aba)\s*[.!?]*$',
             self._browser_native, "browser_close_tab", "close"),
            (r'^(?:zara[,\s]+)?(?:(?:o\s+que\s+diz)|(?:resuma|resume)|(?:qual\s+[ée]\s+o\s+assunto\s+d[ae]))\s+(?:essa|esta|a)\s+p[áa]gina\s*[.!?]*$',
             self._browser_native, "browser_read_page", "read"),
            (r'^(?:zara[,\s]+)?(?:tire|faça|capture)\s+(?:uma\s+)?(?:captura\s+de\s+tela|screenshot)\s*[.!?]*$',
             self._screenshot, "vision_screenshot", "full"),
            (r'^(?:zara[,\s]+)?(?:mostre|envie|crie)\s+(?:uma\s+)?notificação(?:\s+dizendo)?\s+(.+?)\s*[.!?]*$',
             self._notification_message, "os_notify", None),

            # Read-only system truth.
            (r'^(?:zara[,\s]+)?(?:que\s+horas\s+(?:s[ãa]o|sao)|qual\s+(?:é|e)\s+a\s+hora|hora\s+local)\s*[.!?]*$',
             self._system_info, "system_time", "local"),
            (r'^(?:zara[,\s]+)?(?:como\s+est[áa]\s+o\s+(?:computador|pc)|status\s+do\s+(?:computador|pc)|uso\s+de\s+(?:cpu|ram|mem[óo]ria))\s*[.!?]*$',
             self._system_metrics, "system_metrics", "summary"),
            (r'^(?:zara[,\s]+)?(?:mostre|diga|quais\s+s[ãa]o)\s+(?:as\s+)?informaç[õo]es\s+do\s+sistema\s*[.!?]*$',
             self._system_info, "system_info", "basic"),
            (r'^(?:zara[,\s]+)?(?:liste|mostre|quais)\s+(?:os\s+)?processos(?:\s+est[ãa]o\s+rodando)?\s*[.!?]*$',
             self._system_processes, "system_processes", "top"),

            # Search
            (r'\b(pesquise?|procure|search|busque?)\s+(por\s+)?(.+)\b',
             self._search, "browser_search", None),

            # Volume
            (r'\b(?:coloque|coloca|defina|ponha|deixe|set)\s+(?:o\s+)?volume\s+(?:em|para|a)\s+(\d{1,3})\s*%?\b',
             self._volume_level, "os_volume", None),
            (r'\bvolume\s+(?:em\s+)?(\d{1,3})\s*%?\b',
             self._volume_level, "os_volume", None),
            # Volume (aceita imperativo E infinitivo: "aumente/aumentar/aumenta",
            # "diminua/diminuir", "suba/subir", "baixe/baixar/abaixar").
            (r'\b(?:aument[ae]r?|suba|subir|subo|up|mais\s+volume|increase?)\s+(?:o\s+)?volume\b',
             self._volume_up, "os_volume", "up"),
            (r'\b(?:diminu(?:[ae]r?|ir?)|baix[ae]r?|abaix[ae]r?|down|menos\s+volume|decrease?|lower)\s+(?:o\s+)?volume\b',
             self._volume_down, "os_volume", "down"),

            # Media controls are deliberately anchored to avoid collisions
            # with ordinary conversation such as "faça uma pausa no projeto".
            (r'^(?:zara[,\s]+)?(?:pause(?:\s+(?:a\s+)?música)?|pausa)\s*[.!?]*$',
             self._youtube_pause, "youtube_pause", "pause"),
            (r'^(?:zara[,\s]+)?(?:continue(?:\s+(?:a\s+)?música)?|continua|play)\s*[.!?]*$',
             self._youtube_resume, "youtube_resume", "resume"),
            (r'^(?:zara[,\s]+)?(?:avance|avança|adianta)\s+(\d{1,4})\s+segundos?\s*[.!?]*$',
             self._youtube_seek_forward, "youtube_seek", None),
            (r'^(?:zara[,\s]+)?(?:volte|volta|retroceda)\s+(\d{1,4})\s+segundos?\s*[.!?]*$',
             self._youtube_seek_backward, "youtube_seek", None),
            (r'^(?:zara[,\s]+)?(?:volte|volta)\s+um\s+pouco\s*[.!?]*$',
             self._youtube_seek_small_back, "youtube_seek", "-10"),
            (r'^(?:zara[,\s]+)?(?:recomece|recomeça|reinicie|volte\s+ao\s+início)(?:\s+(?:essa|a)\s+(?:música|faixa|vídeo))?\s*[.!?]*$',
             self._youtube_restart, "youtube_seek", "restart"),
            (r'^(?:zara[,\s]+)?(?:próxima(?:\s+música)?|pule\s+essa)\s*[.!?]*$',
             self._media_next, "youtube_next", "next"),
            (r'^(?:zara[,\s]+)?(?:anterior|música\s+anterior|volt[ae]\s+(?:a\s+)?(?:música|faixa))\s*[.!?]*$',
             self._media_previous, "media_previous", "previous"),
            (r'^(?:zara[,\s]+)?(?:mute|(?:ativ[ae]r?|lig[ae]r?|coloc[ae]r?)\s+(?:o\s+)?mudo)\s*[.!?]*$',
             self._audio_mute, "audio_mute", "mute"),
            (r'^(?:zara[,\s]+)?(?:tir[ae]r?\s+(?:do\s+|o\s+)?mudo|retir[ae]r?\s+do\s+mudo|desativ[ae]r?\s+(?:o\s+)?mudo)\s*[.!?]*$',
             self._audio_unmute, "audio_unmute", "unmute"),
            (r'^(?:zara[,\s]+)?(?:qual\s+(?:é|e)\s+o\s+dispositivo\s+de\s+áudio|status\s+d[eo]\s+áudio|como\s+está\s+o\s+áudio)\s*[.!?]*$',
             self._audio_status, "audio_status", "status"),

            # Silent Windows radios (WinRT API, no Quick Settings flyout).
            (r'^(?:zara[,\s]+)?(?:ative|ligue)\s+(?:o\s+)?wi-?fi\s*[.!?]*$',
             self._radio_on, "os_wifi_on", "on"),
            (r'^(?:zara[,\s]+)?(?:desative|desligue)\s+(?:o\s+)?wi-?fi\s*[.!?]*$',
             self._radio_off, "os_wifi_off", "off"),
            (r'^(?:zara[,\s]+)?(?:ative|ligue)\s+(?:o\s+)?bluetooth\s*[.!?]*$',
             self._radio_on, "os_bluetooth_on", "on"),
            (r'^(?:zara[,\s]+)?(?:desative|desligue)\s+(?:o\s+)?bluetooth\s*[.!?]*$',
             self._radio_off, "os_bluetooth_off", "off"),

            # Brightness and night-light controls.
            (r'^(?:zara[,\s]+)?(?:brilho\s+(?:em\s+)?|coloque\s+(?:o\s+)?brilho\s+(?:em\s+)?|deixe\s+a\s+tela\s+em\s+)(\d{1,3})\s*%?\s*[.!?]*$',
             self._brightness_level, "os_brightness_absolute", None),
            (r'^(?:zara[,\s]+)?(?:aumente\s+(?:o\s+)?brilho|(?:um\s+pouco\s+)?mais\s+claro)\s*[.!?]*$',
             self._brightness_up, "os_brightness_up", "up"),
            (r'^(?:zara[,\s]+)?(?:diminua\s+(?:o\s+)?brilho|(?:um\s+pouco\s+)?mais\s+escuro)\s*[.!?]*$',
             self._brightness_down, "os_brightness_down", "down"),
            (r'^(?:zara[,\s]+)?(?:ative|ativar|ligue|ligar)\s+(?:(?:a\s+)?luz|(?:o\s+)?modo)\s+noturn[oa]\s*[.!?]*$',
             self._night_light_on, "os_night_light_on", "on"),
            (r'^(?:zara[,\s]+)?(?:desative|desativar|desligue|desligar)\s+(?:(?:a\s+)?luz|(?:o\s+)?modo)\s+noturn[oa]\s*[.!?]*$',
             self._night_light_off, "os_night_light_off", "off"),

            # Window controls are anchored and never include close/Alt+F4.
            (r'^(?:zara[,\s]+)?(?:minimize(?:\s+(?:a|esta)\s+janela)?|agora\s+minimize\s+ele)\s*[.!?]*$',
             self._window_minimize, "window_minimize", "active"),
            (r'^(?:zara[,\s]+)?(?:maximize(?:\s+(?:a|esta)\s+janela)?)\s*[.!?]*$',
             self._window_maximize, "window_maximize", "active"),
            (r'^(?:zara[,\s]+)?(?:restaure(?:\s+a\s+janela)?|volte\s+a\s+janela\s+ao\s+normal)\s*[.!?]*$',
             self._window_restore, "window_restore", "active"),
            (r'^(?:zara[,\s]+)?(?:troque\s+de\s+janela|v[áa]\s+para\s+a\s+próxima\s+janela)\s*[.!?]*$',
             self._window_switch, "window_switch_next", "next"),
            (r'^(?:zara[,\s]+)?(?:traz|traga|coloque)\s+(?:o\s+)?chrome\s+(?:pra|para)\s+frente\s*[.!?]*$',
             self._window_chrome, "window_focus_named", "chrome"),
            (r'^(?:zara[,\s]+)?(?:volta|volte|traz|traga)\s+(?:pra|para)\s+(?:a\s+)?zara\s*[.!?]*$',
             self._window_zara, "window_focus_named", "zara"),
            (r'^(?:zara[,\s]+)?(?:troca|troque|mude)\s+(?:para|pro|para\s+o)\s+(?:o\s+)?(?:vs\s*code|visual\s+studio\s+code)\s*[.!?]*$',
             self._window_vscode, "window_focus_named", "vscode"),
            (r'^(?:zara[,\s]+)?(?:mostra|mostre|traz|traga)\s+(?:o\s+)?projeto\s*[.!?]*$',
             self._window_project, "window_focus_named", "project"),

            # Scroll
            (r'^(?:zara[,\s]+)?(?:role|scroll|desça|descer|desce)(?:\s+(?:a\s+)?página)?(?:\s+(?:para\s+)?baixo)?\s*[.!?]*$',
             self._scroll_down, "browser_scroll", "down"),
            (r'^(?:zara[,\s]+)?(?:role|scroll|suba|subir|sobe)(?:\s+(?:a\s+)?página)?(?:\s+(?:para\s+)?cima|\s+um\s+pouco)?\s*[.!?]*$',
             self._scroll_up, "browser_scroll", "up"),

            # Explicitly catch unsupported app requests after all known safe
            # commands. The raw text is never executed.
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|inicie|inicia|iniciar|executa|execute|executar|quero\s+abrir)\s+'
             r'(?P<app>.+?)\s*[.!?]*$',
             self._unsupported_app, "os_app", None),
        ]

    def detect(self, text: str) -> PcVoiceResult:
        """Detect PC control intent in text."""
        if not text:
            return PcVoiceResult(is_pc_intent=False)

        text_lower = text.lower().strip()

        type_match = re.fullmatch(
            r'(?:zara[,\s]+)?(?:digite|digita|escreva|escreve)\s+[\'\"“”‘’](.+)[\'\"“”‘’]\s*[.!?]*',
            str(text or "").strip(), flags=re.IGNORECASE,
        )
        if type_match:
            return PcVoiceResult(is_pc_intent=True, action="input_type_text", param=type_match.group(1), physical_effect=1)

        input_commands = (
            (r'(?:zara[,\s]+)?(?:selecione|seleciona)\s+tudo\s*[.!?]*', "select_all"),
            (r'(?:zara[,\s]+)?(?:copie|copia)\s+(?:a\s+seleção|o\s+texto\s+selecionado)\s*[.!?]*', "copy"),
            (r'(?:zara[,\s]+)?(?:cole|cola)\s+(?:aqui|neste\s+campo)\s*[.!?]*', "paste"),
            (r'(?:zara[,\s]+)?(?:procure|busque)\s+(?:aqui|neste\s+texto)\s*[.!?]*', "find"),
            (r'(?:zara[,\s]+)?(?:desfaça|desfaz)\s*[.!?]*', "undo"),
            (r'(?:zara[,\s]+)?(?:refaça|refaz)\s*[.!?]*', "redo"),
        )
        for pattern, command in input_commands:
            if re.fullmatch(pattern, text_lower):
                return PcVoiceResult(is_pc_intent=True, action="input_hotkey", param=command, physical_effect=1)

        # Resolve explicit volume before the intentionally broad music phrase
        # "coloque <faixa>"; otherwise "coloque o volume em 30%" is mistaken
        # for a YouTube title.
        explicit_volume = re.fullmatch(
            r'(?:zara[,\s]+)?(?:coloque|coloca|defina|ponha|deixe|set)?\s*(?:o\s+)?volume\s+(?:em\s+)?(\d{1,3})\s*%?\s*[.!?]*',
            text_lower,
        )
        if explicit_volume:
            return PcVoiceResult(is_pc_intent=True, action="os_volume", param=explicit_volume.group(1), physical_effect=1)

        # Resolve explicit brightness before the intentionally broad music
        # phrase "coloque <faixa>" for the same reason as volume above.
        explicit_brightness = re.fullmatch(
            r'(?:zara[,\s]+)?(?:brilho\s+(?:em\s+)?|coloque\s+(?:o\s+)?brilho\s+(?:em\s+)?|deixe\s+a\s+tela\s+em\s+)(\d{1,3})\s*%?\s*[.!?]*',
            text_lower,
        )
        if explicit_brightness:
            return PcVoiceResult(
                is_pc_intent=True,
                action="os_brightness_absolute",
                param=explicit_brightness.group(1),
                physical_effect=1,
            )

        if re.fullmatch(
            r'(?:zara[,\s]+)?(?:troque\s+de\s+janela|v[áa]\s+para\s+a\s+próxima\s+janela)\s*[.!?]*',
            text_lower,
        ):
            return PcVoiceResult(
                is_pc_intent=True,
                action="window_switch_next",
                blocked=True,
                reply="Diga qual janela devo trazer para a frente; não alterno às cegas.",
                contextual=True,
            )

        contextual_volume = re.search(
            r'\b(?:(?:deixa?|deixe)\s+(?:o\s+volume\s+)?um\s+pouco\s+|agora\s+)?mais\s+(alto|baixo)\b',
            text_lower,
        )
        if contextual_volume:
            if self.volume_context_level is None:
                return PcVoiceResult(
                    is_pc_intent=True,
                    action="os_volume",
                    blocked=True,
                    reply="Não tenho um volume verificado recente. Diga o nível desejado.",
                    contextual=True,
                )
            blocked = self._blocked_by_superbrain("os_volume")
            return PcVoiceResult(
                is_pc_intent=True,
                action="os_volume",
                param="up" if contextual_volume.group(1) == "alto" else "down",
                blocked=blocked,
                physical_effect=0 if blocked else 1,
                reply="Para controlar o computador, ative o Supercérebro." if blocked else "",
                contextual=True,
            )

        contextual_window = re.fullmatch(
            r'(?:zara[,\s]+)?(?:agora\s+)?(minimize|maximize|restaure)\s+(?:ele|ela|isso|essa\s+janela)\s*[.!?]*',
            text_lower,
        )
        if contextual_window:
            command = contextual_window.group(1)
            action = {
                "minimize": "window_minimize",
                "maximize": "window_maximize",
                "restaure": "window_restore",
            }[command]
            if not self.window_context_available:
                return PcVoiceResult(
                    is_pc_intent=True,
                    action=action,
                    blocked=True,
                    reply="Não tenho uma janela recente e inequívoca. Diga qual janela devo controlar.",
                    contextual=True,
                )
            blocked = self._blocked_by_superbrain(action)
            return PcVoiceResult(
                is_pc_intent=True,
                action=action,
                blocked=blocked,
                physical_effect=0 if blocked else 1,
                reply="Para controlar o computador, ative o Supercérebro." if blocked else "",
                contextual=True,
            )

        contextual_geometry = re.fullmatch(
            r'(?:zara[,\s]+)?(?:coloque|coloca|move|mova)\s+(?:isso|isto|essa\s+janela|a\s+janela)\s+(?:para\s+o|pro|no|do)\s+lado\s+(direito|esquerdo)\s*[.!?]*',
            text_lower,
        )
        if contextual_geometry:
            if not self.window_context_available:
                return PcVoiceResult(is_pc_intent=True, action="window_move", blocked=True, reply="Não tenho uma janela recente e inequívoca. Diga qual janela devo controlar.", contextual=True)
            return PcVoiceResult(is_pc_intent=True, action="window_move", param="right" if contextual_geometry.group(1) == "direito" else "left", physical_effect=1, contextual=True)

        contextual_resize = re.fullmatch(
            r'(?:zara[,\s]+)?(?:deixe|deixa|faça|faz)\s+(?:isso|isto|essa\s+janela|a\s+janela)\s+(?:maior|mais\s+grande)\s*[.!?]*',
            text_lower,
        )
        if contextual_resize:
            if not self.window_context_available:
                return PcVoiceResult(is_pc_intent=True, action="window_resize_larger", blocked=True, reply="Não tenho uma janela recente e inequívoca. Diga qual janela devo controlar.", contextual=True)
            return PcVoiceResult(is_pc_intent=True, action="window_resize_larger", physical_effect=1, contextual=True)

        contextual_close = re.fullmatch(
            r'(?:zara[,\s]+)?(?:feche|fecha)\s+(?:isso|isto|essa\s+janela|a\s+janela)\s*[.!?]*',
            text_lower,
        )
        if contextual_close:
            if not self.window_context_available:
                return PcVoiceResult(is_pc_intent=True, action="window_close", blocked=True, reply="Não tenho uma janela recente e inequívoca. Diga qual janela devo fechar.", contextual=True)
            return PcVoiceResult(is_pc_intent=True, action="window_close", physical_effect=1, contextual=True)

        contextual_folder = re.fullmatch(
            r'(?:(?:abra|mostre)\s+)?(?:ela|essa\s+pasta|a\s+mesma\s+pasta)(?:\s+(?:novamente|de\s+novo))?\s*[.!?]*',
            text_lower,
        )
        if contextual_folder:
            if self.folder_context is None:
                return PcVoiceResult(
                    is_pc_intent=True,
                    action="os_open",
                    blocked=True,
                    reply="Qual pasta devo mostrar?",
                    contextual=True,
                )
            blocked = self._blocked_by_superbrain("os_open")
            return PcVoiceResult(
                is_pc_intent=True,
                action="os_open",
                param=self.folder_context,
                blocked=blocked,
                physical_effect=0 if blocked else 1,
                reply="Para controlar o computador, ative o Supercérebro." if blocked else "",
                contextual=True,
            )

        if re.fullmatch(r'(?:agora\s+)?feche\s+(?:ele|ela|essa\s+janela)\s*[.!?]*', text_lower):
            return PcVoiceResult(
                is_pc_intent=True,
                blocked=True,
                reply="Não fecho alvos por referência genérica. Diga explicitamente o aplicativo.",
                contextual=True,
            )

        # Must start with wake word "zara" or be direct command
        if not (text_lower.startswith("zara") or "zara," in text_lower or "zara " in text_lower):
            # Still check if it's a clear command
            pass

        for pattern, handler, action, default_param in self.patterns:
            m = re.search(pattern, text_lower)
            if m:
                param = handler(m)
                if default_param and not param:
                    param = default_param

                if action == "os_app" and param not in {
                    "calculator", "notepad", "chrome", "task_manager", "settings",
                    "paint", "snipping_tool", "edge", "spotify",
                }:
                    return PcVoiceResult(
                        is_pc_intent=True,
                        action="os_app",
                        param=param,
                        blocked=True,
                        physical_effect=0,
                        reply=(
                            "Esse aplicativo não está autorizado. "
                            "Posso abrir Calculadora, Bloco de Notas ou Chrome."
                        ),
                    )

                blocked = self._blocked_by_superbrain(action)
                reply = ""
                if blocked:
                    reply = "Para controlar o computador, ative o Supercérebro."

                return PcVoiceResult(
                    is_pc_intent=True,
                    action=action,
                    param=param,
                    blocked=blocked,
                    physical_effect=0 if blocked else 1,
                    reply=reply
                )

        return PcVoiceResult(is_pc_intent=False)

    def _blocked_by_superbrain(self, action: str) -> bool:
        return not self.pc_control_allowed and action not in _LOCAL_DETERMINISTIC_ACTIONS

    # Handlers
    def _browser_native(self, m):
        return ""

    def _clipboard_read(self, m):
        return "read"

    def _clipboard_clear(self, m):
        return "__CLEAR__"

    def _clipboard_text(self, m):
        value = m.group(1).strip()
        value = re.sub(r'^(?:este\s+texto\s+|o\s+texto\s+)', '', value)
        if len(value) >= 2 and value[0] in "'\"‘’“”" and value[-1] in "'\"‘’“”":
            value = value[1:-1].strip()
        return value[:4000]

    def _screenshot(self, m):
        return "full"

    def _notification_message(self, m):
        return m.group(1).strip()

    def _open_calc(self, m):
        return "calculator"

    def _open_notepad(self, m):
        return "notepad"

    def _open_chrome(self, m):
        return "chrome"

    def _open_task_manager(self, m):
        return "task_manager"

    def _open_settings(self, m):
        return "settings"

    def _open_paint(self, m):
        return "paint"

    def _open_snipping_tool(self, m):
        return "snipping_tool"

    def _open_edge(self, m):
        return "edge"

    def _open_spotify(self, m):
        return "spotify"

    def _close_calculator(self, m):
        return "calculator"

    def _close_task_manager(self, m):
        return "task_manager"

    def _close_settings(self, m):
        return "settings"

    def _close_spotify(self, m):
        return "spotify"

    def _close_notepad(self, m):
        return "notepad"

    def _close_paint(self, m):
        return "paint"

    def _close_snipping_tool(self, m):
        return "snipping_tool"

    def _close_chrome(self, m):
        return "chrome"

    def _close_edge(self, m):
        return "edge"

    def _unsupported_app(self, m):
        return m.group("app").strip()

    def _open_downloads(self, m):
        return "downloads"

    def _open_documents(self, m):
        return "documents"

    def _open_desktop(self, m):
        return "desktop"

    def _open_pictures(self, m):
        return "pictures"

    def _open_zara_folder(self, m):
        return "zara_root"

    def _open_openai(self, m):
        return "https://openai.com/"

    def _open_url(self, m):
        return m.group(1).strip()

    def _search(self, m):
        # Extract query after "pesquise/procure/busque"; remove destination
        # noise ("no google", "no navegador") so the query is the real search.
        query = m.group(3) if m.groups() else ""
        query = re.sub(r'\s+(?:no|na|pelo|pela)\s+(?:google|navegador|internet|web)\s*$', '', query.strip())
        return query.strip()

    def _media_query(self, m):
        return m.group(1).strip()

    def _youtube_skip_ad(self, m):
        return "skip"

    def _youtube_now_playing(self, m):
        return "current"

    def _youtube_another(self, m):
        return "current_artist"

    def _system_metrics(self, m):
        return "summary"

    def _system_info(self, m):
        return "basic"

    def _system_processes(self, m):
        return "top"

    def _volume_up(self, m):
        return "up"

    def _volume_down(self, m):
        return "down"

    def _volume_level(self, m):
        return m.group(1)

    def _media_play_pause(self, m):
        return "toggle"

    def _youtube_pause(self, m):
        return "pause"

    def _youtube_resume(self, m):
        return "resume"

    def _youtube_seek_forward(self, m):
        return str(int(m.group(1)))

    def _youtube_seek_backward(self, m):
        return str(-int(m.group(1)))

    def _youtube_seek_small_back(self, m):
        return "-10"

    def _youtube_restart(self, m):
        return "restart"

    def _media_next(self, m):
        return "next"

    def _media_previous(self, m):
        return "previous"

    def _audio_mute(self, m):
        return "mute"

    def _audio_unmute(self, m):
        return "unmute"

    def _audio_status(self, m):
        return "status"

    def _radio_on(self, m):
        return "on"

    def _radio_off(self, m):
        return "off"

    def _brightness_level(self, m):
        return m.group(1)

    def _brightness_up(self, m):
        return "up"

    def _brightness_down(self, m):
        return "down"

    def _night_light_on(self, m):
        return "on"

    def _night_light_off(self, m):
        return "off"

    def _window_minimize(self, m):
        return "active"

    def _window_maximize(self, m):
        return "active"

    def _window_restore(self, m):
        return "active"

    def _window_switch(self, m):
        return "next"

    def _window_chrome(self, m):
        return "chrome"

    def _window_zara(self, m):
        return "zara"

    def _window_vscode(self, m):
        return "vscode"

    def _window_project(self, m):
        return "project"

    def _scroll_down(self, m):
        return "down"

    def _scroll_up(self, m):
        return "up"
