#!/usr/bin/env python3
"""
ZARA-PC-CONTROL-VOICE-BINDING-001

PC voice intent detector. Maps natural language Windows commands to existing PC control actions.
"""

import json
import os
import re
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from core.actions.os_ops import resolve_app_alias, _SAFE_CLOSE_APPS
from core.action_registry import get_registry
from core.aprendizado import Aprendizado, _forma_do_pedido

# ZARA-RECUSA-UNICA-001 (Alex, 2026-08-13)
# "eu nao quero que ela ofereça calculadora, quando ela nao puder fazer algo,
# ela vai falar eu ainda nao sei fazer isto."
#
# Uma frase so para TODO caso de incapacidade, venha de allowlist, de sintaxe
# recusada ou de comando sem executor. Continua sendo recusa honesta: ela nao
# executa nada e nao finge que executou. O que muda e parar de listar
# consolacoes que o Alex nao pediu.
# ZARA-RECUSA-HUMANA-001
#
# Alex: *"tem que ser o mais próximo de uma conversa entre humanos em todos os
# sentidos"*, e antes disso: *"isso é muito robótico"*.
#
# A recusa era "Eu ainda não sei fazer isto." — honesta, e é por isso que ela
# existe: é o guarda que impede a ZARA de fingir que executou. Mas ninguém fala
# assim. Uma pessoa que não sabe fazer algo diz que não sabe **e diz o que
# fazer a seguir**; frase seca deixa o outro sem saída.
#
# A honestidade não mudou uma vírgula. Só deixou de ser uma porta na cara.
RESPOSTA_NAO_SEI = (
    "Isso eu ainda não sei fazer. Se você me disser de outro jeito eu tento, "
    "e se for coisa nova mesmo, é só pedir pro Claude me ensinar."
)

# ZARA-PONTE-NOMES-001
# O reconhecimento de fala não escreve "Claude". Alex relatou: "falei claude ela
# entendeu claudio". Estes são os nomes que precisam valer como se fossem o
# mesmo. Quando ele reportar uma variação nova, é só acrescentar aqui.
_NOME_CLAUDE = (
    r"(?:claude|cláudio|claudio|cláudia|claudia|cloud|cloude|clode|claudi|"
    r"claudy|clau|glaude|clod)(?:\s+code)?"
)
_NOME_CODEX = r"(?:codex|códex|codes|c[óo]dice|cortex|chat\s*gpt|chatgpt|cheat\s*gpt)"

# ZARA-INTENSIDADE-VOLUME-001 (Alex, 2026-08-28)
# "põe o som lá em baixo" virou -10% fixo; "diminua muito o volume" nem
# reconhecia. Alex: "quando eu peça pra diminuir muito, diminua muito na
# mesma hora" -- raciocinar sobre a MAGNITUDE do pedido, nao só a direção,
# sem sair do caminho determinístico (zero rede, zero latência nova).
#
# Vocabulário fechado de proposito, mesma disciplina do classificador de
# raciocínio livre (core/intent_classifier.py): nunca um número livre vindo
# de regex, só um rótulo de um conjunto pequeno e auditável.
_INTENSIDADE_POUCO = {"um pouco", "um pouquinho", "levemente"}
_INTENSIDADE_MUITO = {"muito", "bastante", "demais", "bem"}


def _encode_intensity(direction: str, intensity_text: str | None) -> str:
    """Traduz o texto de intensidade capturado no regex num sufixo fechado
    ('_pouco'/'_muito') que core/ipc_handlers.py usa para escolher o passo
    real. Sem captura -> passo padrão de sempre (10 pontos), comportamento
    inalterado para quem já falava sem qualificador."""
    if not intensity_text:
        return direction
    texto = " ".join(intensity_text.strip().lower().split())
    if texto in _INTENSIDADE_POUCO:
        return f"{direction}_pouco"
    if texto in _INTENSIDADE_MUITO:
        return f"{direction}_muito"
    return direction


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
        volume_context_level: int | None = None,
        window_context_available: bool = False,
        folder_context: str | None = None,
    ):
        self.volume_context_level = volume_context_level
        self.window_context_available = window_context_available
        self.folder_context = folder_context

        # Advanced OS commands. Each tuple is (regex, action, default_param).
        # Mutating items still pass the registry risk gates.
        self.advanced_patterns = [
            (r'^(?:zara[,.\s]+)?(?:liste|lista|mostre|quais\s+s[ãa]o)\s+(?:os\s+)?servi[cç]os(?:\s+do\s+windows)?\s*[.!?]*$', "os_service_list", ""),
            (r'^(?:zara[,.\s]+)?(?:inicie|inicia|ligue)\s+(?:o\s+)?servi[cç]o\s+(.+?)\s*[.!?]*$', "os_service_start", None),
            (r'^(?:zara[,.\s]+)?(?:pare|parar|desligue)\s+(?:o\s+)?servi[cç]o\s+(.+?)\s*[.!?]*$', "os_service_stop", None),
            (r'^(?:zara[,.\s]+)?(?:liste|lista|mostre)\s+(?:as\s+)?tarefas\s+agendadas\s*[.!?]*$', "os_task_list", ""),
            (r'^(?:zara[,.\s]+)?(?:execute|executa|rode|roda)\s+(?:a\s+)?tarefa\s+agendada\s+(.+?)\s*[.!?]*$', "os_task_run", None),
            (r'^(?:zara[,.\s]+)?crie\s+(?:a\s+)?tarefa\s+agendada\s+(.+?)\s*[.!?]*$', "os_task_create", None),
            (r'^(?:zara[,.\s]+)?(?:liste|lista|mostre)\s+(?:os\s+)?planos\s+de\s+energia\s*[.!?]*$', "os_power_plan_list", ""),
            (r'^(?:zara[,.\s]+)?(?:ative|ativa|use)\s+(?:o\s+)?plano\s+de\s+energia\s+(.+?)\s*[.!?]*$', "os_power_plan_set", None),
            (r'^(?:zara[,.\s]+)?(?:suspenda|suspende|durma|dorme)(?:\s+o\s+(?:computador|pc))?\s*[.!?]*$', "os_sleep", "sleep"),
            (r'^(?:zara[,.\s]+)?(?:hiberne|hiberna)(?:\s+o\s+(?:computador|pc))?\s*[.!?]*$', "os_sleep", "hibernate"),
            (r'^(?:zara[,.\s]+)?(?:liste|lista|mostre)\s+(?:os\s+)?adaptadores\s+de\s+rede\s*[.!?]*$', "os_network_adapters", ""),
            (r'^(?:zara[,.\s]+)?(?:liste|lista|mostre)\s+(?:as\s+)?redes\s+wi-?fi\s+salvas\s*[.!?]*$', "os_wifi_profiles", ""),
            (r'^(?:zara[,.\s]+)?(?:conecte|conecta)\s+(?:no|ao)\s+wi-?fi\s+(.+?)\s*[.!?]*$', "os_wifi_connect", None),
            (r'^(?:zara[,.\s]+)?(?:ligue|liga|ative|ativa)\s+(?:o\s+)?hotspot\s*[.!?]*$', "os_hotspot_toggle", "on"),
            (r'^(?:zara[,.\s]+)?(?:desligue|desliga|desative|desativa)\s+(?:o\s+)?hotspot\s*[.!?]*$', "os_hotspot_toggle", "off"),
            (r'^(?:zara[,.\s]+)?(?:liste|lista|mostre)\s+(?:as\s+)?vpns?\s*[.!?]*$', "os_vpn_list", ""),
            (r'^(?:zara[,.\s]+)?(?:conecte|conecta)\s+(?:na|a)\s+vpn\s+(.+?)\s*[.!?]*$', "os_vpn_connect", None),
            (r'^(?:zara[,.\s]+)?(?:mostre|mostra|abra|liste)\s+(?:o\s+)?hist[oó]rico\s+(?:da\s+)?[aá]rea\s+de\s+transfer[eê]ncia\s*[.!?]*$', "os_clipboard_history", ""),
            (r'^(?:zara[,.\s]+)?fixe\s+(.+?)\s+(?:no\s+)?hist[oó]rico\s+(?:da\s+)?[aá]rea\s+de\s+transfer[eê]ncia\s*[.!?]*$', "os_clipboard_pin", None),
            (r'^(?:zara[,.\s]+)?(?:liste|lista|mostre)\s+(?:os\s+)?itens\s+(?:da|na)\s+lixeira\s*[.!?]*$', "os_recycle_bin_list", ""),
            (r'^(?:zara[,.\s]+)?(?:restaure|restaura)\s+(?:da\s+lixeira\s+)(.+?)\s*[.!?]*$', "os_recycle_bin_restore", None),
            (r'^(?:zara[,.\s]+)?(?:esvazie|esvazia|limpe|limpa)\s+(?:a\s+)?lixeira\s*[.!?]*$', "os_recycle_bin_empty", ""),
            (r'^(?:zara[,.\s]+)?(?:encaixe|encaixa)\s+(?:a\s+)?janela\s+(?:na|para\s+a)\s+(esquerda|direita|cima|baixo)\s*[.!?]*$', "window_snap", None),
            (r'^(?:zara[,.\s]+)?crie\s+(?:um\s+)?novo\s+desktop\s+virtual\s*[.!?]*$', "window_virtual_desktop_create", ""),
            (r'^(?:zara[,.\s]+)?(?:v[aá]|mude|troque)\s+(?:para\s+)?(?:o\s+)?desktop\s+(?:virtual\s+)?(anterior|seguinte|esquerda|direita)\s*[.!?]*$', "window_virtual_desktop_switch", None),
            (r'^(?:zara[,.\s]+)?mova\s+(?:a\s+)?janela\s+(?:para\s+)?(?:o\s+)?desktop\s+(?:virtual\s+)?(anterior|seguinte|esquerda|direita)\s*[.!?]*$', "window_virtual_desktop_move", None),
            (r'^(?:zara[,.\s]+)?minimize\s+todas\s+(?:as\s+)?janelas\s*[.!?]*$', "window_minimize_all", ""),
            (r'^(?:zara[,.\s]+)?(?:mostre|mostra|exiba)\s+(?:o\s+)?desktop\s*[.!?]*$', "window_show_desktop", ""),
        ]

        # Intent patterns
        self.patterns = [
            # ZARA-PONTE-CLAUDE-001 — conversar com o Claude Code sem teclado.
            # Ficam no topo de propósito: "lê o que o Claude falou" contém
            # "lê", que padrões mais abaixo (área de transferência, página)
            # também disputam.
            (r'^(?:zara[,\s]+)?(?:responde|responda|responder|manda|mande|mandar|'
             r'diz|diga|dizer|fala|escreve|escreva)\s+'
             r'(?:pro|para\s+o|ao|pro\s+o)\s+(?:(?:claude|cloud|claudi)(?:\s+code)?|code(?!x))\s*[:,]?\s*(.+)$',
             self._claude_enviar, "claude_enviar", None),
            # ZARA-PONTE-REPASSE-001 — os três conversando, com a ZARA no meio.
            # Vem antes dos padrões de envio: "manda o que o Claude falou pro
            # Codex" também casaria com "manda pro Codex ...".
            (r'^(?:zara[,\s]+)?(?:manda|mande|mandar|passa|passe|repassa|repasse|'
             r'diz|mostra|leva)\s+(?:isso\s+|o\s+que\s+)?(?:o\s+)?'
             r'(?:(?:claude|cloud|claudi)(?:\s+code)?|code(?!x))\s*(?:falou|disse|mandou|respondeu|escreveu)?\s*'
             r'(?:pro|para\s+o|ao)\s+(?:codex|codes|c[óo]dex|chat\s*gpt)\b.*$',
             self._repasse_claude_codex, "ponte_repassar", "claude>codex"),
            (r'^(?:zara[,\s]+)?(?:manda|mande|mandar|passa|passe|repassa|repasse|'
             r'diz|mostra|leva)\s+(?:isso\s+|o\s+que\s+)?(?:o\s+)?'
             r'(?:codex|codes|c[óo]dex|chat\s*gpt)\s*(?:falou|disse|mandou|respondeu|escreveu)?\s*'
             r'(?:pro|para\s+o|ao)\s+(?:(?:claude|cloud|claudi)(?:\s+code)?|code(?!x))\b.*$',
             self._repasse_codex_claude, "ponte_repassar", "codex>claude"),
            # Mesma ideia com a ordem trocada: "passa PRO CODEX o que o CLAUDE
            # disse". Alex fala das duas formas.
            (r'^(?:zara[,\s]+)?(?:manda|mande|mandar|passa|passe|repassa|repasse|diz|mostra|leva)\s+'
             r'(?:pro|para\s+o|ao)\s+(?:codex|codes|c[óo]dex|chat\s*gpt)\s+'
             r'(?:isso\s+|o\s+que\s+)(?:o\s+)?(?:(?:claude|cloud|claudi)(?:\s+code)?|code(?!x))\b.*$',
             self._repasse_claude_codex, "ponte_repassar", "claude>codex"),
            (r'^(?:zara[,\s]+)?(?:manda|mande|mandar|passa|passe|repassa|repasse|diz|mostra|leva)\s+'
             r'(?:pro|para\s+o|ao)\s+(?:(?:claude|cloud|claudi)(?:\s+code)?|code(?!x))\s+'
             r'(?:isso\s+|o\s+que\s+)(?:o\s+)?(?:codex|codes|c[óo]dex|chat\s*gpt)\b.*$',
             self._repasse_codex_claude, "ponte_repassar", "codex>claude"),
            # ZARA-APRENDIZADO-001 — Alex vendo o que ela aprendeu.
            #
            # Sem isso o aprendizado vira caixa preta que só cresce. Ele precisa
            # poder olhar dentro; sem olhar não há como corrigir, e uma memória
            # que ninguém revisa acaba operando com base em besteira.
            (r'^(?:zara[,\s]+)?(?:o\s+que\s+)?(?:voc[êe]\s+)?'
             r'(?:aprendeu|aprendendo|aprendi[óo]?|evolui[uo]?|melhorou)\b.*$',
             self._o_que_aprendeu, "aprendizado_resumo", "hoje"),
            (r'^(?:zara[,\s]+)?(?:me\s+)?(?:mostra|mostre|conta|conte|diga|fala)\s+'
             r'(?:o\s+que\s+)?(?:voc[êe]\s+)?(?:aprendeu|est[áa]\s+aprendendo)\b.*$',
             self._o_que_aprendeu, "aprendizado_resumo", "hoje"),
            (r'^(?:zara[,\s]+)?(?:em\s+que\s+)?(?:dia|nivel|n[íi]vel)\s+'
             r'(?:voc[êe]\s+)?(?:est[áa]|ta|t[áa])\b.*$',
             self._o_que_aprendeu, "aprendizado_resumo", "hoje"),
            # ZARA-PONTE-LEITURA-COMPLETA-002 — "lê resumido".
            #
            # O padrão passou a ser ler TUDO: a voz dela é gratuita, quem gasta
            # token é o Claude e o Codex escrevendo. Cortar a fala dela
            # economizava o recurso errado. Estas frases pedem a versão curta,
            # e vêm antes da leitura normal, que casaria igual.
            (r'^(?:zara[,\s]+)?'
             rf'(?!.*\b{_NOME_CODEX}\b)'
             rf'(?=.*\b{_NOME_CLAUDE}\b)'
             r'(?=.*\b(?:resumid[oa]|resumo|resumindo|resuma|resume|por\s+cima|'
             r'r[áa]pido|s[óo]\s+o\s+principal)\b)'
             r'(?=.*(?:l[êe]\b|leia|ler\b|falou|disse|mandou|escreveu|resposta|texto))'
             r'.*$',
             self._ler_resumido, "claude_ler", "resumido"),
            (r'^(?:zara[,\s]+)?'
             rf'(?=.*\b{_NOME_CODEX}\b)'
             r'(?=.*\b(?:resumid[oa]|resumo|resumindo|resuma|resume|por\s+cima|'
             r'r[áa]pido|s[óo]\s+o\s+principal)\b)'
             r'(?=.*(?:l[êe]\b|leia|ler\b|falou|disse|mandou|escreveu|resposta|texto))'
             r'.*$',
             self._ler_resumido, "codex_ler", "resumido"),
            # ZARA-PONTE-FRASE-LIVRE-001 — leitura em frase livre.
            #
            # A primeira versão exigia a frase quase exata e Alex disse "eu falei
            # tudo o que pudia" sem ela entender. Agora basta ele CITAR o Claude
            # e usar QUALQUER palavra de ouvir/dizer, em qualquer ordem.
            #
            # Fica DEPOIS do envio e do repasse de propósito: "diz pro Claude
            # que..." também contém "diz", e mandar recado é mais específico que
            # pedir leitura. O mais específico ganha.
            (r'^(?:zara[,\s]+)?'
             rf'(?!.*\b{_NOME_CODEX}\b)'
             rf'(?=.*\b{_NOME_CLAUDE}\b)'
             r'(?=.*(?:falou|fala\b|disse|diz\b|mandou|respondeu|resposta|escreveu|'
             r'l[êe]\b|leu\b|leia|ler\b|mensagem|novidade|recado))'
             r'.*$',
             self._claude_ler, "claude_ler", "read"),
            # Mesma frase livre, para o Codex.
            (r'^(?:zara[,\s]+)?'
             rf'(?=.*\b{_NOME_CODEX}\b)'
             r'(?=.*(?:falou|fala\b|disse|diz\b|mandou|respondeu|resposta|escreveu|'
             r'l[êe]\b|leu\b|leia|ler\b|mensagem|novidade|recado))'
             r'.*$',
             self._claude_ler, "codex_ler", "read"),
            # Codex — mesmo par de comandos, outro destino.
            (r'^(?:zara[,\s]+)?(?:l[êe]|leia|ler|me\s+l[êe])\s+(?:o\s+que\s+)?'
             r'(?:a\s+|o\s+)?(?:[úu]ltim[ao]\s+)?(?:resposta\s+d[oe]\s+|mensagem\s+d[oe]\s+)?'
             r'(?:codex|codes|c[óo]dex|chat\s*gpt)\b.*$',
             self._claude_ler, "codex_ler", "read"),
            (r'^(?:zara[,\s]+)?(?:o\s+que\s+)?(?:o\s+)?(?:codex|codes|c[óo]dex|chat\s*gpt)\s+'
             r'(?:falou|disse|mandou|respondeu|escreveu)\b.*$',
             self._claude_ler, "codex_ler", "read"),
            (r'^(?:zara[,\s]+)?(?:responde|responda|responder|manda|mande|mandar|'
             r'diz|diga|dizer|fala|escreve|escreva)\s+'
             r'(?:pro|para\s+o|ao|pro\s+o)\s+(?:codex|codes|c[óo]dex|chat\s*gpt)\s*[:,]?\s*(.+)$',
             self._claude_enviar, "codex_enviar", None),
            # Clipboard writes stay MEDIUM and are confirmed conversationally by IPCHandler.
            (r'\b(?:o\s+que\s+(?:est[áa]|ta|tem)|lei[ae]r?|l[êe])\s+(?:o\s+que\s+(?:est[áa]|ta)\s+)?(?:na\s+|a\s+)?(?:área|area)\s+de\s+transfer[êe]ncia\b',
             self._clipboard_read, "os_clipboard_read", "read"),
            (r'^(?:zara[,\s]+)?(?:limpe|limpa|esvazie)\s+(?:a\s+)?(?:área|area)\s+de\s+transfer[êe]ncia\s*[.!?]*$',
             self._clipboard_clear, "os_clipboard", "__CLEAR__"),
            (r'\b(?:coloc[ae]r?|copi[ae]r?)\s+(.+?)\s+(?:na|pra|para\s+a?)\s*(?:área|area)\s+de\s+transfer[êe]ncia\b',
             self._clipboard_text, "os_clipboard", None),
            # Open apps
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|inicie|inicia|iniciar|executa|execute|executar|quero\s+abrir)\s+'
             r'(?:o\s+)?(?:bloco\s+de\s+notas|notepad)\s*[.!?]*$',
             self._open_notepad, "os_app", "notepad"),
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|inicie|inicia|iniciar|executa|execute|executar|quero\s+abrir)\s+'
             r'(?:o\s+)?(?:google\s+chrome|chrome)\s+(?:no|com o)\s+perfil\s+(.+?)\s*[.!?]*$',
             self._open_chrome_profile, "chrome_open_profile", None),
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
            # Apps fora dos 9 originais (Telegram, Obsidian, WinRAR, WordPad,
            # EA App, NVIDIA App, Windows Media Player e o resto da lista real
            # de apps do Alex) nao tem regex proprio: caem no catch-all generico
            # de abrir/fechar mais abaixo, que resolve o nome falado contra
            # _APP_ALIASES em os_ops.py. Isso evita crescer este arquivo a cada
            # app novo instalado.
            (r'^(?:zara[,\s]+)?(?:abr[ae]|abrir|mostr[ae]|v[áa]\s+(?:pra|para))\s+(?:a\s+)?(?:pasta\s+(?:de\s+|dos\s+)?)?(?:meus?\s+)?downloads\s*[.!?]*$',
             self._open_downloads, "os_open", "downloads"),
            (r'^(?:zara[,\s]+)?(?:abr[ae]|abrir|mostr[ae]|v[áa]\s+(?:pra|para))\s+(?:a\s+)?(?:pasta\s+(?:de\s+|dos\s+)?)?(?:meus?\s+)?(?:documentos|documents)\s*[.!?]*$',
             self._open_documents, "os_open", "documents"),
            # ZARA-DESKTOP-ARTIGO-001: "area de trabalho" (sem acento, comum em
            # texto digitado e em STT) e "abra O desktop" (artigo masculino)
            # nao casavam -- so existia "a" + "área" acentuada, entao os dois
            # caiam no catch-all generico de app e viravam "ainda nao sei fazer".
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|mostre|v[áa]\s+para)\s+(?:(?:a\s+)?[áa]rea\s+de\s+trabalho|(?:o\s+)?desktop)\s*[.!?]*$',
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
            # ZARA-VA-AO-YOUTUBE-001: "va AO youtube" (contracao a+o) e tao comum
            # quanto "va PARA o youtube", mas so a segunda forma casava -- em
            # comando composto ("abra o Chrome, va ao YouTube e pesquise X") a
            # etapa inteira virava "ainda nao sei fazer" por causa dessa unica
            # preposicao faltando.
            (r'^(?:zara[,\s]+)?(?:(?:abra|abre|abrir|acesse|v[áa]\s+para)\s+(?:o\s+)?|v[áa]\s+ao\s+)youtube\s*[.!?]*$',
             self._browser_native, "youtube_open", "youtube"),
                        (r'\b(?:pesquis[ae]r?|procur[ae]r?|busc[ae]r?|toc[ae]r?)\s+(.+?)\s+(?:no|na)\s+youtube\b',
                         self._media_query, "youtube_search", None),
                        (r'^(?:zara[,\s]+)?(?:toque|toca|coloque|bote|quero\s+ouvir)\s+(?:por\s+)?(.+?)\s*[.!?]*$',
                         self._media_query, "youtube_play_by_name", None),
                        (r'^(?:zara[,\s]+)?(?:toque|toca|coloque|bote|quero\s+ouvir)\s+m[úu]sica\s*[.!?]*$',
                         self._media_query, "youtube_play_by_name", "random"),
                        (r'^(?:zara[,\s]+)?(?:pule|pula|pular)\s+(?:a\s+)?m[úu]sica\s*[.!?]*$',
                         self._media_next, "youtube_next", "next"),
                        (r'^(?:zara[,\s]+)?(?:pr[óo]xima|proxima)\s+(?:m[úu]sica|faixa)\s*[.!?]*$',
                         self._media_next, "youtube_next", "next"),
            (r'\b(?:o\s+que\s+(?:est[áa]|ta)\s+(?:tocando|passando)|qual\s+(?:m[úu]sica|v[íi]deo)\s+(?:est[áa]|ta)\s+tocando)\b',
             self._youtube_now_playing, "youtube_now_playing", "current"),
            (r'^(?:zara[,\s]+)?(?:(?:n[ãa]o\s+gostei(?:\s+dessa\s+m[úu]sica)?[,\s]+)?(?:coloque|coloca|bote|bota)\s+outra\s+(?:dele|dela|desse\s+artista)|outra\s+desse\s+artista)\s*[.!?]*$',
             self._youtube_another, "youtube_another_by_artist", "current_artist"),
            (r'^(?:zara[,\s]+)?(?:pesquise?|procure|busque?)\s+(.+?)\s+(?:no|na)\s+spotify\s*[.!?]*$',
             self._media_query, "spotify_search", None),
            (r'\b(?:pul[ae]r?|pass[ae]r?|skip)\s+(?:o\s+)?an[úu]ncio\b',
             self._youtube_skip_ad, "youtube_skip_ad", "skip"),
            (r'\b(?:abr[ae]r?)\s+(?:uma\s+)?(?:nova\s+(?:guia|aba)|(?:guia|aba)\s+nova)\b',
             self._browser_native, "browser_new_tab", "new_tab"),
            (r'\b(?:volt[ae]r?)\s+(?:no|pelo|na)\s+(?:navegador|p[áa]gina|chrome)\b',
             self._browser_native, "browser_back", "back"),
            (r'\b(?:avanc?[ae]r?|avanç[ae]r?)\s+(?:no|pelo|na)\s+(?:navegador|p[áa]gina|chrome)\b',
             self._browser_native, "browser_forward", "forward"),
            (r'^(?:zara[,\s]+)?(?:feche|fecha)\s+(?:essa|esta|a)\s+(?:guia|aba)\s*[.!?]*$',
             self._browser_native, "browser_close_tab", "close"),
            (r'^(?:zara[,\s]+)?(?:(?:o\s+que\s+diz)|(?:resuma|resume)|(?:qual\s+[ée]\s+o\s+assunto\s+d[ae]))\s+(?:essa|esta|a)\s+p[áa]gina\s*[.!?]*$',
             self._browser_native, "browser_read_page", "read"),
            (r'\b(?:tir[ae]r?|faz|faça|fazer|captur[ae]r?|print[ae]?r?)\s+(?:uma\s+|um\s+)?(?:captura\s+de\s+tela|screenshot|print\s+da\s+tela|print)\b',
             self._screenshot, "vision_screenshot", "full"),
            (r'\b(?:mostr[ae]r?|envi[ae]r?|cri[ae]r?|manda?r?)\s+(?:uma\s+)?notifica[çc][ãa]o(?:\s+dizendo)?\s+(.+?)\s*[.!?]*$',
             self._notification_message, "os_notify", None),

            # Read-only system truth.
            (r'^(?:zara[,\s]+)?(?:que\s+horas\s+(?:s[ãa]o|sao)|qual\s+(?:é|e)\s+a\s+hora|hora\s+local)\s*[.!?]*$',
             self._system_info, "system_time", "local"),
            (r'\b(?:como\s+(?:est[áa]|ta)\s+o\s+(?:computador|pc)|status\s+do\s+(?:computador|pc)|uso\s+de\s+(?:cpu|ram|mem[óo]ria)|quanto\s+de\s+bateria|quanta\s+bateria|n[íi]vel\s+da\s+bateria)\b',
             self._system_metrics, "system_metrics", "summary"),
            (r'\b(?:mostr[ae]r?|diz|diga|quais\s+s[ãa]o)\s+(?:as\s+)?informa[çc][õo]es\s+do\s+sistema\b',
             self._system_info, "system_info", "basic"),
            (r'\b(?:list[ae]r?|mostr[ae]r?|quais)\s+(?:os\s+)?processos(?:\s+est[ãa]o\s+rodando)?\b',
             self._system_processes, "system_processes", "top"),

            # Search
            (r'^(?:zara[,\s]+)?(pesquis[ae]r?|procur[ae]r?|search|busc[ae]r?)\s+(por\s+)?(.+?)\s*[.!?]*$',
             self._search, "browser_search", None),

            # Volume
            # ZARA-VOICE-VERBOS-002: faltavam "poe/bota/ajusta" e a preposicao "pra".
            (r'\b(?:coloc[ae]r?|defin[ae]r?|ponha|p[oõ]e|bot[ae]r?|deix[ae]r?|ajust[ae]r?|set)\s+(?:o\s+)?volume\s+(?:em|para|pra|a)\s*(\d{1,3})\s*%?\b',
             self._volume_level, "os_volume", None),
            (r'\bvolume\s+(?:em\s+|para\s+|pra\s+|a\s+)?(\d{1,3})\s*%?\b',
             self._volume_level, "os_volume", None),
            # Volume (aceita imperativo E infinitivo: "aumente/aumentar/aumenta",
            # "diminua/diminuir", "suba/subir", "baixe/baixar/abaixar").
            (r'\b(?:aument[ae]r?|sob[ae]|suba|subir|subo|up|mais\s+volume|increase?)\s+'
             r'(?:(?P<intensity>um\s+pouquinho|um\s+pouco|levemente|muito|bastante|demais|bem)\s+)?'
             r'(?:o\s+)?volume\b',
             self._volume_up, "os_volume", "up"),
            (r'\b(?:diminu(?:[ae]r?|ir?)|baix[ae]r?|abaix[ae]r?|down|menos\s+volume|decrease?|lower)\s+'
             r'(?:(?P<intensity>um\s+pouquinho|um\s+pouco|levemente|muito|bastante|demais|bem)\s+)?'
             r'(?:o\s+)?volume\b',
             self._volume_down, "os_volume", "down"),
            # ZARA-VOICE-VERBOS-003: "põe/bota/coloca o volume/som lá embaixo"
            # -- frase do dia a dia sem numero, so intencao de baixar bastante.
            # ZARA-INTENSIDADE-VOLUME-001: o idioma "lá embaixo" já É um pedido
            # forte por natureza -- não existe "lá embaixo, mas só um pouco".
            (r'\b(?:p[oõ]e|ponha|bot[ae]|coloc[ae])\s+(?:o\s+)?(?:volume|som)\s+l[áa]\s+(?:em\s*baixo|embaixo)\b',
             self._volume_down_forte, "os_volume", "down_muito"),

            # Media controls are deliberately anchored to avoid collisions
            # with ordinary conversation such as "faça uma pausa no projeto".
            (r'^(?:zara[,\s]+)?(?:pause(?:\s+(?:a\s+)?música)?|pausa)\s*[.!?]*$',
             self._youtube_pause, "youtube_pause", "pause"),
            (r'^(?:zara[,\s]+)?(?:continue(?:\s+(?:a\s+)?música)?|continua(?:\s+(?:a\s+)?música)?|play)\s*[.!?]*$',
             self._youtube_resume, "youtube_resume", "resume"),
            (r'\b(?:avanc?[ae]r?|avanç[ae]r?|adiant[ae]r?|pul[ae]r?)\s+(\d{1,4})\s+segundos?\b',
             self._youtube_seek_forward, "youtube_seek", None),
            (r'\b(?:volt[ae]r?|retroced[ae]r?|retorn[ae]r?)\s+(\d{1,4})\s+segundos?\b',
             self._youtube_seek_backward, "youtube_seek", None),
            (r'^(?:zara[,\s]+)?(?:volte|volta)\s+um\s+pouco\s*[.!?]*$',
             self._youtube_seek_small_back, "youtube_seek", "-10"),
            (r'^(?:zara[,\s]+)?(?:recomece|recomeça|reinicie|volte\s+ao\s+início)(?:\s+(?:essa|a)\s+(?:música|faixa|vídeo))?\s*[.!?]*$',
             self._youtube_restart, "youtube_seek", "restart"),
            (r'^(?:zara[,\s]+)?(?:pr[óo]xima(?:\s+m[úu]sica)?|pul[ae]\s+essa|pul[ae]\s+(?:a\s+)?m[úu]sica|next)\s*[.!?]*$',
             self._media_next, "youtube_next", "next"),
            (r'^(?:zara[,\s]+)?(?:anterior|música\s+anterior|volt[ae]\s+(?:a\s+)?(?:música|faixa))\s*[.!?]*$',
             self._media_previous, "media_previous", "previous"),
            # ZARA-VOICE-VERBOS-002: mudo em fala real -> "muta", "tira o som",
            # "deixa mudo", "silencia". Desmutar -> "volta o som", "tira do mudo".
            # O unmute vem ANTES do mute: "tira o som" e mute, mas "volta o som"
            # e unmute, e a ordem evita que um coma o outro.
            (r'^(?:zara[,\s]+)?(?:volt(?:a|e)|devolv(?:a|e)|retom(?:a|e))\s+(?:o\s+)?(?:som|audio|áudio)\s*[.!?]*$',
             self._audio_unmute, "audio_unmute", "unmute"),
            (r'\b(?:tir[ae]r?\s+(?:do\s+|o\s+)?mudo|retir[ae]r?\s+do\s+mudo|desativ[ae]r?\s+(?:o\s+)?mudo|desmut[ae]r?|unmute)\b',
             self._audio_unmute, "audio_unmute", "unmute"),
            (r'^(?:zara[,\s]+)?(?:mute|mut[ae]|silenci[ae]|(?:ativ(?:a|e)|lig(?:a|ue)|coloc(?:a|ue)|deix(?:a|e)|p[oõ]e|ponha)\s+(?:no\s+|o\s+)?mudo)\s*[.!?]*$',
             self._audio_mute, "audio_mute", "mute"),
            (r'^(?:zara[,\s]+)?(?:tir(?:a|e)|cort(?:a|e)|deslig(?:a|ue))\s+(?:o\s+)?(?:som|audio|áudio)\s*[.!?]*$',
             self._audio_mute, "audio_mute", "mute"),
            (r'\b(?:qual\s+(?:é|e)\s+o\s+dispositivo\s+de\s+(?:áudio|audio)|status\s+d[eo]\s+(?:áudio|audio)|como\s+(?:está|esta)\s+o\s+(?:áudio|audio))\b',
             self._audio_status, "audio_status", "status"),

            # Silent Windows radios (WinRT API, no Quick Settings flyout).
            # ZARA-VOICE-VERBOS-002: eram ancorados e so aceitavam "ative/ligue".
            # A fala real usa "liga o wifi", "ativa o wi-fi", "desliga o bluetooth".
            (r'\b(?:ativ(?:a|e|ar)|lig(?:a|ue|ar))\s+(?:o\s+)?wi-?\s?fi\b',
             self._radio_on, "os_wifi_on", "on"),
            (r'\b(?:desativ(?:a|e|ar)|deslig(?:a|ue|ar)|tir(?:a|e|ar))\s+(?:o\s+)?wi-?\s?fi\b',
             self._radio_off, "os_wifi_off", "off"),
            (r'\b(?:ativ(?:a|e|ar)|lig(?:a|ue|ar))\s+(?:o\s+)?bluetooth\b',
             self._radio_on, "os_bluetooth_on", "on"),
            (r'\b(?:desativ(?:a|e|ar)|deslig(?:a|ue|ar)|tir(?:a|e|ar))\s+(?:o\s+)?bluetooth\b',
             self._radio_off, "os_bluetooth_off", "off"),

            # Brightness and night-light controls.
            # ZARA-VOICE-VERBOS-001: os padroes de brilho eram ancorados (^...$)
            # e so aceitavam o imperativo culto. "diminui o brilho", "abaixa o
            # brilho ai" e "deixa a tela mais escura" nao casavam, caiam no LLM
            # e voltavam como falso sucesso. Agora sao delimitados por \b, como
            # os de volume — que por isso sempre funcionaram.
            # AUDITORIA_2026-08-27 item 1.6: o numero so casa colado em "brilho"
            # (so um espaco/preposicao curta no meio), entao frases soltas tipo
            # "o brilho daquele quadro e uns 80" nao disparam isto (verificado
            # empiricamente). A preposicao "a" foi removida por ser generica
            # demais e coincidir com expressoes de hora ("brilho a 3 da tarde").
            (r'\b(?:coloc\w+|ponha|p[oõ]e|bote|bota|defin\w+|deix\w+|ajust\w+|deixa)?\s*'
             r'(?:o\s+)?brilho\s+(?:em|para|pra)?\s*(\d{1,3})\s*%?',
             self._brightness_level, "os_brightness_absolute", None),
            (r'\bbrilho\s+(?:em\s+)?(\d{1,3})\s*%?',
             self._brightness_level, "os_brightness_absolute", None),
            (r'\b(?:aument\w+|sob[ae]|sub\w+|clarei\w+)\s+'
             r'(?:(?P<intensity>um\s+pouquinho|um\s+pouco|levemente|muito|bastante|demais|bem)\s+)?'
             r'(?:o\s+)?brilho',
             self._brightness_up, "os_brightness_up", "up"),
            (r'\b(?:mais\s+claro|clareia|clareie)\b',
             self._brightness_up, "os_brightness_up", "up"),
            (r'\b(?:diminu\w+|abaix\w+|baix\w+|reduz\w*|escurec\w+)\s+'
             r'(?:(?P<intensity>um\s+pouquinho|um\s+pouco|levemente|muito|bastante|demais|bem)\s+)?'
             r'(?:o\s+)?brilho',
             self._brightness_down, "os_brightness_down", "down"),
            (r'\b(?:mais\s+escur[oa]|escurece|escureca)\b',
             self._brightness_down, "os_brightness_down", "down"),
            # ZARA-VOICE-VERBOS-002: "ativa o modo noturno", "liga a luz noturna",
            # "tira o modo noturno" nao casavam. Agora delimitado por \b.
            (r'\b(?:ativ(?:a|e|ar)|lig(?:a|ue|ar)|coloc(?:a|ue|ar)|p[oõ]e|ponha)\s+(?:(?:a\s+)?luz|(?:o\s+)?modo)\s+noturn[oa]\b',
             self._night_light_on, "os_night_light_on", "on"),
            (r'\b(?:desativ(?:a|e|ar)|deslig(?:a|ue|ar)|tir(?:a|e|ar)|remov(?:a|e|er))\s+(?:(?:a\s+)?luz|(?:o\s+)?modo)\s+noturn[oa]\b',
             self._night_light_off, "os_night_light_off", "off"),

            # Window controls are anchored and never include close/Alt+F4.
            (r'^(?:zara[,\s]+)?(?:minimiz[ae]|minimizar)(?:\s+(?:a|esta|essa)\s+janela)?\s*[.!?]*$',
             self._window_minimize, "window_minimize", "active"),
            (r'^(?:zara[,\s]+)?(?:maximiz[ae]|maximizar)(?:\s+(?:a|esta|essa)\s+janela)?\s*[.!?]*$',
             self._window_maximize, "window_maximize", "active"),
            (r'^(?:zara[,\s]+)?(?:(?:restaur[ae]|restaurar)(?:\s+(?:a|esta|essa)\s+janela)?|volt[ae]\s+a\s+janela\s+ao\s+normal)\s*[.!?]*$',
             self._window_restore, "window_restore", "active"),
            # ZARA-JANELA-NOMEADA-001: as tres acima so cobriam a janela
            # ATIVA/contextual. "Minimize o Chrome" pede uma janela por NOME,
            # que pode nem estar em foco -- mesmos quatro alvos ja permitidos
            # em window_focus_named (chrome/zara/vscode/project), agora tambem
            # para minimizar/maximizar/restaurar.
            (r'^(?:zara[,\s]+)?(?:minimiz[ae]|minimizar)\s+(?:a\s+janela\s+d[oe]\s+|o\s+|a\s+)?chrome\s*[.!?]*$',
             self._window_chrome, "window_minimize", "chrome"),
            (r'^(?:zara[,\s]+)?(?:maximiz[ae]|maximizar)\s+(?:a\s+janela\s+d[oe]\s+|o\s+|a\s+)?chrome\s*[.!?]*$',
             self._window_chrome, "window_maximize", "chrome"),
            (r'^(?:zara[,\s]+)?(?:restaur[ae]|restaurar)\s+(?:a\s+janela\s+d[oe]\s+|o\s+|a\s+)?chrome\s*[.!?]*$',
             self._window_chrome, "window_restore", "chrome"),
            (r'^(?:zara[,\s]+)?(?:minimiz[ae]|minimizar)\s+(?:a\s+janela\s+d[oe]\s+|o\s+|a\s+)?zara\s*[.!?]*$',
             self._window_zara, "window_minimize", "zara"),
            (r'^(?:zara[,\s]+)?(?:maximiz[ae]|maximizar)\s+(?:a\s+janela\s+d[oe]\s+|o\s+|a\s+)?zara\s*[.!?]*$',
             self._window_zara, "window_maximize", "zara"),
            (r'^(?:zara[,\s]+)?(?:restaur[ae]|restaurar)\s+(?:a\s+janela\s+d[oe]\s+|o\s+|a\s+)?zara\s*[.!?]*$',
             self._window_zara, "window_restore", "zara"),
            (r'^(?:zara[,\s]+)?(?:minimiz[ae]|minimizar)\s+(?:a\s+janela\s+d[oe]\s+|o\s+|a\s+)?(?:vs\s*code|visual\s+studio\s+code)\s*[.!?]*$',
             self._window_vscode, "window_minimize", "vscode"),
            (r'^(?:zara[,\s]+)?(?:maximiz[ae]|maximizar)\s+(?:a\s+janela\s+d[oe]\s+|o\s+|a\s+)?(?:vs\s*code|visual\s+studio\s+code)\s*[.!?]*$',
             self._window_vscode, "window_maximize", "vscode"),
            (r'^(?:zara[,\s]+)?(?:restaur[ae]|restaurar)\s+(?:a\s+janela\s+d[oe]\s+|o\s+|a\s+)?(?:vs\s*code|visual\s+studio\s+code)\s*[.!?]*$',
             self._window_vscode, "window_restore", "vscode"),
            (r'^(?:zara[,\s]+)?(?:minimiz[ae]|minimizar)\s+(?:a\s+janela\s+d[oe]\s+|o\s+|a\s+)?projeto\s*[.!?]*$',
             self._window_project, "window_minimize", "project"),
            (r'^(?:zara[,\s]+)?(?:maximiz[ae]|maximizar)\s+(?:a\s+janela\s+d[oe]\s+|o\s+|a\s+)?projeto\s*[.!?]*$',
             self._window_project, "window_maximize", "project"),
            (r'^(?:zara[,\s]+)?(?:restaur[ae]|restaurar)\s+(?:a\s+janela\s+d[oe]\s+|o\s+|a\s+)?projeto\s*[.!?]*$',
             self._window_project, "window_restore", "project"),
            (r'\b(?:troc[ae]r?\s+de\s+janela|v[áa]\s+(?:pra|para)\s+a\s+pr[óo]xima\s+janela|pr[óo]xima\s+janela)\b',
             self._window_switch, "window_switch_next", "next"),
            (r'\b(?:traz|traga|coloc[ae]r?|foc[ae]r?|v[áa]\s+(?:pro|para\s+o))\s+(?:n[oa]\s+)?(?:o\s+)?chrome(?:\s+(?:pra|para)\s+frente)?\b',
             self._window_chrome, "window_focus_named", "chrome"),
            (r'^(?:zara[,\s]+)?(?:volta|volte|traz|traga)\s+(?:pra|para)\s+(?:a\s+)?zara\s*[.!?]*$',
             self._window_zara, "window_focus_named", "zara"),
            (r'^(?:zara[,\s]+)?(?:troca|troque|mude)\s+(?:para|pro|para\s+o)\s+(?:o\s+)?(?:vs\s*code|visual\s+studio\s+code)\s*[.!?]*$',
             self._window_vscode, "window_focus_named", "vscode"),
            (r'^(?:zara[,\s]+)?(?:mostra|mostre|traz|traga)\s+(?:o\s+)?projeto\s*[.!?]*$',
             self._window_project, "window_focus_named", "project"),

            # Scroll
            (r'^(?:zara[,\s]+)?(?:rol[ae]|scroll|desç[ae]|descer|desce)(?:\s+(?:a\s+)?p[áa]gina)?(?:\s+(?:pra|para)?\s*baixo)?\s*[.!?]*$',
             self._scroll_down, "browser_scroll", "down"),
            (r'^(?:zara[,\s]+)?(?:rol[ae]|scroll|sub[ae]|subir|sobe)(?:\s+(?:a\s+)?p[áa]gina)?(?:\s+(?:pra|para)?\s*cima|\s+um\s+pouco)?\s*[.!?]*$',
             self._scroll_up, "browser_scroll", "up"),

            # Explicitly catch unsupported app requests after all known safe
            # commands. The raw text is never executed.
            (r'^(?:zara[,\s]+)?(?:abra|abre|abrir|inicie|inicia|iniciar|executa|execute|executar|quero\s+abrir)\s+'
             r'(?P<app>.+?)\s*[.!?]*$',
             self._unsupported_app, "os_app", None),
            (r'^(?:zara[,\s]+)?(?:feche|fecha|fechar)\s+(?P<app>.+?)\s*[.!?]*$',
             self._unsupported_close_app, "os_close_safe_app", None),
        ]

    # ZARA-VOICE-SEGURANCA-001 / ZARA-RECUSA-HONESTA-001
    #
    # A primeira versao deste guarda rodava na ENTRADA de `detect` e devolvia
    # `is_pc_intent=False` para qualquer texto contendo sintaxe de shell OU o
    # nome de um programa perigoso. Duas consequencias, ambas ruins:
    #
    # 1. Silencio em vez de recusa. "abra powershell" saia daqui como "nao e
    #    comando de PC" e caia no LLM, entao a ZARA nao executava (certo) mas
    #    tambem nao dizia que era proibido (errado). O contrato do projeto
    #    exige recusa honesta, nao mudez.
    # 2. Falso positivo em fala inocente. A lista tinha `python`, `reg`, `sh`,
    #    `curl`: "procure por Python asyncio" virava texto perigoso e a busca
    #    era recusada em silencio.
    #
    # Agora a defesa e por PARAMETRO, depois do casamento, e so contra
    # SINTAXE (encadeamento de comando e travessia de caminho) — nunca contra
    # nomes de programa, que ja sao barrados pela allowlist de `os_app`.
    _SINTAXE_PERIGOSA = re.compile(r'(?:&&|\|\||[;`]|\$\(|\.\.[\\/]|[\\/]\.\.)')

    # Acoes cujo parametro e texto para ler/digitar/buscar, nunca caminho ou
    # comando. Aqui "&&" e um caractere qualquer e nao pode bloquear a frase.
    _ACOES_DE_TEXTO_LIVRE = frozenset({
        "browser_search", "input_type_text", "os_clipboard",
    })

    def detect(self, text: str) -> PcVoiceResult:
        """Detect PC control intent in text."""
        if not text:
            return PcVoiceResult(is_pc_intent=False)

        text_lower = text.lower().strip()

        # Destructive drive formatting has no executable voice route. Keep it
        # explicit before learned shortcuts or the conversational fallback.
        if re.fullmatch(r'(?:zara[,\s]+)?format(?:ar|e|a)\s+(?:(?:o\s+)?(?:disco|drive|volume)\s+)?[a-z]:?\s*[.!?]*', text_lower):
            return PcVoiceResult(is_pc_intent=True, blocked=True, reply="Não formato discos por comando de voz.")

        # Fast Path - Intenções Aprendidas: Verificar primeiro no cache de aprendizados
        # Se uma forma de pedido já foi aprendida (acertos >= erros), usar diretamente
        # sem consultar LLM.
        try:
            aprendizado = Aprendizado()
            intencao = aprendizado.intencao_aprendida(text_lower)
            if intencao and intencao.get("acao"):
                action_name = intencao["acao"]
                # Verificar se a ação ainda existe no registry
                registry = get_registry()
                if action_name in registry.get_all_specs():
                    return PcVoiceResult(
                        is_pc_intent=True,
                        action=action_name,
                        param="",  # Parâmetros podem ser extraídos depois pelo ipc_handlers se necessário
                        physical_effect=1,
                        reply="",
                    )
        except Exception:
            pass  # Falha silenciosa para não atrapalhar o fluxo principal

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
            r'\b(?:(?:deixa?|deixe)\s+(?:o\s+volume\s+)?|agora\s+)?'
            r'(?:(?P<intensity>um\s+pouquinho|um\s+pouco|levemente|muito|bastante|demais|bem)\s+)?'
            r'mais\s+(?P<direction>alto|baixo)\b',
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
            direction = "up" if contextual_volume.group("direction") == "alto" else "down"
            return PcVoiceResult(
                is_pc_intent=True,
                action="os_volume",
                param=_encode_intensity(direction, contextual_volume.groupdict().get("intensity")),
                physical_effect=1,
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
            return PcVoiceResult(
                is_pc_intent=True,
                action=action,
                physical_effect=1,
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
            return PcVoiceResult(
                is_pc_intent=True,
                action="os_open",
                param=self.folder_context,
                physical_effect=1,
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

        for pattern, action, default_param in self.advanced_patterns:
            advanced_match = re.search(pattern, text_lower)
            if not advanced_match:
                continue
            param = advanced_match.group(1).strip() if advanced_match.lastindex else default_param
            translations = {
                "esquerda": "left", "direita": "right", "cima": "up", "baixo": "down",
                "anterior": "previous", "seguinte": "next",
            }
            param = translations.get(str(param), param)
            return PcVoiceResult(
                is_pc_intent=True, action=action, param=param or "",
                physical_effect=1,
            )

        for pattern, handler, action, default_param in self.patterns:
            m = re.search(pattern, text_lower)
            if m:
                param = handler(m)
                if default_param and not param:
                    param = default_param

                if action == "os_app" and param not in {
                    "notepad", "chrome", "task_manager", "settings",
                    "paint", "snipping_tool", "edge", "spotify",
                    "telegram", "obsidian", "winrar", "wordpad",
                }:
                    # ZARA-APPS-REAIS-2026-08-27: antes de recusar, tenta achar
                    # o app pelo apelido falado (ex.: "cursor",
                    # "geforce now") na lista real de apps instalados do Alex.
                    resolved = resolve_app_alias(param)
                    if resolved:
                        param = resolved
                    else:
                        return PcVoiceResult(
                            is_pc_intent=True,
                            action="os_app",
                            param=param,
                            blocked=True,
                            physical_effect=0,
                            reply=RESPOSTA_NAO_SEI,
                        )

                if action == "os_close_safe_app" and param not in _SAFE_CLOSE_APPS:
                    resolved = resolve_app_alias(param)
                    if resolved and resolved in _SAFE_CLOSE_APPS:
                        param = resolved
                    else:
                        return PcVoiceResult(
                            is_pc_intent=True,
                            action="os_close_safe_app",
                            param=param,
                            blocked=True,
                            physical_effect=0,
                            reply=RESPOSTA_NAO_SEI,
                        )

                # Defesa de sintaxe: encadeamento de comando ou travessia de
                # caminho num parametro que vai virar acao no Windows. Recusa
                # falada, nunca silencio.
                if (
                    action not in self._ACOES_DE_TEXTO_LIVRE
                    and param
                    and self._SINTAXE_PERIGOSA.search(str(param))
                ):
                    return PcVoiceResult(
                        is_pc_intent=True,
                        action=action,
                        param=param,
                        blocked=True,
                        physical_effect=0,
                        reply=RESPOSTA_NAO_SEI,
                    )

                return PcVoiceResult(
                    is_pc_intent=True,
                    action=action,
                    param=param,
                    physical_effect=1,
                    reply="",
                )

        # Try free reasoning fallback as last resort
        # Quick heuristic: if text is very short or looks like greeting/small talk, skip
        text_clean = text.strip().lower()
        if len(text_clean) >= 3 and text_clean not in {"hi", "hello", "hey", "thanks", "thank you", "ok", "okay"}:
            try:
                # Get available actions for validation
                registry = get_registry()
                available_actions = set(registry.get_all_specs().keys())
                
                # Prepare the LLM prompt for tool use
                # Use all available actions but limit prompt size if needed
                action_list = sorted(list(available_actions))
                
                # If action list is too long, prioritize PC control actions.
                # But for completeness, we'll use all actions and let validation handle it
                action_json = json.dumps(action_list, ensure_ascii=False)
                
                # Safety check: if prompt would be excessively long, truncate to most common actions
                if len(action_json) > 2000:  # Arbitrary limit to keep prompt reasonable
                    # Fall back to a reasonable subset of common PC control actions
                    common_actions = [
                        "os_volume", "os_brightness_absolute", "os_brightness_up", "os_brightness_down",
                        "os_night_light_on", "os_night_light_off", "os_wifi_on", "os_wifi_off",
                        "os_bluetooth_on", "os_bluetooth_off", "media_play_pause", "media_next",
                        "media_previous", "window_minimize", "window_maximize", "window_restore",
                        "window_close", "window_switch", "window_switch_next", "os_app", "os_open",
                        "os_close_safe_app", "input_type_text", "input_hotkey", "browser_new_tab",
                        "browser_back", "browser_forward", "youtube_search", "youtube_open",
                        "youtube_play_by_name", "spotify_search", "system_time", "system_info",
                        "claude_ler", "claude_enviar", "codex_ler", "codex_enviar", "ponte_repassar",
                        "aprendizado_resumo"
                    ]
                    # Filter to only actions that actually exist
                    action_list = [a for a in common_actions if a in available_actions]
                    action_json = json.dumps(action_list, ensure_ascii=False)
                
                prompt = f"""You are a PC control intent classifier for ZARA assistant.
Determine if the user's text is a command to control their Windows PC.
If YES, respond with JSON selecting the BEST matching action from this list:
{action_json}

If NO or uncertain, respond with {{"action": null}}.

User text: "{text}"

Respond ONLY with valid JSON, no extra text."""
                
                # Try Ollama qwen3:8b first (fastest local tool-capable model)
                ollama_url = "http://127.0.0.1:11434/v1/chat/completions"
                payload = {
                    "model": "qwen3:8b",
                    "messages": [
                        {"role": "system", "content": "You are a precise intent classifier. Respond only with valid JSON."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,  # Low temperature for consistent classification
                    "max_tokens": 100,   # We only need a short JSON response
                    "stream": False
                }
                
                # Make synchronous HTTP call with short timeout
                response = httpx.post(
                    ollama_url,
                    json=payload,
                    timeout=3.0  # 3 second timeout - fast fallback
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                    
                    # Try to parse JSON from the response
                    try:
                        # Extract JSON if it's wrapped in markdown or extra text
                        if content.startswith("```json"):
                            content = content.split("```json")[1].split("```")[0].strip()
                        elif content.startswith("```"):
                            content = content.split("```")[1].split("```")[0].strip()
                        
                        parsed = json.loads(content)
                        action_name = parsed.get("action")
                        
                        if action_name and isinstance(action_name, str) and action_name in available_actions:
                            # Valid action detected - extract parameters if any
                            params = parsed.get("param", "")
                            
                            # Auto-Aprendizado: aprender o mapeamento para que da
                            # próxima vez seja tratado no Fast Path local.
                            try:
                                aprendizado = Aprendizado()
                                aprendizado.reforjar_intencao(text, action_name, sucesso=True)
                            except Exception:
                                pass  # Falha silenciosa para não atrapalhar o fluxo

                            return PcVoiceResult(
                                is_pc_intent=True,
                                action=action_name,
                                param=str(params) if params else "",
                                physical_effect=0,  # Will be set correctly during execution
                                reply="",
                            )
                    except (json.JSONDecodeError, KeyError, TypeError):
                        # Invalid JSON response - fall through to return None
                        pass
            except Exception:
                # Any error in free reasoning - fail silently and fall back to deterministic
                pass
        
        return PcVoiceResult(is_pc_intent=False)

    # Handlers
    def _browser_native(self, m):
        return ""

    # ZARA-PONTE-CLAUDE-001
    def _claude_ler(self, m):
        return "read"

    # ZARA-PONTE-LEITURA-COMPLETA-002
    def _ler_resumido(self, m):
        return "resumido"

    # ZARA-APRENDIZADO-001
    def _o_que_aprendeu(self, m):
        return "hoje"

    # ZARA-PONTE-REPASSE-001
    def _repasse_claude_codex(self, m):
        return "claude>codex"

    def _repasse_codex_claude(self, m):
        return "codex>claude"

    def _claude_enviar(self, m):
        texto = m.group(1).strip()
        # Alex costuma abrir com "que"/"pra" quando dita: "responde pro Claude
        # que ele conserte o volume". Isso vira parte da frase e polui a
        # mensagem; tiramos só quando abre a fala.
        texto = re.sub(r'^(?:que\s+|pra\s+|para\s+)', '', texto)
        if len(texto) >= 2 and texto[0] in "'\"‘’“”" and texto[-1] in "'\"‘’“”":
            texto = texto[1:-1].strip()
        return texto[:2000]

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

    def _open_notepad(self, m):
        return "notepad"

    def _open_chrome(self, m):
        return "chrome"

    def _open_chrome_profile(self, m):
        return m.group(1).strip()

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

    def _unsupported_close_app(self, m):
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

    def _intensity_param(self, direction: str, m) -> str:
        """Le o grupo nomeado 'intensity' quando o regex que casou o tem;
        padroes sem esse grupo (ex. idioma fixo) simplesmente nao o carregam,
        e groupdict() nao levanta excecao por isso -- so nao acha a chave."""
        intensity_text = m.groupdict().get("intensity")
        return _encode_intensity(direction, intensity_text)

    def _volume_up(self, m):
        return self._intensity_param("up", m)

    def _volume_down(self, m):
        return self._intensity_param("down", m)

    def _volume_down_forte(self, m):
        return "down_muito"

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
        return self._intensity_param("up", m)

    def _brightness_down(self, m):
        return self._intensity_param("down", m)

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
