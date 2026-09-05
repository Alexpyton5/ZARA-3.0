"""A regressão nº 1 deste projeto: voz e texto divergirem.

`.claude/rules/path-rules/backend-core.md` diz, em letras maiúsculas, que
qualquer PR que adicione um intent a um lado e não ao outro é regressão. Até
aqui isso era uma regra escrita — nada quebrava quando alguém esquecia um
lado.

Este teste lê o SOURCE das duas entradas (`_process_voice_message`, que é a
voz, e `handle_send_message`, que é o texto) e exige que a sequência de
tentativas seja a mesma, na mesma ordem. É a mesma checagem que um humano
faria lendo os dois blocos lado a lado, só que automática.

Não substitui teste de comportamento: prova a ESTRUTURA, e a estrutura é
exatamente o que costuma sair de sincronia.
"""

import inspect
import re

from core.ipc_handlers import IPCHandler

# Ordem canônica documentada em backend-core.md.
CADEIA_ESPERADA = [
    "_try_jarvis_multi_action",
    "_try_reminder_intent",
    "_try_operational_memory_intent",
    "_try_self_knowledge",
    "_try_file_intent",
    "_try_compound_pc_intent",
    "_try_pc_intent",
    "_looks_like_unhandled_local_action",
]

_CHAMADA = re.compile(
    r"(?:self\.)?(" + "|".join(re.escape(n) for n in CADEIA_ESPERADA) + r")\s*\(\s*text\s*\)"
)


def _cadeia_de(func) -> list[str]:
    """Sequência de tentativas da cadeia, na ordem em que aparecem no source."""
    fonte = inspect.getsource(func)
    vistos: list[str] = []
    for nome in _CHAMADA.findall(fonte):
        # `_try_pc_intent` aparece duas vezes no fallback do composto; só a
        # primeira ocorrência conta para a ordem.
        if nome not in vistos:
            vistos.append(nome)
    return vistos


def test_voz_e_texto_percorrem_a_mesma_cadeia_na_mesma_ordem():
    voz = _cadeia_de(IPCHandler._process_voice_message)
    texto = _cadeia_de(IPCHandler.handle_send_message)

    assert voz == texto, (
        "Voz e texto divergiram.\n"
        f"  voz  : {voz}\n"
        f"  texto: {texto}\n"
        "Todo intent novo entra nos DOIS caminhos (backend-core.md)."
    )


def test_a_cadeia_e_a_documentada_em_backend_core_md():
    assert _cadeia_de(IPCHandler.handle_send_message) == CADEIA_ESPERADA


def test_nenhum_dos_dois_caminhos_perdeu_uma_etapa():
    for func in (IPCHandler._process_voice_message, IPCHandler.handle_send_message):
        faltando = set(CADEIA_ESPERADA) - set(_cadeia_de(func))
        assert not faltando, f"{func.__name__} não tenta: {sorted(faltando)}"
