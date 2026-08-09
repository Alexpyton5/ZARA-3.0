#!/usr/bin/env python3
"""
ZARA-PC-CONTROL-VOICE-BINDING-001

PC voice intent detector. Maps natural language Windows commands to existing PC control actions.
With Supercerebro OFF, detected intents are blocked (BLOCKED_PC_CONTROL).
"""

import re
from dataclasses import dataclass


@dataclass
class PcVoiceResult:
    is_pc_intent: bool
    action: str = ""
    param: str = ""
    blocked: bool = False
    physical_effect: int = 0
    reply: str = ""


class PcVoiceIntentDetector:
    """Detect PC control voice commands and map to existing actions."""

    def __init__(self, pc_control_allowed: bool = False):
        self.pc_control_allowed = pc_control_allowed

        # Intent patterns
        self.patterns = [
            # Open apps
            (r'\b(abra|abre|abrir|abre\s+a|open)\s+(a\s+)?(calculadora|calc|calculator)\b',
             self._open_calc, "os_app", "calc"),
            (r'\b(abra|abre|abrir|open)\s+(o\s+)?(navegador|browser|chrome|edge|firefox)\b',
             self._open_browser, "os_app", "browser"),
            (r'\b(abra|abre|abrir|open)\s+(o\s+)?(downloads?)\b',
             self._open_downloads, "os_open", "downloads"),
            (r'\b(abra|abre|abrir|open)\s+(os\s+)?(documentos?|documents?)\b',
             self._open_documents, "os_open", "documents"),

            # Search
            (r'\b(pesquise?|procure|search|busque?)\s+(por\s+)?(.+)\b',
             self._search, "web_search", None),

            # Volume
            (r'\b(?:coloque|coloca|colocar|defina|define|ponha|põe|deixe|ajuste|set)\s+'
             r'(?:o\s+)?(?:volume|som)\s+(?:em|para|a|no)\s+(\d{1,3})\s*%?\b',
             self._volume_level, "os_volume", None),
            (r'\b(?:volume|som)\s+(?:em\s+|no\s+)?(\d{1,3})\s*%?\b',
             self._volume_level, "os_volume", None),
            (r'\b(?:(?:aumente?|aumenta|suba|sobe|eleve|up|increase?)\s+'
             r'(?:(?:um|mais)\s+pouco\s+)?(?:o\s+)?(?:volume|som)|mais\s+(?:volume|som))\b',
             self._volume_up, "os_volume", "up"),
            (r'\b(?:(?:diminua?|diminui|baixe|baixa|abaixe|abaixa|reduza|reduz|down|decrease?|lower)\s+'
             r'(?:(?:só\s+)?um\s+pouco\s+)?(?:o\s+)?(?:volume|som)|menos\s+(?:volume|som))\b',
             self._volume_down, "os_volume", "down"),

            # Scroll
            (r'\b(role?|scroll|desça|descer|go\s+down)\s+(para\s+)?(baixo|down)\b',
             self._scroll_down, "scroll", "down"),
            (r'\b(role?|scroll|suba|subir|go\s+up)\s+(para\s+)?(cima|up)\b',
             self._scroll_up, "scroll", "up"),
        ]

    def detect(self, text: str) -> PcVoiceResult:
        """Detect PC control intent in text."""
        if not text:
            return PcVoiceResult(is_pc_intent=False)

        text_lower = text.lower().strip()

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

                blocked = not self.pc_control_allowed
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

    # Handlers
    def _open_calc(self, m):
        return "calc"

    def _open_browser(self, m):
        return "browser"

    def _open_downloads(self, m):
        return "downloads"

    def _open_documents(self, m):
        return "documents"

    def _search(self, m):
        # Extract query after "pesquise/procure/busque"
        query = m.group(3) if m.groups() else ""
        return query.strip()

    def _volume_up(self, m):
        return "up"

    def _volume_down(self, m):
        return "down"

    def _volume_level(self, m):
        return m.group(1)

    def _scroll_down(self, m):
        return "down"

    def _scroll_up(self, m):
        return "up"
